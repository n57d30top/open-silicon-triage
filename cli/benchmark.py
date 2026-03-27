#!/usr/bin/env python3
"""
Open Silicon Triage — Benchmark your run against community data.

Compares your OpenLane run results against similar designs in the corpus
and shows where you stand.

Usage:
    python benchmark.py --run-dir ./runs/RUN_2026.03.27
    python benchmark.py --metrics '{"hpwl": 10937, "wns": -7.93, "setup": 459, "hold": 0, "antenna": 0}'
    python benchmark.py --run-dir ./runs/RUN_2026.03.27 --corpus corpus/seed-corpus.json
"""
import argparse
import json
import math
import os
import sys


def load_corpus(corpus_path: str) -> list:
    """Load corpus records."""
    with open(corpus_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("records", []) if isinstance(data, dict) else data


def extract_run_metrics(run_dir: str) -> dict:
    """Extract metrics from an OpenLane run directory."""
    import re
    metrics = {}

    for csv_name in ["metrics.csv", "final_summary_report.csv"]:
        csv_path = os.path.join(run_dir, "reports", csv_name)
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) >= 2:
                headers = [h.strip().lower() for h in lines[0].split(",")]
                values = [v.strip() for v in lines[1].split(",")]
                row = dict(zip(headers, values))
                if "hpwl" in row:
                    metrics["hpwlUm"] = float(row["hpwl"])
                for key in ["wns", "setup_wns"]:
                    if key in row:
                        metrics["setupWnsNs"] = float(row[key])
                if "antenna_violations" in row:
                    metrics["antennaViolations"] = int(float(row["antenna_violations"]))
            break

    for subdir in ["signoff", "cts", ""]:
        for log_name in ["sta.log", "opensta.log"]:
            log_path = os.path.join(run_dir, "logs", subdir, log_name) if subdir else os.path.join(run_dir, "logs", log_name)
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    content = f.read()
                for pattern in [r"Setup:\s*(\d+)", r"setup.*?(\d+)\s+violat"]:
                    m = re.search(pattern, content, re.IGNORECASE)
                    if m and "setupViolations" not in metrics:
                        metrics["setupViolations"] = int(m.group(1))
                for pattern in [r"Hold:\s*(\d+)", r"hold.*?(\d+)\s+violat"]:
                    m = re.search(pattern, content, re.IGNORECASE)
                    if m and "holdViolations" not in metrics:
                        metrics["holdViolations"] = int(m.group(1))
                break

    return metrics


def parse_manual_metrics(metrics_str: str) -> dict:
    """Parse manually provided metrics."""
    raw = json.loads(metrics_str)
    SHORT_MAP = {
        "hpwl": "hpwlUm", "sink": "averageSinkWireLengthUm",
        "wns": "setupWnsNs", "setup": "setupViolations",
        "hold": "holdViolations", "antenna": "antennaViolations",
    }
    result = {}
    for short, full in SHORT_MAP.items():
        if short in raw:
            result[full] = raw[short]
    result.update({k: v for k, v in raw.items() if k not in SHORT_MAP})
    return result


def percentile(values: list, pct: float) -> float:
    """Calculate percentile of a sorted list."""
    if not values:
        return 0
    k = (len(values) - 1) * pct
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return values[int(k)]
    return values[f] * (c - k) + values[c] * (k - f)


def compute_corpus_stats(corpus: list) -> dict:
    """Compute statistics for each metric across the corpus."""
    metric_keys = ["hpwlUm", "averageSinkWireLengthUm", "setupWnsNs",
                   "setupViolations", "holdViolations", "antennaViolations"]

    stats = {}
    for key in metric_keys:
        values = []
        for record in corpus:
            m = record.get("metrics", {})
            if key in m and m[key] is not None:
                values.append(float(m[key]))

        if not values:
            continue

        values.sort()
        stats[key] = {
            "min": min(values),
            "max": max(values),
            "median": percentile(values, 0.5),
            "p25": percentile(values, 0.25),
            "p75": percentile(values, 0.75),
            "count": len(values),
        }

    # Stats by outcome
    outcomes = {}
    for record in corpus:
        outcome = record.get("outcome", "unknown")
        if outcome not in outcomes:
            outcomes[outcome] = 0
        outcomes[outcome] += 1
    stats["_outcomes"] = outcomes

    return stats


def rate_metric(value: float, stats: dict, lower_is_better: bool = True) -> str:
    """Rate a metric value against corpus statistics."""
    if lower_is_better:
        if value <= stats["p25"]:
            return "✅ excellent"
        elif value <= stats["median"]:
            return "✅ good"
        elif value <= stats["p75"]:
            return "🟡 average"
        else:
            return "🔴 poor"
    else:  # higher is better (e.g., WNS closer to 0)
        if value >= stats["p75"]:
            return "✅ excellent"
        elif value >= stats["median"]:
            return "✅ good"
        elif value >= stats["p25"]:
            return "🟡 average"
        else:
            return "🔴 poor"


