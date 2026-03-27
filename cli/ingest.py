#!/usr/bin/env python3
"""Open Silicon Triage — Ingest OpenLane run results into the open corpus format.

Usage:
    python ingest.py --openlane-dir ./runs/RUN_2026.03.27 --out corpus/my-run.json
    python ingest.py --metrics '{"hpwl": 10937, "sink": 312, "wns": -7.93, "setup": 459, "hold": 395, "antenna": 0}' --out corpus/manual.json
"""
import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_openlane_summary(run_dir: str) -> dict:
    """Try to extract key metrics from an OpenLane run directory."""
    metrics = {}
    
    # Try final_summary_report.csv
    csv_path = os.path.join(run_dir, "reports", "metrics.csv")
    if not os.path.exists(csv_path):
        csv_path = os.path.join(run_dir, "reports", "final_summary_report.csv")
    
    if os.path.exists(csv_path):
        with open(csv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) >= 2:
            headers = [h.strip() for h in lines[0].split(",")]
            values = [v.strip() for v in lines[1].split(",")]
            row = dict(zip(headers, values))
            
            for key in ["HPWL", "hpwl"]:
                if key in row:
                    metrics["hpwlUm"] = float(row[key])
            for key in ["wns", "WNS", "setup_wns"]:
                if key in row:
                    metrics["setupWnsNs"] = float(row[key])
            for key in ["antenna_violations", "antenna"]:
                if key in row:
                    metrics["antennaViolations"] = int(row[key])

    # Try parsing STA logs for hold/setup violations
    for log_name in ["sta.log", "opensta.log"]:
        log_path = os.path.join(run_dir, "logs", "signoff", log_name)
        if os.path.exists(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            setup_match = re.search(r"setup\s+violations?\s*[:=]\s*(\d+)", content, re.IGNORECASE)
            hold_match = re.search(r"hold\s+violations?\s*[:=]\s*(\d+)", content, re.IGNORECASE)
            if setup_match:
                metrics["setupViolations"] = int(setup_match.group(1))
            if hold_match:
                metrics["holdViolations"] = int(hold_match.group(1))

    return metrics


def main():
    parser = argparse.ArgumentParser(description="Ingest OpenLane results into the open triage corpus format")
    parser.add_argument("--openlane-dir", help="Path to an OpenLane run directory")
    parser.add_argument("--metrics", help="Raw metrics as JSON string")
    parser.add_argument("--project", default="community", help="Project identifier (default: community)")
    parser.add_argument("--variant", default="unknown", help="Design variant name")
    parser.add_argument("--pdk", default="sky130A", help="PDK used (default: sky130A)")
    parser.add_argument("--tool", default="OpenLane 2.x", help="EDA tool used")
    parser.add_argument("--outcome", choices=["negative_evidence", "strategic_progress", "promoted_winner"],
                        default="negative_evidence", help="Run outcome label")
    parser.add_argument("--out", required=True, help="Output JSON path")
    args = parser.parse_args()

    metrics = {}
    if args.openlane_dir:
        metrics = parse_openlane_summary(args.openlane_dir)
    if args.metrics:
        manual = json.loads(args.metrics)
        # Map short names to schema names
        SHORT_MAP = {
            "hpwl": "hpwlUm", "sink": "averageSinkWireLengthUm",
            "wns": "setupWnsNs", "setup": "setupViolations",
            "hold": "holdViolations", "antenna": "antennaViolations",
        }
        for short, full in SHORT_MAP.items():
            if short in manual:
                metrics[full] = manual[short]
        metrics.update({k: v for k, v in manual.items() if k not in SHORT_MAP})

    record_id = hashlib.sha256(json.dumps(metrics, sort_keys=True).encode()).hexdigest()[:16]
    
    record = {
        "schemaVersion": "open-silicon-triage.corpus.v1",
        "recordId": f"ost-{record_id}",
        "project": args.project,
        "variant": args.variant,
        "pdk": args.pdk,
        "tool": args.tool,
        "metrics": {
            "hpwlUm": metrics.get("hpwlUm", 0),
            "averageSinkWireLengthUm": metrics.get("averageSinkWireLengthUm", 0),
            "setupWnsNs": metrics.get("setupWnsNs", 0),
            "setupViolations": metrics.get("setupViolations", 0),
            "holdViolations": metrics.get("holdViolations", 0),
            "antennaViolations": metrics.get("antennaViolations", 0),
        },
        "outcome": args.outcome,
        "observedAt": now_iso(),
        "contributor": "anonymous",
    }

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2)
        f.write("\n")

    print(json.dumps(record, indent=2))
    print(f"\n✅ Record written to {args.out}")


if __name__ == "__main__":
    main()
