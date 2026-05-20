"""
Publication Results Tables Generator
=====================================
Reads analysis CSVs and generates IEEE-style LaTeX tables for the paper.

Tables produced:
  Table I  — RQ1 Latency Summary Statistics (mean, median, std, p95)
  Table II — RQ1 Pairwise Statistical Tests (Mann-Whitney U + Cohen's d)
  Table III— RQ2 PII Detection Metrics (precision, recall, F1 per category)
  Table IV — RQ2 Gateway Enforcement Latency Overhead

Usage:
    python3.11 results_tables.py
    python3.11 results_tables.py --live   # pull from results/ not sample_results/
    python3.11 results_tables.py --out ./  # write .tex files to current directory
"""

import argparse
import textwrap
from pathlib import Path

import pandas as pd
import numpy as np

HERE    = Path(__file__).parent.parent       # research/
SAMPLE  = HERE / "analysis" / "sample_results"
LIVE    = HERE / "analysis" / "results"


# LaTeX helpers

def tex_table(caption: str, label: str, header: list[str],
              rows: list[list], col_fmt: str) -> str:
    col_sep = " & "
    row_sep = " \\\\\n"
    hline   = "\\hline\n"
    header_line = col_sep.join(f"\\textbf{{{h}}}" for h in header) + row_sep

    body_lines = []
    for row in rows:
        body_lines.append(col_sep.join(str(c) for c in row) + " \\\\")

    body = "\n".join(body_lines)

    return textwrap.dedent(f"""
        \\begin{{table}}[t]
        \\centering
        \\caption{{{caption}}}
        \\label{{{label}}}
        \\begin{{tabular}}{{{col_fmt}}}
        \\hline
        {header_line}\\hline
        {body}
        \\hline
        \\end{{tabular}}
        \\end{{table}}
    """).strip()


def sig_marker(sig: str) -> str:
    if sig == "***": return "$^{***}$"
    if sig == "*":   return "$^{*}$"
    return "ns"


# Table I — RQ1 Latency Summary

def table_rq1_latency(base: Path) -> str:
    path = base / "latency_summary_stats.csv"
    if not path.exists():
        # Derive from raw CSVs
        dfs = []
        for cfg in ["sequential", "parallel", "max-parallel", "max_parallel"]:
            for f in base.glob(f"latency_{cfg}*.csv"):
                df = pd.read_csv(f)
                df["config"] = cfg.replace("max_parallel", "max-parallel")
                dfs.append(df)
        if not dfs:
            raise FileNotFoundError(f"No latency CSVs in {base}")
        full = pd.concat(dfs, ignore_index=True)
        full = full[full["success"] == 1]
        rows_out = []
        for cfg in ["sequential", "parallel", "max-parallel"]:
            vals = full[full["config"] == cfg]["latency_ms"].values
            if len(vals) == 0:
                continue
            rows_out.append({
                "Configuration": cfg,
                "n": len(vals),
                "Mean (ms)": round(np.mean(vals), 1),
                "Median (ms)": round(np.median(vals), 1),
                "Std Dev (ms)": round(np.std(vals, ddof=1), 1),
                "p95 (ms)": round(np.percentile(vals, 95), 1),
            })
        stats = pd.DataFrame(rows_out)
    else:
        stats = pd.read_csv(path)

    label_map = {"sequential": "Sequential", "parallel": "Parallel",
                 "max-parallel": "Max-Parallel"}

    rows = []
    for _, r in stats.iterrows():
        cfg = r.get("Configuration", r.get("config", ""))
        rows.append([
            label_map.get(cfg, cfg),
            int(r.get("n", r.get("n", 0))),
            f"{r.get('Mean (ms)', r.get('mean_ms', 0)):.1f}",
            f"{r.get('Median (ms)', r.get('median_ms', 0)):.1f}",
            f"{r.get('Std Dev (ms)', r.get('std_ms', 0)):.1f}",
            f"{r.get('p95 (ms)', r.get('p95_ms', 0)):.1f}",
        ])

    return tex_table(
        caption="RQ1: End-to-End Latency Summary Statistics by Orchestration Configuration "
                "(Customer Complaint Resolution, MuleSoft Agent Fabric)",
        label="tab:rq1_latency",
        header=["Configuration", "$n$", "Mean (ms)", "Median (ms)", "Std Dev (ms)", "p95 (ms)"],
        rows=rows,
        col_fmt="lccccc"
    )


# Table II — RQ1 Pairwise Tests

def table_rq1_pairwise(base: Path) -> str:
    path = base / "latency_pairwise_tests.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path} — run latency_analysis.py first")

    pw = pd.read_csv(path)
    rows = []
    for _, r in pw.iterrows():
        rows.append([
            r["Pair"].replace("sequential", "Seq").replace("parallel", "Par")
                     .replace("max-parallel", "Max-Par"),
            f"{r['U']:.1f}",
            f"{r['p']:.4f}",
            f"{r['Cohen_d']:.3f}",
            r["Effect"].capitalize(),
            sig_marker(r["Sig"]),
        ])

    return tex_table(
        caption="RQ1: Pairwise Mann-Whitney U Tests Between Orchestration Configurations "
                "(Bonferroni-corrected $\\alpha = 0.017$)",
        label="tab:rq1_pairwise",
        header=["Pair", "$U$", "$p$-value", "Cohen's $d$", "Effect size", "Sig."],
        rows=rows,
        col_fmt="lccccc"
    )


