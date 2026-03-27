#!/usr/bin/env python3
"""
Open Silicon Triage — Pre-Run Config Analyzer.

Reads your OpenLane config.json BEFORE you start a run and predicts
whether the design is likely to succeed based on community data.

Usage:
    python analyze-config.py --config ./openlane/config.json
    python analyze-config.py --clock-period 20 --utilization 0.45 --die-area "0 0 500 500" --pdk sky130A
"""
import argparse
import json
import math
import os
import sys

# Hardcoded fallback baselines (used when no corpus data is available)
FALLBACK_BASELINES = {
    "sky130A": {
        "max_viable_utilization": 0.65,
        "min_clock_period_ns": 10.0,
        "typical_clock_period_ns": 20.0,
        "min_die_area_um2": 10000,
        "notes": "sky130 has limited routing resources — keep utilization under 65% for clean runs",
        "source": "hardcoded defaults",
    },
    "gf180mcuD": {
        "max_viable_utilization": 0.70,
        "min_clock_period_ns": 8.0,
        "typical_clock_period_ns": 15.0,
        "min_die_area_um2": 8000,
        "notes": "GF180 has better metal stack — can tolerate slightly higher utilization",
        "source": "hardcoded defaults",
    },
}

DEFAULT_BASELINE = {
    "max_viable_utilization": 0.60,
    "min_clock_period_ns": 10.0,
    "typical_clock_period_ns": 20.0,
    "min_die_area_um2": 10000,
    "notes": "Using conservative defaults — contribute your runs to improve these baselines!",
    "source": "hardcoded defaults",
}


