"""
RQ1 Latency Benchmark — sends real requests to the agent network and records response times.

THE PROBLEM
-----------
I needed actual latency measurements from the live system — not simulations.
The only way to test whether parallel orchestration is faster than sequential
is to deploy each configuration to Anypoint and measure how long requests take
from the moment they're sent to the moment the full response arrives.

HOW THIS WORKS
--------------
This script takes one config name (sequential / parallel / max-parallel),
sends N requests to the live broker URL, and writes each result to a CSV.
You then run latency_analysis.py on that CSV to get the statistics.

The three configs differ only in their instructions block in agent-network.yaml:
- sequential:    each step waits for the previous one to finish
- parallel:      steps 3 and 4 run at the same time (lab config)
- max-parallel:  as many steps as possible run concurrently

To switch configs, you deploy the matching YAML from research/configs/ to
Anypoint, then run this script pointing at the new deployment.

IMPORTANT NOTES
---------------
- Set BROKER_URL in your .env file before running. The script will error
  if it's not set — this is intentional so you don't accidentally benchmark
  against the wrong environment.
- The script waits 2 seconds between requests by default. This gives the LLM
  rate limiter time to reset and prevents requests from queuing up. You can
  change this with --delay.
- Only HTTP 200 responses are counted as successful. Timeouts and errors are
  recorded but excluded from the statistical analysis.

PREREQUISITES
-------------
1. Deploy the config you want to test from research/configs/ to Anypoint
2. Set BROKER_URL in the .env file at the project root
3. pip install -r requirements.txt

USAGE
-----
    python3.11 run_latency_benchmark.py --config parallel --runs 30
    python3.11 run_latency_benchmark.py --config sequential --runs 30
    python3.11 run_latency_benchmark.py --config max-parallel --runs 30

OUTPUT
------
    research/analysis/results/latency_{config}_{timestamp}.csv
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

ROOT     = Path(__file__).resolve().parents[2]   # project root (mcp-project/)
RESULTS  = ROOT / "research" / "analysis" / "results"
TESTDATA = ROOT / "research" / "test-data" / "complaint_requests.json"

load_dotenv(ROOT / ".env")

BROKER_URL = os.getenv("BROKER_URL", "").rstrip("/")


def build_request(complaint_text: str, run_id: str) -> dict:
    """
    Wraps a plain-text complaint in the A2A JSON-RPC 2.0 envelope.
    This is the exact format the broker expects — the method is
    always "message/send" and the text goes inside params.message.parts.

    run_id is used as both the JSON-RPC id and the sessionId so we can
    match results back to specific runs in the CSV.
    """
    return {
        "jsonrpc": "2.0",
        "id":        run_id,
        "sessionId": run_id,
        "method":    "message/send",
        "params": {
            "message": {
                "messageId": str(uuid.uuid4()),
                "role":      "user",
                "kind":      "message",
                "parts": [
                    {"kind": "text", "text": complaint_text}
                ]
            }
        }
    }


def load_complaints() -> list:
    """
    Loads the complaint texts to rotate through during the benchmark.
    Using a variety of customers and orders (CUST001-003, ORD001-005)
    prevents the LLM or backend from caching responses, which would
    make the latency measurements artificially low.

    Falls back to a minimal built-in set if the JSON file doesn't exist.
    """
    if not TESTDATA.exists():
        return [
            "I am customer CUST001. I would like a refund for ORD001",
            "I am customer CUST002. I would like a refund for ORD002",
            "I am customer CUST003. I would like a refund for ORD003",
        ]
    with open(TESTDATA) as f:
        data = json.load(f)
    return [item["text"] for item in data["requests"]]


def run_benchmark(config_name: str, n_runs: int, delay_between: float = 2.0) -> list:
    """
    Runs the benchmark: sends n_runs requests and records the latency of each.

    Latency is measured wall-clock time from the moment the POST is sent to
    the moment the full response is received. This includes:
    - Network round-trip to the Flex Gateway
    - Policy evaluation (PII check)
    - LLM orchestration across all 5 steps
    - All MCP and A2A calls to the backend

    For the sequential config, steps run one after another so this is the
    true total time. For parallel configs, steps 3+4 overlap, which is
    why the total time is shorter even though the same work is done.
    """
    if not BROKER_URL:
        sys.exit("BROKER_URL is not set in .env — update it before running the benchmark.")

    complaints = load_complaints()
    results    = []

    print(f"\n{'='*60}")
    print(f"  Config : {config_name}")
    print(f"  Runs   : {n_runs}")
    print(f"  URL    : {BROKER_URL}")
    print(f"  Delay  : {delay_between}s between requests")
    print(f"{'='*60}\n")

    for i in range(1, n_runs + 1):
        # Rotate through complaint texts to avoid any caching effects
        text   = complaints[(i - 1) % len(complaints)]
        run_id = f"{config_name}-run-{i:03d}"
        body   = build_request(text, run_id)

        print(f"  [{i:02d}/{n_runs}] \"{text[:55]}...\"", end=" ", flush=True)

        t_start = time.perf_counter()
        try:
            resp = requests.post(
                BROKER_URL,
                json=body,
                headers={"Content-Type": "application/json"},
                timeout=120   # 2 minutes — LLM orchestration can be slow
            )
            t_end      = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000, 2)
            status     = resp.status_code

            try:
                resp_text = str(resp.json())[:200]
            except Exception:
                resp_text = resp.text[:200]

            print(f"  {status}  {latency_ms:>8.0f} ms")

        except requests.exceptions.Timeout:
            t_end      = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000, 2)
            status     = 0
            resp_text  = "TIMEOUT"
            print(f"  TIMEOUT  {latency_ms:>8.0f} ms")

        except requests.exceptions.RequestException as e:
            t_end      = time.perf_counter()
            latency_ms = round((t_end - t_start) * 1000, 2)
            status     = -1
            resp_text  = f"ERROR: {e}"
            print(f"  ERROR    {latency_ms:>8.0f} ms")

        results.append({
            "run":        i,
            "config":     config_name,
            "complaint":  text[:80],
            "status":     status,
            "latency_ms": latency_ms,
            "success":    1 if status == 200 else 0,
            "timestamp":  datetime.utcnow().isoformat(),
            "response":   resp_text,
        })

        # Wait between requests to avoid hitting LLM rate limits
        if i < n_runs:
            time.sleep(delay_between)

    return results


def save_results(results: list, config_name: str) -> Path:
    """
    Writes the results to a timestamped CSV in research/analysis/results/.
    The timestamp in the filename means you can run the benchmark multiple
    times without overwriting previous data.
    """
    RESULTS.mkdir(parents=True, exist_ok=True)
    ts       = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out_file = RESULTS / f"latency_{config_name}_{ts}.csv"

    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=results[0].keys())
        writer.writeheader()
        writer.writerows(results)

    return out_file


def print_summary(results: list, config_name: str):
    """
    Prints a quick summary table after the benchmark finishes so you
    can see the results immediately without running the analysis script.
    """
    latencies = [r["latency_ms"] for r in results if r["status"] == 200]
    errors    = sum(1 for r in results if r["status"] != 200)

    if not latencies:
        print("\n  No successful runs — check BROKER_URL and confirm the deployment is active.")
        return

    import statistics
    print(f"\n{'='*60}")
    print(f"  RESULTS — {config_name.upper()}")
    print(f"{'='*60}")
    print(f"  Successful  : {len(latencies)} of {len(results)} runs")
    print(f"  Errors      : {errors}")
    print(f"  Mean        : {statistics.mean(latencies):>8.0f} ms")
    print(f"  Median      : {statistics.median(latencies):>8.0f} ms")
    print(f"  Std dev     : {statistics.stdev(latencies):>8.0f} ms")
    print(f"  Min / Max   : {min(latencies):>8.0f} / {max(latencies):.0f} ms")
    print(f"  p95         : {sorted(latencies)[int(len(latencies)*0.95)]:>8.0f} ms")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Measure end-to-end latency for each orchestration configuration (RQ1)"
    )
    parser.add_argument(
        "--config", required=True,
        choices=["sequential", "parallel", "max-parallel"],
        help="Which config is currently deployed to Anypoint"
    )
    parser.add_argument(
        "--runs", type=int, default=30,
        help="Number of requests to send (default: 30)"
    )
    parser.add_argument(
        "--delay", type=float, default=2.0,
        help="Seconds to wait between requests to avoid rate limiting (default: 2.0)"
    )
    args = parser.parse_args()

    results  = run_benchmark(args.config, args.runs, args.delay)
    out_file = save_results(results, args.config)
    print_summary(results, args.config)
    print(f"  Raw results saved to {out_file}\n")
    print(f"  Run: python3.11 research/analysis/latency_analysis.py --live")
    print(f"  to compute statistics and generate charts.\n")
