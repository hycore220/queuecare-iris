/// Embedded Python boundary: all values crossing it are JSON strings.
Class QueueCare.Bridge Extends %RegisteredObject
{
ClassMethod ParseJson(text As %String, maxBytes As %Integer = 32768) [ Language = python ]
{
    import json
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("Duplicate JSON key")
            out[key] = value
        return out
    def bad_constant(value):
        raise ValueError("Non-finite JSON number")
    if len(text.encode("utf-8")) > maxBytes:
        raise ValueError("JSON input is too large")
    value = json.loads(text, object_pairs_hook=unique, parse_constant=bad_constant)
    json.dumps(value, allow_nan=False)
    return value
}

ClassMethod IdentityJson(eventJSON As %String) As %String [ Language = python ]
{
    import json
    import hashlib
    import iris
    event = iris.cls("QueueCare.Bridge").ParseJson(eventJSON, 16384)
    if type(event) is not dict:
        raise ValueError("Event must be a JSON object")
    for name, limit in (("id", 128), ("source", 256), ("order_id", 128)):
        value = event.get(name)
        if type(value) is not str or not value or len(value) > limit or value != value.strip():
            raise ValueError("Missing or invalid event identity")
    canonical = json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    key = json.dumps([event["source"], event["id"]], ensure_ascii=False, separators=(",", ":"))
    result = {"source": event["source"], "event_id": event["id"], "order_id": event["order_id"],
              "event_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
              "key_sha256": hashlib.sha256(key.encode("utf-8")).hexdigest()}
    return json.dumps(result, ensure_ascii=False, separators=(",", ":"))
}

ClassMethod TextHash(text As %String) As %String [ Language = python ]
{
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
}

ClassMethod CanonicalHash(text As %String) As %String [ Language = python ]
{
    import json
    import hashlib
    import iris
    value = iris.cls("QueueCare.Bridge").ParseJson(text)
    canonical = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
}

ClassMethod ValidateJson(eventJSON As %String, orderJSON As %String, proposalJSON As %String, aliasJSON As %String = "{}") As %String [ Language = python ]
{
    import json
    import iris
    from queuecare.core import validate_decision
    bridge = iris.cls("QueueCare.Bridge")
    decision = validate_decision(bridge.ParseJson(eventJSON), bridge.ParseJson(orderJSON),
                                 proposalJSON, bridge.ParseJson(aliasJSON))
    return json.dumps(decision, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
}

ClassMethod PromptJson(eventJSON As %String, orderJSON As %String, aliasJSON As %String) As %String [ Language = python ]
{
    import json
    import iris
    bridge = iris.cls("QueueCare.Bridge")
    data = {"untrusted_event": bridge.ParseJson(eventJSON),
            "authoritative_order": bridge.ParseJson(orderJSON),
            "configured_sku_aliases": bridge.ParseJson(aliasJSON)}
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
}

ClassMethod DeliveryJson(eventJSON As %String, decisionJSON As %String) As %String [ Language = python ]
{
    import copy
    import json
    import iris
    bridge = iris.cls("QueueCare.Bridge")
    event = bridge.ParseJson(eventJSON)
    decision = bridge.ParseJson(decisionJSON)
    if decision.get("approved") is not True:
        raise ValueError("Policy validation did not pass")
    action = decision.get("action")
    payload = copy.deepcopy(event)
    if action == "normalize_sku":
        patch = decision.get("patch")
        if type(patch) is not dict or set(patch) != {"sku"} or type(patch["sku"]) is not str:
            raise ValueError("Invalid normalization patch")
        payload["sku"] = patch["sku"]
    elif action == "retry_later":
        if decision.get("patch") != {}:
            raise ValueError("Retry cannot modify an event")
    else:
        raise ValueError("This disposition cannot enter the local delivery sink")
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
}
}
