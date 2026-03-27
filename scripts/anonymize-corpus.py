#!/usr/bin/env python3
"""Extract and anonymize the Sovryn training corpus into the open schema format.

Usage:
    python scripts/anonymize-corpus.py \
      --input ../SovrynClean/outputs/runtime/silicon-ml/pan-stem-npu-silicon-training-corpus-latest.json \
      --out ../open-silicon-triage/corpus/seed-corpus.json
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone


def anonymize_id(original: str) -> str:
    return "ost-" + hashlib.sha256(original.encode()).hexdigest()[:12]


def map_stage_family(stage_family: str) -> str:
    return {"v1": "family-a", "v2": "family-b", "v3": "family-c"}.get(stage_family, "other")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    with open(args.input, "r", encoding="utf-8") as f:
        raw = json.load(f)

    records = raw.get("records", [])
    anonymized = []

    for r in records:
        anonymized.append({
            "schemaVersion": "open-silicon-triage.corpus.v1",
            "recordId": anonymize_id(r.get("recordId", "")),
            "project": "seed",
            "variant": map_stage_family(r.get("stageFamily", "other")),
            "pdk": "sky130A",
            "tool": "OpenLane 2.x + OpenROAD",
            "metrics": {
                "hpwlUm": r.get("hpwlUm", 0),
                "averageSinkWireLengthUm": r.get("averageSinkWireLengthUm", 0),
                "setupWnsNs": r.get("setupWnsNs", 0),
                "setupViolations": r.get("setupViolations", 0),
                "holdViolations": r.get("holdViolations", 0),
                "antennaViolations": r.get("finalAntennaOffenderCount", 0),
                "maxCapViolations": r.get("maxCapViolations", 0),
                "maxSlewViolations": r.get("maxSlewViolations", 0),
            },
            "outcome": r.get("outcomeLabel", "negative_evidence"),
            "observedAt": r.get("observedAt", datetime.now(timezone.utc).isoformat()),
            "contributor": "sovereign-factory-seed",
        })

    output = {
        "schemaVersion": "open-silicon-triage.corpus.v1",
        "generatedAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "recordCount": len(anonymized),
        "records": anonymized,
    }

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
        f.write("\n")

    print(f"✅ Anonymized {len(anonymized)} records → {args.out}")


if __name__ == "__main__":
    main()