# Table III — RQ2 PII Category Accuracy

def table_rq2_categories(base: Path) -> str:
    path = base / "pii_category_accuracy.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path} — run pii_analysis.py first")

    cat = pd.read_csv(path).sort_values("Category")

    label_map = {
        "adversarial":              "Adversarial (SSN + jailbreak)",
        "edge_case":                "Edge cases (bare / whitespace / minimal)",
        "format_variant":           "Format variants (no-dash / space / equals)",
        "long_message":             "Long message (clean)",
        "long_message_with_pii":    "Long message with buried SSN",
        "multilingual":             "Multilingual (French / Spanish)",
        "multiple_pii":             "Multiple PII types (SSN + email/phone)",
        "near_miss":                "Near-miss (phone / date / 8-digit)",
        "prompt_injection_no_pii":  "Prompt injection (no SSN)",
        "true_negative":            "True negative (clean complaints)",
        "true_negative_numbers":    "True negative (order/tracking numbers)",
        "true_positive":            "True positive (standard SSN format)",
    }

    rows = []
    for _, r in cat.iterrows():
        cat_name = label_map.get(r["Category"], r["Category"])
        rows.append([cat_name,
                     int(r["n"]),
                     int(r["Correct"]),
                     f"{r['Accuracy_%']:.0f}\\%"])

    return tex_table(
        caption="RQ2: PII Detection Accuracy by Test Category "
                "(a-two-a-pii-detector v1.0.1, Flex Gateway, $n=50$ test cases)",
        label="tab:rq2_categories",
        header=["Category", "$n$", "Correct", "Accuracy"],
        rows=rows,
        col_fmt="p{5.5cm}ccc"
    )


# Table IV — RQ2 Gateway Latency Overhead

def table_rq2_latency(base: Path) -> str:
    path = base / "pii_metrics_summary.csv"
    if not path.exists():
        raise FileNotFoundError(f"Missing {path} — run pii_analysis.py first")

    m = pd.read_csv(path).iloc[0]

    # Load raw for percentiles
    raw_path = sorted(base.glob("pii_*.csv"))
    if raw_path:
        raw = pd.read_csv(raw_path[-1])
        block_p95 = np.percentile(raw[raw["actual"] == "BLOCK"]["latency_ms"], 95)
        pass_p95  = np.percentile(raw[raw["actual"] == "PASS"]["latency_ms"], 95)
    else:
        block_p95 = pass_p95 = float("nan")

    overhead = m["latency_block_mean_ms"] - m["latency_pass_mean_ms"]

    rows = [
        ["BLOCK (policy rejected)", f"{m['latency_block_mean_ms']:.0f}", f"{block_p95:.0f}",
         "Flex Gateway short-circuit; no LLM invocation"],
        ["PASS (policy allowed)",   f"{m['latency_pass_mean_ms']:.0f}",  f"{pass_p95:.0f}",
         "Full 5-step orchestration; LLM + tool calls"],
        ["Overhead (BLOCK$-$PASS)", f"{overhead:.0f}", "—",
         "Negative = gateway faster than full pipeline"],
    ]

    return tex_table(
        caption="RQ2: Gateway Enforcement Latency by Outcome — "
                "BLOCK requests are short-circuited at Flex Gateway before reaching the LLM",
        label="tab:rq2_latency",
        header=["Outcome", "Mean (ms)", "p95 (ms)", "Notes"],
        rows=rows,
        col_fmt="lccp{4.5cm}"
    )


# master runner

def run(base: Path, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    tables = {
        "table_I_rq1_latency.tex":    table_rq1_latency,
        "table_II_rq1_pairwise.tex":  table_rq1_pairwise,
        "table_III_rq2_categories.tex": table_rq2_categories,
        "table_IV_rq2_latency.tex":   table_rq2_latency,
    }

    print("\n" + "="*65)
    print("  GENERATING LATEX TABLES FOR PUBLICATION")
    print("="*65)

    for fname, fn in tables.items():
        try:
            tex = fn(base)
            out_path = out_dir / fname
            out_path.write_text(tex + "\n")
            print(f"  {fname:<40} → {out_path}")
        except FileNotFoundError as e:
            print(f"  SKIP  {fname:<35}  ({e})")

    # Also write a combined tables.tex that inputs all four
    combined = out_dir / "tables_combined.tex"
    lines = [
        "% Auto-generated by results_tables.py",
        "% Include this file in your paper with \\input{tables/tables_combined}",
        "",
    ]
    for fname in tables:
        p = out_dir / fname
        if p.exists():
            lines.append(f"\\input{{{out_dir}/{fname}}}")
            lines.append("")
    combined.write_text("\n".join(lines))
    print(f"  {'tables_combined.tex':<40} → {combined}")
    print("="*65 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="Use live results/ instead of sample_results/")
    parser.add_argument("--out", type=str, default=None,
                        help="Output directory (default: research/paper/tables/)")
    args = parser.parse_args()

    base    = LIVE if args.live else SAMPLE
    out_dir = Path(args.out) if args.out else (HERE / "paper" / "tables")
    run(base, out_dir)
