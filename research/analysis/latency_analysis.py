"""
RQ1 — Does running agents in parallel actually make things faster?

THE PROBLEM
-----------
When I built the agent network, I noticed the instructions told the LLM
it could run steps 3 and 4 at the same time (generate shipping label +
process refund in parallel). I wanted to know: does this actually matter?
How much faster is it really?

WHY I COULDN'T JUST USE AN AVERAGE
------------------------------------
LLM response times don't follow a normal bell curve. Sometimes Gemini
responds in 18 seconds, sometimes in 32 seconds. The distribution has
a long tail. Because of this, a standard t-test is technically wrong
here — it assumes normally distributed data. So I used the
Kruskal-Wallis test instead (a non-parametric version of ANOVA), and
Mann-Whitney U tests for comparing pairs. These work on ranked data and
make no assumptions about the shape of the distribution.

WHAT THIS SCRIPT DOES
----------------------
1. Loads the CSV files from the latency benchmark runs
2. Computes basic statistics (mean, median, standard deviation, p95)
3. Runs a Kruskal-Wallis test to check if the three configs are
   different at all (overall significance)
4. Runs pairwise Mann-Whitney U tests to compare each config against
   the others, with Bonferroni correction for multiple comparisons
5. Computes Cohen's d to measure how large the effect is
6. Produces a box plot showing the spread of latencies per config

LIMITATIONS
-----------
- The sample data in sample_results/ is synthetic but calibrated to
  match the real run (20.81s observed during Exercise 5 at TDX 2026).
  If you want real numbers, run the benchmark against the live Anypoint
  environment using the --live flag.
- Cohen's d values in the synthetic data are very large (7.84, 13.95)
  because synthetic data has low variance by design. Real LLM inference
  has much higher variance, so the effect sizes would be more moderate
  in production — but the direction (parallel is faster) would hold.
- 30 trials per config is enough for the statistics but not enough to
  capture rare edge cases like cold starts or rate-limit retries.

USAGE
-----
    python3.11 latency_analysis.py              # uses sample_results/
    python3.11 latency_analysis.py --live       # uses results/ (live data)
    python3.11 latency_analysis.py --out ~/Desktop  # custom output folder
"""

import argparse
import os
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # don't try to open a window — just save the file
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

HERE    = Path(__file__).parent
SAMPLE  = HERE / "sample_results"
LIVE    = HERE / "results"


def load_data(use_live: bool) -> pd.DataFrame:
    """
    Loads the three latency CSV files (sequential, parallel, max-parallel).
    Each CSV was produced by run_latency_benchmark.py — one row per request.
    Falls back to sample_results/ if no live data exists.
    """
    base = LIVE if use_live else SAMPLE
    dfs  = []

    # Try both naming conventions (max-parallel and max_parallel)
    for config in ["sequential", "parallel", "max-parallel", "max_parallel"]:
        pattern = list(base.glob(f"latency_{config}*.csv"))
        if pattern:
            df = pd.read_csv(pattern[-1])
            df["config"] = config.replace("max_parallel", "max-parallel")
            dfs.append(df)

    if not dfs:
        raise FileNotFoundError(f"No latency CSVs found in {base}")

    return pd.concat(dfs, ignore_index=True)


def cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """
    Measures how large the difference between two groups is,
    in units of standard deviations. This tells you whether a
    statistically significant difference is also practically meaningful.

    Cohen's conventions: 0.2 = small, 0.5 = medium, 0.8 = large.
    Values above 0.8 mean the difference is clearly visible in the data.
    """
    pooled_std = np.sqrt((np.std(a, ddof=1)**2 + np.std(b, ddof=1)**2) / 2)
    return (np.mean(a) - np.mean(b)) / pooled_std if pooled_std > 0 else 0.0


def interpret_d(d: float) -> str:
    """Translates a Cohen's d number into plain English."""
    d = abs(d)
    if d < 0.2: return "negligible"
    if d < 0.5: return "small"
    if d < 0.8: return "medium"
    return "large"


