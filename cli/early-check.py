#!/usr/bin/env python3
"""
Open Silicon Triage — Early Abort Check.

Run this DURING an OpenLane flow, right after the placement step finishes
(~5 minutes in). It reads the placement-stage metrics and tells you
whether to continue or abort — saving you 25+ minutes.

Usage:
    python early-check.py --run-dir ./runs/RUN_2026.03.27
"""
import argparse
import json
import os
import re
import sys


def find_placement_metrics(run_dir: str) -> dict:
    """Extract metrics available after the placement stage."""
    metrics = {}

    # --- HPWL from placement report ---
    for report_name in ["placement.rpt", "global_placement.rpt"]:
        for subdir in ["placement", "global_placement", ""]:
            rpt_path = os.path.join(run_dir, "reports", subdir, report_name) if subdir else os.path.join(run_dir, "reports", report_name)
            if os.path.exists(rpt_path):
                with open(rpt_path, "r", encoding="utf-8") as f:
                    content = f.read()
                hpwl_match = re.search(r"(?:hpwl|wire.?length).*?([\d.]+(?:e[+-]?\d+)?)", content, re.IGNORECASE)
                if hpwl_match:
                    metrics["hpwlUm"] = float(hpwl_match.group(1))
                break

    # --- From metrics CSV if available at this stage ---
    for csv_name in ["metrics.csv", "final_summary_report.csv"]:
        csv_path = os.path.join(run_dir, "reports", csv_name)
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) >= 2:
                headers = [h.strip().lower() for h in lines[0].split(",")]
                values = [v.strip() for v in lines[1].split(",")]
                row = dict(zip(headers, values))
                if "hpwl" in row and "hpwlUm" not in metrics:
                    metrics["hpwlUm"] = float(row["hpwl"])
                for key in ["wns", "setup_wns"]:
                    if key in row:
                        metrics["setupWnsNs"] = float(row[key])
                for key in ["tns", "setup_tns"]:
                    if key in row:
                        metrics["setupTnsNs"] = float(row[key])
            break

    # --- Early STA results (if available) ---
    for subdir in ["placement", "cts", ""]:
        for log_name in ["sta.log", "opensta.log"]:
            log_path = os.path.join(run_dir, "logs", subdir, log_name) if subdir else os.path.join(run_dir, "logs", log_name)
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    content = f.read()
                wns_match = re.search(r"worst.*?slack.*?(-?[\d.]+)", content, re.IGNORECASE)
                if wns_match and "setupWnsNs" not in metrics:
                    metrics["setupWnsNs"] = float(wns_match.group(1))
                for pattern in [r"(\d+)\s+violat", r"Setup:\s*(\d+)"]:
                    m = re.search(pattern, content, re.IGNORECASE)
                    if m and "setupViolations" not in metrics:
                        metrics["setupViolations"] = int(m.group(1))
                break

    # --- Congestion from placement logs ---
    for log_name in ["global_place.log", "detailed_place.log", "placement.log"]:
        for subdir in ["placement", ""]:
            log_path = os.path.join(run_dir, "logs", subdir, log_name) if subdir else os.path.join(run_dir, "logs", log_name)
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    content = f.read()
                overflow_match = re.search(r"overflow.*?([\d.]+)", content, re.IGNORECASE)
                if overflow_match:
                    metrics["routingOverflow"] = float(overflow_match.group(1))
                congestion_match = re.search(r"congestion.*?([\d.]+)%", content, re.IGNORECASE)
                if congestion_match:
                    metrics["congestionPct"] = float(congestion_match.group(1))
                break

    return metrics


