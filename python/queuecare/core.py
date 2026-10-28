"""Validate recovery suggestions without trusting or executing model output.

This module performs no network requests, writes, retries, or model inference.
The caller must load ``order`` and ``alias_map`` from trusted application state,
not from a model response or the incoming event.  It must also perform the
approved operation atomically with its own idempotency and concurrency checks.

Model JSON has exactly one ``proposed_action`` plus action-specific fields:
* normalize_sku: ``patch`` containing exactly ``sku``.
* retry_later: integer ``retry_after_seconds`` from 30 through 3600.
* manual_review / reject: no additional fields.

Fixtures supplied with this project are synthetic, not recorded LLM results.
"""

import hashlib
import json
import math


MAX_PROPOSAL_BYTES = 8192
MAX_RETRIES = 3
MAX_JSON_DEPTH = 16
ACTIONS = frozenset({"normalize_sku", "retry_later", "manual_review", "reject"})


class _InvalidProposal(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _finite_json(value, depth=0):
    """Reject non-JSON objects and excessive nesting, including 1e999 floats."""
    if depth > MAX_JSON_DEPTH:
        raise ValueError("JSON nesting exceeds policy limit")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Non-finite JSON number")
        return
    if type(value) is list:
        for item in value:
            _finite_json(item, depth + 1)
        return
    if type(value) is dict and all(type(key) is str for key in value):
        for item in value.values():
            _finite_json(item, depth + 1)
        return
    raise ValueError("Input contains a non-JSON value")


def _canonical_hash(value):
    try:
        _finite_json(value)
        encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                             separators=(",", ":"), allow_nan=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
    except (ValueError, TypeError, OverflowError, UnicodeError, RecursionError):
        return None


def _raw_bytes(proposal):
    if type(proposal) is bytes:
        return proposal
    if type(proposal) is str:
        try:
            return proposal.encode("utf-8")
        except UnicodeError:
            return None
    return None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidProposal("duplicate_json_key", "Duplicate JSON keys are forbidden.")
        result[key] = value
    return result


def _invalid_constant(value):
    raise _InvalidProposal("nonfinite_number", "Non-finite numbers are forbidden.")


def _parse_proposal(raw):
    if raw is None:
        raise _InvalidProposal("invalid_proposal_type", "Model response must be UTF-8 JSON text.")
    if len(raw) > MAX_PROPOSAL_BYTES:
        raise _InvalidProposal("proposal_too_large", "Model response exceeds the size limit.")
    try:
        text = raw.decode("utf-8", errors="strict")
        value = json.loads(text, object_pairs_hook=_unique_object,
                           parse_constant=_invalid_constant)
        _finite_json(value)
    except _InvalidProposal:
        raise
    except (ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        raise _InvalidProposal("invalid_json", "Expected one finite JSON object without prose or fences.") from None
    if type(value) is not dict:
        raise _InvalidProposal("invalid_proposal_shape", "The model response must be a JSON object.")
    return value


def _text(value, limit=128):
    return type(value) is str and 0 < len(value) <= limit and value == value.strip()


def _integer(value, minimum=0):
    return type(value) is int and value >= minimum


def validate_decision(event, order, proposal, alias_map=None):
    """Return a new decision dict; never mutate event, order, or alias_map.

    ``approved`` says whether the suggestion passed policy.  Failed policy
    always yields ``manual_review``, an empty patch, and no retry interval.
    Approved manual_review/reject also have no patch or retry interval.
    Hashes use canonical UTF-8 JSON for source records and exact response bytes
    for the model proposal.  An unhashable invalid input has a null hash.
    """
    aliases = {} if alias_map is None else alias_map
    raw = _raw_bytes(proposal)
    provenance = {
        "hash_algorithm": "sha256",
        "record_encoding": "canonical-json-sort-keys-utf8",
        "event_sha256": _canonical_hash(event),
        "order_sha256": _canonical_hash(order),
        "proposal_sha256": hashlib.sha256(raw).hexdigest() if raw is not None else None,
        "alias_map_sha256": _canonical_hash(aliases),
        "event_id": event.get("id") if type(event) is dict and _text(event.get("id")) else None,
        "source": event.get("source") if type(event) is dict and _text(event.get("source"), 256) else None,
    }

    def result(code, reason, approved=False, action="manual_review", patch=None, wait=None):
        return {
            "schema_version": 1,
            "approved": approved,
            "action": action,
            "patch": {} if patch is None else patch,
            "retry_after_seconds": wait,
            "reason_code": code,
            "reason": reason,
            "provenance": dict(provenance),
        }

    if type(event) is not dict or provenance["event_sha256"] is None:
        return result("invalid_event", "The event must be a finite JSON object.")
    if not all(_text(event.get(key)) for key in ("id", "order_id", "sku", "status")) or not _text(event.get("source"), 256):
        return result("invalid_event", "Required event identifiers and status must be nonempty strings.")
    if not _integer(event.get("quantity"), 1) or not _integer(event.get("retry_count")):
        return result("invalid_event", "Quantity must be a positive integer and retry count a nonnegative integer.")
    if type(order) is not dict or provenance["order_sha256"] is None:
        return result("invalid_order", "An authoritative finite order record is required.")
    if not all(_text(order.get(key)) for key in ("order_id", "sku")) or not _integer(order.get("quantity"), 1):
        return result("invalid_order", "The authoritative order identifiers or quantity are invalid.")
    if type(aliases) is not dict or provenance["alias_map_sha256"] is None:
        return result("invalid_alias_map", "Alias configuration must be a finite JSON object.")

    try:
        suggested = _parse_proposal(raw)
    except _InvalidProposal as exc:
        return result(exc.code, str(exc))
    action = suggested.get("proposed_action")
    if type(action) is not str or action not in ACTIONS:
        return result("unknown_action", "The proposed action is not in the allowed action set.")
    expected_keys = {"proposed_action"}
    if action == "normalize_sku":
        expected_keys.add("patch")
    elif action == "retry_later":
        expected_keys.add("retry_after_seconds")
    if set(suggested) != expected_keys:
        return result("invalid_proposal_fields", "Only the exact fields for the proposed action are permitted.")

    # A mismatched immutable field cannot be repaired by a model suggestion.
    if event["order_id"] != order["order_id"]:
        return result("order_id_conflict", "Event and authoritative order identifiers disagree.")
    if event["quantity"] != order["quantity"]:
        return result("quantity_conflict", "Event and authoritative order quantities disagree.")
    if action in {"manual_review", "reject"}:
        return result("explicit_" + action, "The non-mutating disposition passed validation.", True, action)
    if event["status"] != "failed":
        return result("event_not_failed", "Automatic recovery is limited to failed events.")
    if event["retry_count"] >= MAX_RETRIES:
        return result("retry_budget_exhausted", "The event has exhausted its automatic recovery budget.")

    if action == "retry_later":
        wait = suggested["retry_after_seconds"]
        if not _integer(wait) or not 30 <= wait <= 3600:
            return result("invalid_retry_interval", "Retry interval must be an integer from 30 to 3600 seconds.")
        if event["sku"] != order["sku"]:
            return result("sku_conflict", "A mismatched SKU must not be retried unchanged.")
        return result("retry_validated", "Retry is bounded and the order identity, SKU, and quantity match.", True, action, wait=wait)

    patch = suggested["patch"]
    if type(patch) is not dict or set(patch) != {"sku"} or not _text(patch.get("sku")):
        return result("invalid_patch", "A normalization patch must contain exactly one nonempty SKU field.")
    if event["sku"] == order["sku"]:
        return result("normalization_unnecessary", "The SKU already matches the authoritative record.")
    candidates = aliases.get(event["sku"])
    if type(candidates) is str:
        candidates = [candidates]
    if type(candidates) is not list or len(candidates) == 0:
        return result("alias_missing", "No explicit alias mapping permits this correction.")
    if len(candidates) != 1:
        return result("alias_ambiguous", "The alias does not have exactly one configured target.")
    if not _text(candidates[0]):
        return result("invalid_alias_map", "The configured alias target is invalid.")
    if candidates[0] != order["sku"]:
        return result("alias_order_conflict", "The configured alias disagrees with the authoritative order.")
    if patch["sku"] != order["sku"]:
        return result("proposal_order_conflict", "The proposed SKU disagrees with the authoritative order.")
    return result("normalization_validated", "Exactly one explicit alias matches the authoritative SKU; immutable order fields agree.",
                  True, action, patch={"sku": order["sku"]})
