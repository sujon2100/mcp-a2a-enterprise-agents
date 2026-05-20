# Research Extension — Toward Scientific Publication

Author: Md Helal Uddin
Base project: Customer Complaint Resolution Network (TDX 2026, Session 1557)

---

## Research Questions

RQ1 — Parallelism (Path 1)

What is the quantifiable latency benefit of LLM-orchestrated parallel step execution
in MCP+A2A multi-agent workflows compared to forced sequential execution?

RQ2 — Governance Effectiveness (Path 2)

How effective is gateway-level PII enforcement in multi-agent systems across
entity types and adversarial inputs, and what is its performance overhead?

---

## Experimental Design

### RQ1 — Three execution configurations

Sequential: Broker instructions force strict step-by-step ordering
File: `configs/sequential-orchestration.yaml`

Parallel (baseline): Current live implementation — steps 3+4 run independently
File: `configs/parallel-orchestration.yaml`

Max-Parallel: Steps 2+4 run concurrently after step 1; steps 3+5 chain immediately
File: `configs/max-parallel-orchestration.yaml`

Each configuration is deployed by replacing `agent-network.yaml` in the live project
and re-publishing to Anypoint Exchange. Only the `instructions:` block changes.

Protocol: 30 requests per configuration × 3 configurations = 90 total runs.
Metric captured: wall-clock latency (ms) from HTTP send to full response received.

### RQ2 — PII test suite

50 test cases across 6 PII entity types + adversarial variants.
Each case has a known expected outcome (BLOCK or PASS).
Metrics: detection rate, false positive rate, false negative rate, latency overhead.

---

## Running the experiments

### Prerequisites

```bash
cd research/benchmarks
pip3.11 install -r requirements.txt
cp ../.env.example ../.env   # fill in BROKER_URL, ANYPOINT credentials
```

### RQ1 — Latency benchmark

```bash
# Deploy sequential config first (see configs/ README), then:
python3.11 run_latency_benchmark.py --config sequential --runs 30

# Redeploy parallel config, then:
python3.11 run_latency_benchmark.py --config parallel --runs 30

# Redeploy max-parallel config, then:
python3.11 run_latency_benchmark.py --config max-parallel --runs 30
```

Results saved to `analysis/results/latency_{config}_{timestamp}.csv`

### RQ2 — PII benchmark

```bash
python3.11 run_pii_benchmark.py --runs 1   # each test case run once by default
```

Results saved to `analysis/results/pii_{timestamp}.csv`

### Analysis

```bash
python3.11 analysis/latency_analysis.py    # generates stats + plots
python3.11 analysis/pii_analysis.py        # generates detection tables + plots
python3.11 paper/results_tables.py         # generates publication-ready LaTeX tables
```

---

## Directory Structure

```
research/
├── README.md                              <- This file
├── configs/
│   ├── sequential-orchestration.yaml      <- Baseline: strict sequential instructions
│   ├── parallel-orchestration.yaml        <- Current live config (copy of real deployment)
│   └── max-parallel-orchestration.yaml    <- Extended: maximum parallelism
├── benchmarks/
│   ├── run_latency_benchmark.py           <- RQ1 test harness
│   ├── run_pii_benchmark.py               <- RQ2 test harness
│   └── requirements.txt
├── test-data/
│   ├── complaint_requests.json            <- 15 varied valid complaint inputs
│   └── pii_test_cases.json               <- 50 PII test cases (expected: BLOCK/PASS)
├── analysis/
│   ├── latency_analysis.py               <- t-tests, box plots, summary stats
│   ├── pii_analysis.py                   <- detection rates, confusion matrix, overhead
│   ├── sample_results/                   <- Pre-filled sample data for offline analysis
│   │   ├── latency_sequential.csv
│   │   ├── latency_parallel.csv
│   │   ├── latency_max_parallel.csv
│   │   └── pii_results.csv
│   └── results/                          <- Live results written here by benchmarks
└── paper/
    └── results_tables.py                 <- LaTeX table generator for publication
```