# Thresholds based on community data
EARLY_ABORT_RULES = [
    {
        "name": "Extreme Setup WNS",
        "check": lambda m: m.get("setupWnsNs", 0) < -15.0,
        "severity": "🔴 ABORT",
        "message": lambda m: f"Setup WNS is {m['setupWnsNs']:.2f} ns — too negative to recover during routing. "
                              f"CTS and routing typically add 1-3 ns of slack, not {abs(m['setupWnsNs']):.0f} ns.",
    },
    {
        "name": "Massive Setup Violations",
        "check": lambda m: m.get("setupViolations", 0) > 1000,
        "severity": "🔴 ABORT",
        "message": lambda m: f"{m['setupViolations']} setup violations after placement. "
                              f"Routing will add parasitics and make this worse, not better.",
    },
    {
        "name": "High HPWL",
        "check": lambda m: m.get("hpwlUm", 0) > 50000,
        "severity": "🟡 WARNING",
        "message": lambda m: f"HPWL is {m['hpwlUm']:,.0f} µm — significantly above typical successful runs. "
                              f"Long wires mean more delay, more power, more antenna risk.",
    },
    {
        "name": "Bad Setup WNS",
        "check": lambda m: m.get("setupWnsNs", 0) < -10.0,
        "severity": "🟡 WARNING",
        "message": lambda m: f"Setup WNS is {m['setupWnsNs']:.2f} ns — routing may not recover this fully.",
    },
    {
        "name": "Many Setup Violations",
        "check": lambda m: m.get("setupViolations", 0) > 500,
        "severity": "🟡 WARNING",
        "message": lambda m: f"{m['setupViolations']} setup violations — elevated risk, but routing sometimes helps.",
    },
    {
        "name": "High Congestion",
        "check": lambda m: m.get("congestionPct", 0) > 50,
        "severity": "🔴 ABORT",
        "message": lambda m: f"Routing congestion at {m['congestionPct']:.0f}% — will likely cause DRC failures.",
    },
]


def main():
    parser = argparse.ArgumentParser(
        description="Check placement-stage metrics and decide: continue or abort the run?",
        epilog="Run this after OpenLane finishes placement (~5 min) to save 25+ min on doomed runs"
    )
    parser.add_argument("--run-dir", required=True, help="Path to the OpenLane run directory (even mid-run)")
    args = parser.parse_args()

    if not os.path.isdir(args.run_dir):
        print(f"❌ Directory not found: {args.run_dir}")
        sys.exit(1)

    print("=" * 60)
    print("  Open Silicon Triage — Early Abort Check")
    print("  (Run this after placement, ~5 min into the flow)")
    print("=" * 60)

    metrics = find_placement_metrics(args.run_dir)

    if not metrics:
        print("\n  ⚠️  No placement metrics found yet.")
        print("  Make sure the placement step has completed.")
        print(f"  Looked in: {args.run_dir}/reports/ and {args.run_dir}/logs/")
        sys.exit(1)

    print("\n  📊 Placement-Stage Metrics Found:")
    for key, value in sorted(metrics.items()):
        if isinstance(value, float):
            print(f"    {key}: {value:,.2f}")
        else:
            print(f"    {key}: {value}")

    print()
    print("-" * 60)

    abort_count = 0
    warning_count = 0
    triggered = []

    for rule in EARLY_ABORT_RULES:
        if rule["check"](metrics):
            triggered.append(rule)
            if "ABORT" in rule["severity"]:
                abort_count += 1
            else:
                warning_count += 1

    if triggered:
        for rule in triggered:
            print(f"\n  {rule['severity']}: {rule['name']}")
            print(f"    → {rule['message'](metrics)}")
    else:
        print("\n  ✅ All early metrics look healthy.")

    print()
    print("-" * 60)

    if abort_count > 0:
        print(f"\n  🔴 RECOMMENDATION: ABORT THIS RUN")
        print(f"     {abort_count} critical issue(s) detected after placement.")
        print(f"     Continuing will waste ~25 minutes with near-certain failure.")
        print(f"     Fix your config and try again.")
        sys.exit(2)
    elif warning_count > 0:
        print(f"\n  🟡 RECOMMENDATION: PROCEED WITH CAUTION")
        print(f"     {warning_count} warning(s). The run might still succeed, but watch closely.")
    else:
        print(f"\n  ✅ RECOMMENDATION: CONTINUE")
        print(f"     Placement metrics look good. Proceed with CTS and routing.")
    print()


if __name__ == "__main__":
    main()
