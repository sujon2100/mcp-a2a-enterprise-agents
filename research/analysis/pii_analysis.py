"""
RQ2 — Does the PII detection policy actually work?

THE PROBLEM
-----------
The agent network uses a Flex Gateway policy called a-two-a-pii-detector
to block messages containing US Social Security Numbers. The idea is that
if a customer accidentally types their SSN in a complaint, the gateway
stops the message before the LLM ever sees it.

But I needed to verify this empirically. The key questions were:
1. Does it catch SSNs reliably? (recall)
2. Does it accidentally block legitimate complaints? (precision)
3. What about edge cases — SSNs in different formats, or hidden inside
   a longer message, or embedded in a prompt injection attempt?
4. How much does the blocking cost in terms of response time?

WHY PRECISION MATTERS AS MUCH AS RECALL
-----------------------------------------
A policy that blocks everything would have perfect recall (zero SSNs get
through) but terrible precision (it would block real customer complaints
too). For a customer service system, false positives are a real problem —
a legitimate customer saying "order number 123456789" could get blocked
if the policy is too aggressive. So I specifically designed test cases
to check that clean messages sail through.

WHAT I FOUND
------------
- Precision: 100% (zero false positives — legitimate complaints were
  never blocked)
- Recall: 87.5% (3 out of 24 SSN cases slipped through)
- The 3 misses were all format variations: undelimited digits (000111111),
  spaces instead of dashes (000 11 1111), and whitespace around dashes
  (000 - 11 - 1111). The policy regex only matches XXX-XX-XXXX exactly.
- Blocked requests returned in 64ms on average vs 382ms for passing
  requests — blocking is FASTER because the LLM never gets called.

LIMITATION
-----------
This test used 50 hand-crafted cases, not real production traffic. Real
traffic would have more variety. The format-normalisation gap is a known
limitation that could be fixed by extending the policy's regex patterns.

USAGE
-----
    python3.11 pii_analysis.py              # uses sample_results/
    python3.11 pii_analysis.py --live       # uses results/ (live data)
    python3.11 pii_analysis.py --out ~/Desktop  # custom output folder
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")   # save to file, no display window needed
import matplotlib.pyplot as plt
import seaborn as sns

HERE   = Path(__file__).parent
SAMPLE = HERE / "sample_results"
LIVE   = HERE / "results"


def load_data(use_live: bool) -> pd.DataFrame:
    """
    Loads the PII test results CSV. Each row is one test case:
    the input message, whether we expected BLOCK or PASS, what
    the gateway actually returned, and how long it took.
    """
    base    = LIVE if use_live else SAMPLE
    pattern = sorted(base.glob("pii_*.csv"))
    if not pattern:
        raise FileNotFoundError(f"No pii_*.csv found in {base}")
    return pd.read_csv(pattern[-1])


def classification_metrics(df: pd.DataFrame) -> dict:
    """
    Computes the standard confusion matrix metrics.

    TP = SSN present, policy correctly blocked it (good)
    TN = no SSN, policy correctly allowed it (good)
    FP = no SSN, policy incorrectly blocked it (bad — customer blocked unfairly)
    FN = SSN present, policy let it through (bad — PII leaked to LLM)

    Precision = of all the things we blocked, how many actually had SSNs?
    Recall    = of all the messages that had SSNs, how many did we catch?
    F1        = harmonic mean of precision and recall (overall balance score)
    """
    tp = ((df["expected"] == "BLOCK") & (df["actual"] == "BLOCK")).sum()
    tn = ((df["expected"] == "PASS")  & (df["actual"] == "PASS")).sum()
    fp = ((df["expected"] == "PASS")  & (df["actual"] == "BLOCK")).sum()
    fn = ((df["expected"] == "BLOCK") & (df["actual"] != "BLOCK")).sum()

    precision = tp / (tp + fp) * 100 if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) * 100 if (tp + fn) > 0 else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    accuracy  = (tp + tn) / len(df) * 100

    return dict(tp=int(tp), tn=int(tn), fp=int(fp), fn=int(fn),
                precision=precision, recall=recall, f1=f1, accuracy=accuracy)


def run_analysis(df: pd.DataFrame, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)

    m     = classification_metrics(df)
    total = len(df)

    # Print a readable summary to the console first
    print("\n" + "="*65)
    print("  RQ2 — PII GOVERNANCE DETECTION RESULTS")
    print("="*65)
    print(f"  Total test cases  : {total}")
    print(f"  Overall accuracy  : {m['accuracy']:.1f}%  ({m['tp']+m['tn']}/{total} correct)")
    print(f"  True  Positives   : {m['tp']:>3}  (SSNs correctly blocked)")
    print(f"  True  Negatives   : {m['tn']:>3}  (clean messages correctly passed)")
    print(f"  False Positives   : {m['fp']:>3}  (clean messages wrongly blocked)")
    print(f"  False Negatives   : {m['fn']:>3}  (SSNs that slipped through)")
    print(f"  Precision         : {m['precision']:.1f}%")
    print(f"  Recall            : {m['recall']:.1f}%")
    print(f"  F1 Score          : {m['f1']:.3f}")

    # Show the latency difference between blocked and passing requests.
    # This is important: blocking is actually FASTER because the gateway
    # short-circuits before calling the LLM. A blocked request never
    # goes through the 5-step orchestration at all.
    block_lat = df[df["actual"] == "BLOCK"]["latency_ms"]
    pass_lat  = df[df["actual"] == "PASS"]["latency_ms"]
    overhead  = block_lat.mean() - pass_lat.mean()

    print(f"\n  Blocked requests  : mean {block_lat.mean():.0f}ms")
    print(f"  Passing requests  : mean {pass_lat.mean():.0f}ms")
    print(f"  Overhead          : {overhead:.0f}ms",
          " (negative means blocking is faster than passing)")
    print("="*65)

    # Print the false negatives with detail so we know exactly what failed.
    # All three failures were format variants — the regex only matches
    # the canonical XXX-XX-XXXX pattern.
    fns = df[(df["expected"] == "BLOCK") & (df["actual"] != "BLOCK")]
    if not fns.empty:
        print(f"\n  False Negatives — {len(fns)} SSN formats the policy missed:")
        for _, row in fns.iterrows():
            print(f"    {row['case_id']:<22} [{row['category']}]  {row['note'][:60]}")

    # Break accuracy down by test category so we can see WHERE the
    # policy works well and where it has gaps
    cat_rows = []
    for cat, grp in df.groupby("category"):
        n    = len(grp)
        ok   = grp["match"].sum()
        rate = ok / n * 100
        exp_block = (grp["expected"] == "BLOCK").sum()
        exp_pass  = (grp["expected"] == "PASS").sum()
        cat_rows.append({
            "Category":      cat,
            "n":             n,
            "Correct":       int(ok),
            "Accuracy_%":    round(rate, 1),
            "Expected_BLOCK": int(exp_block),
            "Expected_PASS":  int(exp_pass)
        })

    cat_df = pd.DataFrame(cat_rows).sort_values("Accuracy_%")
    cat_df.to_csv(out_dir / "pii_category_accuracy.csv", index=False)

    print(f"\n  Accuracy by test category:")
    print(f"  {'Category':<30} {'n':>4}  {'Correct':>7}  {'Accuracy':>9}")
    print(f"  {'-'*30} {'-'*4}  {'-'*7}  {'-'*9}")
    for _, row in cat_df.sort_values("Category").iterrows():
        print(f"  {row['Category']:<30} {row['n']:>4}  {row['Correct']:>7}  {row['Accuracy_%']:>8.0f}%")

    # Save a one-row metrics summary CSV — useful for importing into reports
    metrics_row = {
        **m,
        "latency_block_mean_ms": round(block_lat.mean(), 1),
        "latency_pass_mean_ms":  round(pass_lat.mean(), 1),
        "latency_overhead_ms":   round(overhead, 1),
        "total_cases":           total
    }
    pd.DataFrame([metrics_row]).to_csv(out_dir / "pii_metrics_summary.csv", index=False)

    # Chart 1: Confusion matrix heatmap
    # A confusion matrix is the clearest way to show TP/TN/FP/FN
    # all at once. Blue intensity shows count — darker = more cases.
    cm = np.array([[m["tp"], m["fn"]],
                   [m["fp"], m["tn"]]])

    fig, ax = plt.subplots(figsize=(6, 5))
    sns.heatmap(
        cm, annot=True, fmt="d", cmap="Blues",
        xticklabels=["BLOCK (predicted)", "PASS (predicted)"],
        yticklabels=["BLOCK (actual)", "PASS (actual)"],
        linewidths=0.5, ax=ax,
        annot_kws={"size": 16, "weight": "bold"}
    )
    ax.set_title(
        "PII Detection Confusion Matrix\n"
        "a-two-a-pii-detector v1.0.1 — US SSN, n=50 test cases",
        fontsize=11, fontweight="bold"
    )
    ax.set_xlabel("Predicted Outcome", fontsize=10)
    ax.set_ylabel("True Outcome", fontsize=10)
    ax.text(
        0.5, -0.18,
        f"Precision: {m['precision']:.1f}%   Recall: {m['recall']:.1f}%   F1: {m['f1']:.3f}",
        transform=ax.transAxes, ha="center", fontsize=9,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#e8f4fd", edgecolor="#aac8e0")
    )
    plt.tight_layout()
    cm_path = out_dir / "pii_confusion_matrix.png"
    plt.savefig(cm_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\n  Confusion matrix chart saved to {cm_path}")

    # Chart 2: Accuracy bar chart broken down by category
    # Red bars = categories with failures, green = perfect categories.
    # This makes it immediately obvious that only the format-variant
    # categories had any misses.
    plot_df = cat_df.sort_values("Accuracy_%")
    colors  = ["#d62728" if v < 100 else "#2ca02c" for v in plot_df["Accuracy_%"]]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(plot_df["Category"], plot_df["Accuracy_%"],
                   color=colors, edgecolor="white", height=0.6)

    for bar, val in zip(bars, plot_df["Accuracy_%"]):
        ax.text(min(val + 1, 101), bar.get_y() + bar.get_height() / 2,
                f"{val:.0f}%", va="center", fontsize=9)

    ax.set_xlim(0, 115)
    ax.set_xlabel("Detection Accuracy (%)", fontsize=11)
    ax.set_title(
        "PII Detection Accuracy by Test Category\n"
        "a-two-a-pii-detector v1.0.1 — Flex Gateway enforcement",
        fontsize=11, fontweight="bold"
    )
    ax.axvline(100, color="gray", linestyle="--", alpha=0.5, linewidth=1)
    ax.grid(axis="x", linestyle="--", alpha=0.4)
    plt.tight_layout()
    cat_path = out_dir / "pii_category_accuracy.png"
    plt.savefig(cat_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Category accuracy chart saved to {cat_path}")

    # Chart 3: Latency histogram comparing BLOCK vs PASS response times.
    # This visually confirms that blocked requests are faster — the red
    # distribution is entirely to the left of the blue distribution.
    fig, ax = plt.subplots(figsize=(8, 4.5))
    for outcome, color, label in [
        ("BLOCK", "#d62728", "BLOCK (401 Rejected)"),
        ("PASS",  "#1f77b4", "PASS (200 OK)")
    ]:
        vals = df[df["actual"] == outcome]["latency_ms"]
        ax.hist(vals, bins=15, alpha=0.65, color=color, label=label, edgecolor="white")
        ax.axvline(vals.mean(), color=color, linestyle="--", linewidth=1.5,
                   label=f"{label} mean: {vals.mean():.0f}ms")

    ax.set_xlabel("Latency (ms)", fontsize=11)
    ax.set_ylabel("Frequency", fontsize=11)
    ax.set_title(
        "Response Time: BLOCK vs PASS\n"
        "Gateway blocks at ingress — no LLM call made for rejected requests",
        fontsize=11, fontweight="bold"
    )
    ax.legend(fontsize=9)
    ax.grid(axis="y", linestyle="--", alpha=0.4)
    plt.tight_layout()
    lat_path = out_dir / "pii_latency_distribution.png"
    plt.savefig(lat_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Latency distribution chart saved to {lat_path}")
    print(f"  Metrics summary saved to {out_dir / 'pii_metrics_summary.csv'}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Analyse PII detection effectiveness of the Flex Gateway policy (RQ2)"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Use live benchmark results in results/ instead of the sample data"
    )
    parser.add_argument(
        "--out", type=str, default=None,
        help="Where to save charts and CSVs (default: same folder as input data)"
    )
    args = parser.parse_args()

    df      = load_data(args.live)
    out_dir = Path(args.out) if args.out else (LIVE if args.live else SAMPLE)
    run_analysis(df, out_dir)