def run_analysis(df: pd.DataFrame, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    # Only count requests that actually succeeded (HTTP 200)
    # A timeout or error would skew the latency numbers unfairly
    df = df[df["success"] == 1].copy()

    configs = ["sequential", "parallel", "max-parallel"]
    config_labels = {
        "sequential":   "Sequential",
        "parallel":     "Parallel\n(baseline)",
        "max-parallel": "Max-Parallel"
    }
    # Red for slow, blue for medium, green for fast
    palette = {
        "sequential":   "#d62728",
        "parallel":     "#1f77b4",
        "max-parallel": "#2ca02c"
    }

    groups = {
        c: df[df["config"] == c]["latency_ms"].values
        for c in configs if c in df["config"].values
    }

    # Step 1: Basic descriptive stats for each config
    # This tells us the typical latency and how consistent it is
    rows = []
    for cfg, vals in groups.items():
        rows.append({
            "Configuration": cfg,
            "n":             len(vals),
            "Mean (ms)":     round(np.mean(vals), 1),
            "Median (ms)":   round(np.median(vals), 1),
            "Std Dev (ms)":  round(np.std(vals, ddof=1), 1),
            "Min (ms)":      round(np.min(vals), 1),
            "Max (ms)":      round(np.max(vals), 1),
            "p95 (ms)":      round(np.percentile(vals, 95), 1),
        })
    stats_df = pd.DataFrame(rows)
    stats_df.to_csv(out_dir / "latency_summary_stats.csv", index=False)

    print("\n" + "="*70)
    print("  RQ1 — LATENCY SUMMARY STATISTICS")
    print("="*70)
    print(stats_df.to_string(index=False))

    # Step 2: Kruskal-Wallis test
    # This answers: "are these three groups different at all?"
    # It's the non-parametric equivalent of a one-way ANOVA.
    # H is the test statistic; p < 0.05 means the groups differ significantly.
    group_vals = list(groups.values())
    if len(group_vals) >= 2:
        kw_stat, kw_p = stats.kruskal(*group_vals)
        print(f"\n  Kruskal-Wallis H={kw_stat:.3f}  p={kw_p:.4f}",
              "  significant" if kw_p < 0.05 else "  (not significant)")

    # Step 3: Pairwise Mann-Whitney U tests
    # Now we know the groups differ overall, we compare each pair.
    # Bonferroni correction: with 3 pairs, we divide the 0.05 threshold
    # by 3, giving alpha = 0.017. This prevents false positives from
    # testing the same data multiple times.
    pairs = [
        ("sequential", "parallel"),
        ("parallel", "max-parallel"),
        ("sequential", "max-parallel")
    ]
    print("\n  Pairwise Mann-Whitney U tests (Bonferroni corrected alpha=0.017):")
    print(f"  {'Pair':<40} {'U-stat':>8}  {'p-value':>10}  {'Cohen d':>8}  Effect")
    print(f"  {'-'*40} {'-'*8}  {'-'*10}  {'-'*8}  {'-'*10}")

    pair_rows = []
    for a, b in pairs:
        if a not in groups or b not in groups:
            continue
        u_stat, p_val = stats.mannwhitneyu(groups[a], groups[b], alternative="two-sided")
        d   = cohens_d(groups[a], groups[b])
        eff = interpret_d(d)
        sig = "significant" if p_val < 0.017 else ("marginal" if p_val < 0.05 else "ns")
        print(f"  {a} vs {b:<28} {u_stat:>8.1f}  {p_val:>10.4f}  {d:>8.3f}  {eff} ({sig})")
        pair_rows.append({
            "Pair":    f"{a} vs {b}",
            "U":       u_stat,
            "p":       p_val,
            "Cohen_d": round(d, 3),
            "Effect":  eff,
            "Sig":     sig
        })

    pd.DataFrame(pair_rows).to_csv(out_dir / "latency_pairwise_tests.csv", index=False)

    # Step 4: Show the actual latency reduction in plain percentage terms
    # This is what you'd quote in a presentation or paper
    if "sequential" in groups and "parallel" in groups:
        seq_mean  = np.mean(groups["sequential"])
        par_mean  = np.mean(groups["parallel"])
        reduction = (seq_mean - par_mean) / seq_mean * 100
        print(f"\n  Parallel vs Sequential reduction : {reduction:.1f}%  "
              f"({seq_mean:.0f}ms to {par_mean:.0f}ms)")

    if "sequential" in groups and "max-parallel" in groups:
        seq_mean  = np.mean(groups["sequential"])
        mp_mean   = np.mean(groups["max-parallel"])
        reduction = (seq_mean - mp_mean) / seq_mean * 100
        print(f"  Max-Parallel vs Sequential      : {reduction:.1f}%  "
              f"({seq_mean:.0f}ms to {mp_mean:.0f}ms)")

    # Step 5: Box plot
    # Box plots are ideal for LLM latency because they show the
    # full spread (min/max), the typical range (box = 25th-75th percentile),
    # and the median — all in one chart. Individual dots show each trial.
    fig, ax = plt.subplots(figsize=(9, 5.5))
    plot_df = df[df["config"].isin(configs)].copy()
    plot_df["Config"] = plot_df["config"].map(config_labels)

    order = [config_labels[c] for c in configs if c in groups]
    sns.boxplot(
        data=plot_df, x="Config", y="latency_ms", order=order,
        palette={config_labels[c]: palette[c] for c in palette},
        width=0.5, linewidth=1.5,
        flierprops=dict(marker="o", markersize=4),
        ax=ax
    )
    # Overlay individual data points so reviewers can see the raw data
    sns.stripplot(
        data=plot_df, x="Config", y="latency_ms", order=order,
        palette={config_labels[c]: palette[c] for c in palette},
        size=4, alpha=0.4, jitter=True, ax=ax
    )

    ax.set_title(
        "End-to-End Latency by Orchestration Configuration\n"
        "Customer Complaint Resolution — MuleSoft Agent Fabric (n=30 per config)",
        fontsize=12, fontweight="bold"
    )
    ax.set_xlabel("Orchestration Configuration", fontsize=11)
    ax.set_ylabel("Latency (ms)", fontsize=11)
    ax.grid(axis="y", linestyle="--", alpha=0.5)

    # Label each box with the mean so it's easy to read at a glance
    for i, cfg in enumerate([c for c in configs if c in groups]):
        mean_val = np.mean(groups[cfg])
        ax.text(i, mean_val + 200, f"mean={mean_val:.0f}ms",
                ha="center", va="bottom", fontsize=9, color="black", fontweight="bold")

    plt.tight_layout()
    plot_path = out_dir / "latency_boxplot.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n  Box plot saved to {plot_path}")
    print(f"  Summary stats saved to {out_dir / 'latency_summary_stats.csv'}")
    print(f"  Pairwise tests saved to {out_dir / 'latency_pairwise_tests.csv'}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyse latency across three agent orchestration configs (RQ1)"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Use live benchmark results in results/ instead of the sample data"
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="Where to save output files (default: same folder as the input CSVs)"
    )
    args = parser.parse_args()

    df      = load_data(args.live)
    out_dir = Path(args.out) if args.out else (LIVE if args.live else SAMPLE)
    run_analysis(df, out_dir)
