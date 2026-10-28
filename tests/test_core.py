"""Adversarial synthetic tests; these do not call or benchmark any LLM."""

import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from queuecare import MAX_PROPOSAL_BYTES, validate_decision


def inputs():
    return (
        {"id": "evt-test", "source": "synthetic-erp", "order_id": "ORD-1",
         "sku": "old-sku", "quantity": 2, "status": "failed", "retry_count": 0},
        {"order_id": "ORD-1", "sku": "SKU-1", "quantity": 2},
        {"old-sku": ["SKU-1"]},
    )


NORMALIZE = '{"proposed_action":"normalize_sku","patch":{"sku":"SKU-1"}}'


class RecoveryBoundaryTests(unittest.TestCase):
    def assert_closed(self, result):
        self.assertFalse(result["approved"])
        self.assertEqual(result["action"], "manual_review")
        self.assertEqual(result["patch"], {})
        self.assertIsNone(result["retry_after_seconds"])

    def test_all_named_synthetic_scenarios_and_input_immutability(self):
        with (ROOT / "fixtures" / "cases.jsonl").open(encoding="utf-8") as stream:
            cases = [json.loads(line) for line in stream if line.strip()]
        self.assertGreaterEqual(len(cases), 12)
        self.assertEqual(len({case["name"] for case in cases}), len(cases))
        for case in cases:
            with self.subTest(case=case["name"]):
                self.assertIs(case["synthetic"], True)
                self.assertEqual(case["origin"], "hand_authored_synthetic_not_llm")
                before = copy.deepcopy(case)
                result = validate_decision(case["event"], case["order"],
                                           case["proposal"], case["alias_map"])
                for key, expected in case["expected"].items():
                    self.assertEqual(result[key], expected, key)
                self.assertEqual(case, before, "Validation changed a source record")
                if not result["approved"]:
                    self.assert_closed(result)
                if result["action"] == "normalize_sku":
                    self.assertEqual(result["patch"], {"sku": case["order"]["sku"]})
                    self.assertIsNone(result["retry_after_seconds"])
                else:
                    self.assertEqual(result["patch"], {})
                for key in ("event_sha256", "order_sha256", "proposal_sha256", "alias_map_sha256"):
                    self.assertRegex(result["provenance"][key], r"^[0-9a-f]{64}$")

    def test_all_immutable_patch_fields_are_blocked_even_when_values_unchanged(self):
        event, order, aliases = inputs()
        for field, value in (("id", event["id"]), ("source", event["source"]),
                             ("order_id", event["order_id"]), ("quantity", 2),
                             ("unit_price", 0), ("status", "completed"),
                             ("retry_count", 0)):
            with self.subTest(field=field):
                proposal = json.dumps({"proposed_action": "normalize_sku",
                                       "patch": {"sku": "SKU-1", field: value}})
                self.assert_closed(validate_decision(event, order, proposal, aliases))

    def test_raw_response_hash_preserves_exact_bytes_but_records_are_canonical(self):
        event, order, aliases = inputs()
        plain = validate_decision(event, order, NORMALIZE, aliases)
        spaced = validate_decision(dict(reversed(list(event.items()))), order, " " + NORMALIZE, aliases)
        self.assertTrue(plain["approved"])
        self.assertTrue(spaced["approved"])
        self.assertEqual(plain["provenance"]["event_sha256"], spaced["provenance"]["event_sha256"])
        self.assertNotEqual(plain["provenance"]["proposal_sha256"], spaced["provenance"]["proposal_sha256"])
        self.assertEqual(plain["provenance"]["proposal_sha256"], hashlib.sha256(NORMALIZE.encode()).hexdigest())
        changed = dict(event, source="different-source")
        self.assertNotEqual(plain["provenance"]["event_sha256"],
                            validate_decision(changed, order, NORMALIZE, aliases)["provenance"]["event_sha256"])

    def test_provenance_tracks_trusted_alias_and_order_changes(self):
        event, order, aliases = inputs()
        good = validate_decision(event, order, NORMALIZE, aliases)
        altered_order = validate_decision(event, dict(order, quantity=3), NORMALIZE, aliases)
        altered_alias = validate_decision(event, order, NORMALIZE, {"old-sku": ["OTHER"]})
        self.assert_closed(altered_order)
        self.assert_closed(altered_alias)
        self.assertNotEqual(good["provenance"]["order_sha256"], altered_order["provenance"]["order_sha256"])
        self.assertNotEqual(good["provenance"]["alias_map_sha256"], altered_alias["provenance"]["alias_map_sha256"])

    def test_untrusted_text_size_encoding_and_shape_fail_closed(self):
        event, order, aliases = inputs()
        malformed = [None, {}, b"\xff", b"\xef\xbb\xbf{}", "\ud800", "", "null", "false",
                     NORMALIZE + "{}", "x" * (MAX_PROPOSAL_BYTES + 1),
                     "[" * 1000 + "0" + "]" * 1000,
                     '{"proposed_action":"retry_later","retry_after_seconds":Infinity}',
                     '{"proposed_action":"retry_later","retry_after_seconds":-Infinity}']
        for proposal in malformed:
            with self.subTest(proposal=repr(proposal)[:80]):
                self.assert_closed(validate_decision(event, order, proposal, aliases))

    def test_valid_utf8_bytes_and_bounded_size_are_accepted(self):
        event, order, aliases = inputs()
        raw = NORMALIZE.encode()
        self.assertTrue(validate_decision(event, order, raw, aliases)["approved"])
        padded = raw + b" " * (MAX_PROPOSAL_BYTES - len(raw))
        self.assertTrue(validate_decision(event, order, padded, aliases)["approved"])
        self.assert_closed(validate_decision(event, order, padded + b" ", aliases))

    def test_retry_boundaries_and_retry_budget_are_not_off_by_one(self):
        event, order, aliases = inputs()
        event["sku"] = order["sku"]
        for count in (0, 2, 3, 99):
            for seconds in (29, 30, 3600, 3601, 30.0, True):
                with self.subTest(count=count, seconds=seconds):
                    event["retry_count"] = count
                    proposal = json.dumps({"proposed_action": "retry_later", "retry_after_seconds": seconds})
                    decision = validate_decision(event, order, proposal, aliases)
                    expected = count < 3 and type(seconds) is int and 30 <= seconds <= 3600
                    self.assertEqual(decision["approved"], expected)
                    if expected:
                        self.assertEqual(decision["retry_after_seconds"], seconds)
                    else:
                        self.assert_closed(decision)

    def test_bad_event_fields_never_become_model_repairable(self):
        event, order, aliases = inputs()
        for field, value in (("quantity", -1), ("quantity", 0), ("quantity", 2.0),
                             ("retry_count", True), ("retry_count", -1),
                             ("id", ""), ("source", None), ("sku", " old-sku ")):
            with self.subTest(field=field, value=value):
                self.assert_closed(validate_decision(dict(event, **{field: value}), order, NORMALIZE, aliases))
        self.assert_closed(validate_decision(dict(event, extra=float("nan")), order, NORMALIZE, aliases))
        cyclic = dict(event)
        cyclic["extra"] = cyclic
        self.assert_closed(validate_decision(cyclic, order, NORMALIZE, aliases))

    def test_aliases_are_exact_not_fuzzy_or_model_invented(self):
        event, order, aliases = inputs()
        for configured in ({}, {"OLD-SKU": ["SKU-1"]}, {"old-sku": ["SKU-1", "SKU-1"]},
                           {"old-sku": ["SKU-1", "OTHER"]}, {"old-sku": [None]},
                           {"old-sku": {"target": "SKU-1"}}, {"old-sku": ["OTHER"]}):
            with self.subTest(aliases=configured):
                self.assert_closed(validate_decision(event, order, NORMALIZE, configured))

    def test_result_changes_cannot_mutate_authoritative_inputs(self):
        event, order, aliases = inputs()
        before = copy.deepcopy((event, order, aliases))
        decision = validate_decision(event, order, NORMALIZE, aliases)
        decision["patch"]["sku"] = "tampered"
        decision["provenance"]["event_id"] = "tampered"
        self.assertEqual((event, order, aliases), before)
        repeated = validate_decision(event, order, NORMALIZE, aliases)
        self.assertEqual(repeated["patch"], {"sku": "SKU-1"})

    def test_nonmutating_actions_cannot_smuggle_retry_or_patch(self):
        event, order, aliases = inputs()
        for action in ("manual_review", "reject"):
            for extra in ({"patch": {}}, {"retry_after_seconds": 30}, {"reason": "override"}):
                with self.subTest(action=action, extra=extra):
                    proposal = json.dumps({"proposed_action": action, **extra})
                    self.assert_closed(validate_decision(event, order, proposal, aliases))


if __name__ == "__main__":
    unittest.main()
