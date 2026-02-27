import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib import request


def _post_json(url: str, payload: dict, timeout: int = 120) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url=url,
        data=data,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def _contains_any(text: str, needles: list[str]) -> bool:
    text_l = (text or "").lower()
    for n in needles:
        if n.lower() in text_l:
            return True
    return False


def _write_report(out_path: Path, report: dict) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def run_eval(base_url: str, dataset_path: Path, top_k: int, out_path: Path) -> dict:
    ds = json.loads(dataset_path.read_text(encoding="utf-8"))
    tests = ds.get("tests", [])
    collection = ds.get("collection", "kb_docs")

    results = []
    n_answer_ok = 0
    n_cite_ok = 0
    n_refusal_ok = 0
    n_refusal_cases = 0
    total_latency_ms = 0.0

    for i, t in enumerate(tests, start=1):
        qid = t["id"]
        q = t["question"]
        expected_any = t.get("expected_any", [])
        must_cite_any_file = t.get("must_cite_any_file", [])
        expect_refusal = bool(t.get("expect_refusal", False))

        payload = {"question": q, "collection": collection, "top_k": top_k}
        started = time.perf_counter()
        try:
            resp = _post_json(f"{base_url}/query", payload)
            err = None
        except Exception as e:
            resp = {}
            err = str(e)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        total_latency_ms += elapsed_ms

        answer_text = resp.get("answer_text") or resp.get("answer") or ""
        status = resp.get("status") or ""
        sources = resp.get("sources") or []
        cited_files = [str(s.get("file", "")) for s in sources]

        answer_ok = _contains_any(answer_text, expected_any) if expected_any else True
        cite_ok = any(f in must_cite_any_file for f in cited_files) if must_cite_any_file else True

        refusal_ok = None
        if expect_refusal:
            n_refusal_cases += 1
            refusal_ok = _contains_any(answer_text, ["unknown", "insufficient", "мэдэхгүй", "баттай биш"]) or _contains_any(
                status, ["needs verification", "insufficient", "мэдээлэл хүрэлцэхгүй", "баталгаажуулалт"]
            )

        if answer_ok:
            n_answer_ok += 1
        if cite_ok:
            n_cite_ok += 1
        if refusal_ok is True:
            n_refusal_ok += 1

        results.append(
            {
                "id": qid,
                "question": q,
                "latency_ms": round(elapsed_ms, 2),
                "answer_ok": answer_ok,
                "cite_ok": cite_ok,
                "refusal_ok": refusal_ok,
                "status": status,
                "cited_files": cited_files,
                "answer_text": answer_text,
                "error": err,
            }
        )

        # Save progress after each test so interruptions still leave usable output.
        running_total = len(results)
        running_summary = {
            "dataset": str(dataset_path),
            "total_tests": len(tests),
            "completed_tests": running_total,
            "answer_match_rate_so_far": round(n_answer_ok / running_total, 4),
            "citation_coverage_so_far": round(n_cite_ok / running_total, 4),
            "refusal_rate_on_expected_refusal_so_far": round(n_refusal_ok / n_refusal_cases, 4) if n_refusal_cases else None,
            "avg_latency_ms_so_far": round(total_latency_ms / running_total, 2),
        }
        running_report = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "base_url": base_url,
            "collection": collection,
            "top_k": top_k,
            "summary": running_summary,
            "results": results,
        }
        _write_report(out_path, running_report)
        print(f"[{i}/{len(tests)}] done: {qid}")

    total = len(tests) if tests else 1
    summary = {
        "dataset": str(dataset_path),
        "total_tests": len(tests),
        "answer_match_rate": round(n_answer_ok / total, 4),
        "citation_coverage": round(n_cite_ok / total, 4),
        "refusal_rate_on_expected_refusal": round(n_refusal_ok / n_refusal_cases, 4) if n_refusal_cases else None,
        "avg_latency_ms": round(total_latency_ms / total, 2),
    }

    report = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "collection": collection,
        "top_k": top_k,
        "summary": summary,
        "results": results,
    }
    _write_report(out_path, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run RAG baseline evaluation.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8090")
    parser.add_argument("--dataset", default="eval/questions.phase1.json")
    parser.add_argument("--top-k", type=int, default=4)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_out = Path("eval/reports") / f"baseline_{ts}.json"
    out_path = Path(args.out) if args.out else default_out

    report = run_eval(args.base_url, dataset_path, args.top_k, out_path)
    print("Baseline report written:", out_path)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
