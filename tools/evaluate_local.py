"""Run real local Ollama calls on synthetic cases; not an IRIS or contest score."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from datetime import datetime, timezone
from urllib import request, error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from queuecare import validate_decision


def call_model(base_url, model, system, context, timeout):
    body = {"model": model, "stream": False, "think": False, "format": "json",
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(context, ensure_ascii=False)}],
            "options": {"temperature": 0, "seed": 7, "num_predict": 192}}
    req = request.Request(base_url.rstrip("/") + "/api/chat",
                          data=json.dumps(body).encode(),
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=timeout) as response:
        result = json.load(response)
    if "error" in result:
        raise RuntimeError(result["error"])
    return result["message"]["content"], {
        key: result.get(key) for key in
        ("model", "done", "done_reason", "prompt_eval_count", "eval_count", "total_duration")}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=ROOT / "fixtures" / "live_cases.jsonl")
    parser.add_argument("--model", default="gemma4:e4b")
    parser.add_argument("--url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=90)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "local-evaluation.json")
    args = parser.parse_args()
    prompt = (ROOT / "prompts" / "recovery.txt").read_text(encoding="utf-8")
    cases = [json.loads(line) for line in args.cases.read_text(encoding="utf-8").splitlines() if line.strip()]
    if args.limit:
        cases = cases[:args.limit]
    report = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "evidence_kind": "real-local-ollama-on-author-written-synthetic-cases",
              "iris_runtime_verified": False, "contest_score": None,
              "model": args.model, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
              "cases_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
              "limitation": "Small development smoke set, not held-out data or proof of general accuracy. No actual orders or external delivery.",
              "results": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    for case in cases:
        started = time.perf_counter()
        row = {"id": case["id"], "expected_action": case["expected_action"]}
        context = {key: case[key] for key in ("event", "order", "alias_map")}
        try:
            raw, metrics = call_model(args.url, args.model, prompt, context, args.timeout)
            decision = validate_decision(case["event"], case["order"], raw, case["alias_map"])
            row.update(raw_model_response=raw, runtime_metrics=metrics, decision=decision,
                       matched=(decision["action"] == case["expected_action"]), error=None)
        except (error.URLError, OSError, ValueError, KeyError, RuntimeError) as exc:
            row.update(matched=False, error=f"{type(exc).__name__}: {exc}")
        row["wall_seconds"] = round(time.perf_counter() - started, 3)
        report["results"].append(row)
        report["summary"] = {"attempted": len(report["results"]),
                             "matched": sum(r["matched"] for r in report["results"]),
                             "request_failures": sum(r["error"] is not None for r in report["results"])}
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"id": row["id"], "matched": row["matched"], "seconds": row["wall_seconds"],
                          "error": row["error"]}, ensure_ascii=False), flush=True)
    print(json.dumps(report["summary"]), flush=True)
    return 0 if all(r["matched"] for r in report["results"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