METRIC_LABELS = {
    "hpwlUm": ("HPWL", "µm", True),
    "averageSinkWireLengthUm": ("Avg Sink Wire", "µm", True),
    "setupWnsNs": ("Setup WNS", "ns", False),  # higher (closer to 0) is better
    "setupViolations": ("Setup Violations", "", True),
    "holdViolations": ("Hold Violations", "", True),
    "antennaViolations": ("Antenna Violations", "", True),
}


def main():
    parser = argparse.ArgumentParser(
        description="Compare your OpenLane run against community data",
        epilog="Example: python benchmark.py --run-dir ./runs/RUN_2026.03.27"
    )
    parser.add_argument("--run-dir", help="Path to your OpenLane run directory")
    parser.add_argument("--metrics", help="Manual metrics as JSON string")
    parser.add_argument("--corpus", default="corpus/seed-corpus.json", help="Path to corpus (default: corpus/seed-corpus.json)")
    parser.add_argument("--variant", help="Filter comparisons to a specific design variant (e.g. 'npu-array-v1')")
    args = parser.parse_args()

    if not args.run_dir and not args.metrics:
        parser.error("Provide either --run-dir or --metrics")

    # Load corpus
    corpus_path = args.corpus
    if not os.path.isabs(corpus_path):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        corpus_path = os.path.join(os.path.dirname(script_dir), corpus_path)
    if not os.path.exists(corpus_path):
        print(f"❌ Corpus not found: {corpus_path}")
        sys.exit(1)

    corpus = load_corpus(corpus_path)
    
    context_msg = f"Comparing against {len(corpus)} global community runs"
    if args.variant:
        subset = [r for r in corpus if r.get("variant") == args.variant]
        if len(subset) >= 5:
            corpus = subset
            context_msg = f"Comparing against {len(corpus)} similar runs (Variant: {args.variant})"
        else:
            context_msg += f"\n  (Note: Not enough data for variant '{args.variant}', need >= 5)"

    stats = compute_corpus_stats(corpus)

    # Get user metrics
    if args.run_dir:
        user_metrics = extract_run_metrics(args.run_dir)
    else:
        user_metrics = parse_manual_metrics(args.metrics)

    if not user_metrics:
        print("❌ No metrics found.")
        sys.exit(1)

    # Display
    print("=" * 70)
    print("  Open Silicon Triage — Benchmark Report")
    print(f"  {context_msg}")
    print("=" * 70)

    outcomes = stats.get("_outcomes", {})
    if outcomes:
        print(f"\n  Corpus breakdown: ", end="")
        parts = [f"{v} {k}" for k, v in sorted(outcomes.items())]
        print(", ".join(parts))

    print()
    print(f"  {'Metric':<22} {'Your Value':>12} {'Community':>12} {'25th %':>10} {'75th %':>10} {'Rating':>15}")
    print(f"  {'─' * 22} {'─' * 12} {'─' * 12} {'─' * 10} {'─' * 10} {'─' * 15}")

    for key, (label, unit, lower_is_better) in METRIC_LABELS.items():
        if key not in user_metrics or key not in stats:
            continue

        val = user_metrics[key]
        s = stats[key]
        rating = rate_metric(val, s, lower_is_better)

        unit_str = f" {unit}" if unit else ""
        print(f"  {label:<22} {val:>10.1f}{unit_str:>2} {s['median']:>10.1f}{unit_str:>2} {s['p25']:>8.1f}{unit_str:>2} {s['p75']:>8.1f}{unit_str:>2}  {rating}")

    # Overall verdict
    ratings = []
    for key, (_, _, lower_is_better) in METRIC_LABELS.items():
        if key in user_metrics and key in stats:
            ratings.append(rate_metric(user_metrics[key], stats[key], lower_is_better))

    excellent_or_good = sum(1 for r in ratings if "✅" in r)
    poor = sum(1 for r in ratings if "🔴" in r)

    print()
    print("-" * 70)
    if poor > 0:
        print(f"\n  🔴 BELOW AVERAGE — {poor} metric(s) in the bottom quartile")
        print("     Your run has weaker metrics than most in the community corpus.")
    elif excellent_or_good == len(ratings):
        print(f"\n  ✅ EXCELLENT — All metrics are at or above the community median")
        print("     Your design is performing well compared to the corpus.")
    else:
        print(f"\n  🟡 MIXED — Some metrics are good, some need attention")
    print()


if __name__ == "__main__":
    main()
