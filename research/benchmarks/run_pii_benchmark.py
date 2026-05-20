"""
RQ2 — PII Governance Effectiveness Benchmark
=============================================
Runs the full PII test suite against the live broker endpoint.
Records: expected outcome, actual HTTP status, latency, match.

Usage:
    python3.11 run_pii_benchmark.py
    python3.11 run_pii_benchmark.py --delay 1.5

Output:
    analysis/results/pii_{timestamp}.csv
    Console: detection rate, false positive rate, false negative rate per category
"""

import argparse
import csv
import json
import os
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT      = Path(__file__).resolve().parents[2]
RESULTS   = ROOT / "research" / "analysis" / "results"
TESTCASES = ROOT / "research" / "test-data" / "pii_test_cases.json"

load_dotenv(ROOT / ".env")
BROKER_URL = os.getenv("BROKER_URL", "").rstrip("/")


def build_request(text: str, case_id: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id":        case_id,
        "sessionId": case_id,
        "method":    "message/send",
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role":      "user",
                "kind":      "message",
                "parts":     [{"kind": "text", "text": text}]
            }
        }
    }


def outcome_from_status(status_code: int) -> str:
    """Map HTTP status to BLOCK or PASS for comparison with expected."""
    if status_code == 401:
        return "BLOCK"
    elif status_code == 200:
        return "PASS"
    else:
        return f"ERROR_{status_code}"


def run_pii_benchmark(delay: float = 1.5) -> list[dict]:
    if not BROKER_URL:
        sys.exit("ERROR: BROKER_URL not set in .env")

    with open(TESTCASES) as f:
        suite = json.load(f)

    cases   = suite["test_cases"]
    results = []

    print(f"\n{'='*70}")
    print(f"  PII Governance Benchmark — {len(cases)} test cases")
    print(f"  Target : {BROKER_URL}")
    print(f"{'='*70}")
    print(f"  {'ID':<22} {'Cat':<30} {'Exp':<6} {'Got':<6} {'Lat(ms)':>8}  {'Match'}")
    print(f"  {'-'*22} {'-'*30} {'-'*6} {'-'*6} {'-'*8}  {'-'*5}")

    for case in cases:
        case_id  = case["id"]
        text     = case["text"]
        expected = case["expected"]
        category = case["category"]

        body = build_request(text, case_id)

        t_start = time.perf_counter()
        try:
            resp       = requests.post(
                BROKER_URL,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=60
            )
            t_end      = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000, 2)
            actual     = outcome_from_status(resp.status_code)
            http_status= resp.status_code

        except requests.exceptions.Timeout:
            t_end      = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000, 2)
            actual     = "TIMEOUT"
            http_status= 0

        except requests.exceptions.RequestException as e:
            t_end      = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000, 2)
            actual     = f"ERROR"
            http_status= -1

        match   = (actual == expected)
        symbol  = "PASS" if match else "FAIL"

        print(f"  {case_id:<22} {category:<30} {expected:<6} {actual:<6} {latency_ms:>8.0f}  {symbol}")

        results.append({
            "case_id":     case_id,
            "category":    category,
            "entity":      case.get("entity", ""),
            "expected":    expected,
            "actual":      actual,
            "http_status": http_status,
            "match":       1 if match else 0,
            "latency_ms":  latency_ms,
            "text_len":    len(text),
            "note":        case.get("note", ""),
            "timestamp":   datetime.utcnow().isoformat(),
        })

        time.sleep(delay)

    return results


def save_results(results: list[dict]) -> Path:
    RESULTS.mkdir(parents=True, exist_ok=True)
    ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS / f"pii_{ts}.csv"
    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)
    return out_file


def print_summary(results: list[dict]):
    from collections import defaultdict

    # Overall
    total    = len(results)
    correct  = sum(r["match"] for r in results)
    accuracy = correct / total * 100

    # True positives / negatives / FP / FN
    tp = sum(1 for r in results if r["expected"] == "BLOCK" and r["actual"] == "BLOCK")
    tn = sum(1 for r in results if r["expected"] == "PASS"  and r["actual"] == "PASS")
    fp = sum(1 for r in results if r["expected"] == "PASS"  and r["actual"] == "BLOCK")
    fn = sum(1 for r in results if r["expected"] == "BLOCK" and r["actual"] != "BLOCK")

    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0
    recall    = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    # Latency by outcome
    block_lat = [r["latency_ms"] for r in results if r["actual"] == "BLOCK"]
    pass_lat  = [r["latency_ms"] for r in results if r["actual"] == "PASS"]

    import statistics
    print(f"\n{'='*60}")
    print("  PII DETECTION SUMMARY")
    print(f"{'='*60}")
    print(f"  Total cases    : {total}")
    print(f"  Correct        : {correct}  ({accuracy:.1f}%)")
    print(f"  True Positives : {tp}   (SSN correctly blocked)")
    print(f"  True Negatives : {tn}   (clean messages correctly passed)")
    print(f"  False Positives: {fp}   (clean messages incorrectly blocked)")
    print(f"  False Negatives: {fn}   (SSN messages incorrectly passed)")
    print(f"  Precision      : {precision:.1f}%")
    print(f"  Recall         : {recall:.1f}%")
    print(f"  F1 Score       : {f1:.3f}")
    print(f"{'='*60}")
    if block_lat:
        print(f"  Latency (BLOCK): mean {statistics.mean(block_lat):.0f}ms  "
              f"median {statistics.median(block_lat):.0f}ms")
    if pass_lat:
        print(f"  Latency (PASS) : mean {statistics.mean(pass_lat):.0f}ms  "
              f"median {statistics.median(pass_lat):.0f}ms")
    overhead = statistics.mean(block_lat) - statistics.mean(pass_lat) if block_lat and pass_lat else 0
    print(f"  Policy overhead: ~{overhead:.0f}ms  "
          "(negative = policy blocks faster than LLM responds)")
    print(f"{'='*60}\n")

    # Per-category breakdown
    by_cat = defaultdict(list)
    for r in results:
        by_cat[r["category"]].append(r)

    print("  Category breakdown:")
    print(f"  {'Category':<35} {'Cases':>5}  {'Correct':>7}  {'Rate':>6}")
    print(f"  {'-'*35} {'-'*5}  {'-'*7}  {'-'*6}")
    for cat, rows in sorted(by_cat.items()):
        n    = len(rows)
        ok   = sum(r["match"] for r in rows)
        rate = ok / n * 100
        print(f"  {cat:<35} {n:>5}  {ok:>7}  {rate:>5.0f}%")
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RQ2 PII Governance Benchmark")
    parser.add_argument("--delay", type=float, default=1.5,
                        help="Seconds between requests (default: 1.5)")
    args = parser.parse_args()

    results  = run_pii_benchmark(args.delay)
    out_file = save_results(results)
    print_summary(results)
    print(f"  Results saved → {out_file}\n")