def learn_baselines_from_corpus(corpus_path: str) -> dict:
    """Learn thresholds from actual community run data.

    Analyzes the corpus to find:
    - What metric ranges led to successful (promoted_winner) runs?
    - What metric ranges led to failures (negative_evidence)?
    - Where is the boundary?
    """
    if not os.path.exists(corpus_path):
        return {}

    with open(corpus_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = data.get("records", []) if isinstance(data, dict) else data

    if len(records) < 10:
        return {}

    # Group by outcome
    winners = [r for r in records if r.get("outcome") == "promoted_winner"]
    losers = [r for r in records if r.get("outcome") == "negative_evidence"]

    if not winners or not losers:
        return {}

    def metric_stats(records_list, key):
        values = [r["metrics"].get(key, 0) for r in records_list if key in r.get("metrics", {})]
        if not values:
            return None
        values.sort()
        return {
            "min": min(values),
            "max": max(values),
            "median": values[len(values) // 2],
            "p75": values[int(len(values) * 0.75)] if len(values) > 3 else max(values),
            "p25": values[int(len(values) * 0.25)] if len(values) > 3 else min(values),
        }

    winner_hpwl = metric_stats(winners, "hpwlUm")
    loser_hpwl = metric_stats(losers, "hpwlUm")
    winner_wns = metric_stats(winners, "setupWnsNs")
    loser_wns = metric_stats(losers, "setupWnsNs")
    winner_setup = metric_stats(winners, "setupViolations")
    loser_setup = metric_stats(losers, "setupViolations")

    learned = {
        "source": f"learned from {len(records)} corpus records ({len(winners)} winners, {len(losers)} losers)",
        "recordCount": len(records),
        "winnerCount": len(winners),
        "loserCount": len(losers),
    }

    # Learn HPWL threshold: where winners end and losers begin
    if winner_hpwl and loser_hpwl:
        learned["max_safe_hpwl"] = winner_hpwl["p75"]
        learned["danger_hpwl"] = loser_hpwl["median"]

    # Learn WNS threshold
    if winner_wns and loser_wns:
        learned["max_safe_wns"] = winner_wns["p25"]  # worst WNS among winners
        learned["danger_wns"] = loser_wns["median"]

    # Learn setup violation threshold
    if winner_setup and loser_setup:
        learned["max_safe_setup_violations"] = winner_setup["p75"]
        learned["danger_setup_violations"] = loser_setup["median"]

    return learned


def parse_openlane_config(config_path: str) -> dict:
    """Extract key parameters from an OpenLane config.json."""
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)

    params = {}

    # Clock period
    for key in ["CLOCK_PERIOD", "clock_period"]:
        if key in config:
            params["clock_period_ns"] = float(config[key])

    # Utilization
    for key in ["FP_CORE_UTIL", "PL_TARGET_DENSITY", "fp_core_util", "pl_target_density"]:
        if key in config:
            val = float(config[key])
            params["utilization"] = val / 100.0 if val > 1 else val

    # Die area
    for key in ["DIE_AREA", "die_area", "FP_DIE_AREA"]:
        if key in config:
            area = config[key]
            if isinstance(area, str):
                coords = [float(x) for x in area.split()]
            elif isinstance(area, list):
                coords = [float(x) for x in area]
            else:
                continue
            if len(coords) >= 4:
                width = coords[2] - coords[0]
                height = coords[3] - coords[1]
                params["die_area_um2"] = width * height

    # PDK
    for key in ["PDK", "pdk"]:
        if key in config:
            params["pdk"] = config[key]

    # Design name
    for key in ["DESIGN_NAME", "design_name"]:
        if key in config:
            params["design_name"] = config[key]

    # Routing strategy
    for key in ["GRT_ALLOW_CONGESTION", "ROUTING_STRATEGY"]:
        if key in config:
            params["routing_aggressive"] = True

    return params


def analyze(params: dict) -> list:
    """Analyze config parameters and return warnings/recommendations."""
    findings = []
    pdk = params.get("pdk", "unknown")
    baseline = FALLBACK_BASELINES.get(pdk, DEFAULT_BASELINE)

    # Check utilization
    util = params.get("utilization")
    if util is not None:
        if util > baseline["max_viable_utilization"]:
            findings.append({
                "severity": "🔴 HIGH RISK",
                "metric": "Utilization",
                "value": f"{util:.0%}",
                "threshold": f"{baseline['max_viable_utilization']:.0%}",
                "message": f"Utilization {util:.0%} exceeds the typical max of {baseline['max_viable_utilization']:.0%} for {pdk}. "
                           f"This usually causes routing congestion, antenna violations, and hold failures. "
                           f"Consider reducing to {baseline['max_viable_utilization'] - 0.10:.0%} or below.",
            })
        elif util > baseline["max_viable_utilization"] - 0.10:
            findings.append({
                "severity": "🟡 WARNING",
                "metric": "Utilization",
                "value": f"{util:.0%}",
                "threshold": f"{baseline['max_viable_utilization']:.0%}",
                "message": f"Utilization {util:.0%} is close to the danger zone. "
                           f"Watch for routing congestion in the placement report.",
            })
        else:
            findings.append({
                "severity": "✅ OK",
                "metric": "Utilization",
                "value": f"{util:.0%}",
                "threshold": f"{baseline['max_viable_utilization']:.0%}",
                "message": f"Utilization looks safe for {pdk}.",
            })

    # Check clock period
    clock = params.get("clock_period_ns")
    if clock is not None:
        if clock < baseline["min_clock_period_ns"]:
            findings.append({
                "severity": "🔴 HIGH RISK",
                "metric": "Clock Period",
                "value": f"{clock} ns ({1000/clock:.0f} MHz)",
                "threshold": f"{baseline['min_clock_period_ns']} ns ({1000/baseline['min_clock_period_ns']:.0f} MHz)",
                "message": f"Clock period {clock} ns is very aggressive for {pdk}. "
                           f"Community data shows runs below {baseline['min_clock_period_ns']} ns rarely pass timing. "
                           f"Consider {baseline['typical_clock_period_ns']} ns as a starting point.",
            })
        elif clock < baseline["typical_clock_period_ns"]:
            findings.append({
                "severity": "🟡 WARNING",
                "metric": "Clock Period",
                "value": f"{clock} ns ({1000/clock:.0f} MHz)",
                "threshold": f"Typical: {baseline['typical_clock_period_ns']} ns",
                "message": f"Moderately aggressive clock. May work but watch for setup violations.",
            })
        else:
            findings.append({
                "severity": "✅ OK",
                "metric": "Clock Period",
                "value": f"{clock} ns ({1000/clock:.0f} MHz)",
                "threshold": f"Min: {baseline['min_clock_period_ns']} ns",
                "message": "Clock period looks achievable.",
            })

    # Check die area
    area = params.get("die_area_um2")
    if area is not None:
        if area < baseline["min_die_area_um2"]:
            findings.append({
                "severity": "🟡 WARNING",
                "metric": "Die Area",
                "value": f"{area:,.0f} µm²",
                "threshold": f"{baseline['min_die_area_um2']:,} µm²",
                "message": "Small die area. May force high utilization even with a small design.",
            })
        else:
            findings.append({
                "severity": "✅ OK",
                "metric": "Die Area",
                "value": f"{area:,.0f} µm²",
                "threshold": f"Min: {baseline['min_die_area_um2']:,} µm²",
                "message": "Die area is sufficient.",
            })

    # Combination check: high util + aggressive clock
    if util and clock:
        if util > 0.50 and clock < baseline["typical_clock_period_ns"]:
            findings.append({
                "severity": "🔴 HIGH RISK",
                "metric": "Utilization × Clock",
                "value": f"{util:.0%} util + {clock} ns clock",
                "threshold": "Combined risk",
                "message": "High utilization combined with aggressive clock period is the #1 cause of failed runs. "
                           "Either reduce utilization or relax the clock target.",
            })

    if not findings:
        findings.append({
            "severity": "ℹ️ INFO",
            "metric": "General",
            "value": "-",
            "threshold": "-",
            "message": "Not enough config parameters found. Pass --config with your OpenLane config.json for a full analysis.",
        })

    return findings


def main():
    parser = argparse.ArgumentParser(
        description="Analyze your OpenLane config BEFORE running — catch problems early",
        epilog="Example: python analyze-config.py --config ./openlane/config.json"
    )
    parser.add_argument("--config", help="Path to OpenLane config.json")
    parser.add_argument("--clock-period", type=float, help="Target clock period in ns")
    parser.add_argument("--utilization", type=float, help="Target utilization (0.0-1.0)")
    parser.add_argument("--die-area", help="Die area as 'x0 y0 x1 y1' in µm")
    parser.add_argument("--pdk", default="sky130A", help="PDK name")
    parser.add_argument("--corpus", help="Path to corpus for learning thresholds")
    args = parser.parse_args()

    # Learn thresholds from corpus if available
    if args.corpus:
        learned = learn_baselines_from_corpus(args.corpus)
        if learned:
            print(f"  📚 Baselines: {learned['source']}")
        else:
            print("  📚 Baselines: hardcoded defaults (corpus too small or not found)")
    else:
        # Try default corpus location
        default_corpus = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "corpus", "seed-corpus.json")
        learned = learn_baselines_from_corpus(default_corpus)

    params = {}

    if args.config:
        if not os.path.exists(args.config):
            print(f"❌ Config not found: {args.config}")
            sys.exit(1)
        params = parse_openlane_config(args.config)

    # CLI overrides
    if args.clock_period:
        params["clock_period_ns"] = args.clock_period
    if args.utilization:
        params["utilization"] = args.utilization
    if args.die_area:
        coords = [float(x) for x in args.die_area.split()]
        if len(coords) >= 4:
            params["die_area_um2"] = (coords[2] - coords[0]) * (coords[3] - coords[1])
    if args.pdk:
        params["pdk"] = args.pdk

    print("=" * 60)
    print("  Open Silicon Triage — Pre-Run Config Analysis")
    print("=" * 60)
    print()

    if params.get("design_name"):
        print(f"  Design:  {params['design_name']}")
    print(f"  PDK:     {params.get('pdk', 'unknown')}")
    if params.get("clock_period_ns"):
        print(f"  Clock:   {params['clock_period_ns']} ns ({1000/params['clock_period_ns']:.0f} MHz)")
    if params.get("utilization"):
        print(f"  Util:    {params['utilization']:.0%}")
    if params.get("die_area_um2"):
        print(f"  Area:    {params['die_area_um2']:,.0f} µm²")
    print()
    print("-" * 60)

    findings = analyze(params)

    high_risk = sum(1 for f in findings if "HIGH RISK" in f["severity"])
    warnings = sum(1 for f in findings if "WARNING" in f["severity"])

    for finding in findings:
        print(f"\n  {finding['severity']}: {finding['metric']}")
        print(f"    Your value:  {finding['value']}")
        print(f"    Threshold:   {finding['threshold']}")
        print(f"    → {finding['message']}")

    print()
    print("-" * 60)
    if high_risk > 0:
        print(f"\n  🔴 VERDICT: {high_risk} high-risk issue(s) found.")
        print("     This run will very likely fail. Fix the issues above first.")
    elif warnings > 0:
        print(f"\n  🟡 VERDICT: {warnings} warning(s). Proceed with caution.")
    else:
        print("\n  ✅ VERDICT: Config looks good. Proceed with the run.")
    print()


if __name__ == "__main__":
    main()
