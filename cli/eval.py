#!/usr/bin/env python3
"""Open Silicon Triage — Evaluate a trained triage model on held-out data."""
import argparse
import json
import os
from datetime import datetime, timezone

import joblib
from sklearn.metrics import accuracy_score


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def smoke_records():
    """Built-in smoke eval data."""
    return [
        {"features": {"family": "v1", "touches_observe": 1, "sink_delta_um": 108.0, "antenna_reopen": 1, "hold_delta": 145}, "label": "likely_clear_loser"},
        {"features": {"family": "v2", "touches_observe": 0, "sink_delta_um": -18.0, "antenna_reopen": 0, "hold_delta": -395}, "label": "worth_alpha_run"},
        {"features": {"family": "v2", "touches_retire": 1, "sink_delta_um": 4.0, "antenna_reopen": 0, "hold_delta": -395}, "label": "uncertain"},
    ]


def load_records(args):
    if args.smoke:
        return smoke_records()

    with open(args.features, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    records = payload if isinstance(payload, list) else payload.get("records", [])
    normalized = []
    for record in records:
        if record.get("datasetSplit") == "train":
            continue
        features = record.get("metrics") or record.get("features") or record.get("featureVector") or {}
        label = record.get("outcome") or record.get("label") or record.get("classification")
        if not isinstance(features, dict) or not label:
            continue
        normalized.append({"features": features, "label": str(label)})
    return normalized


def main():
    parser = argparse.ArgumentParser(description="Evaluate a trained triage model")
    parser.add_argument("--model", required=True, help="Path to trained model bundle (.joblib)")
    parser.add_argument("--features", help="Path to normalized features JSON")
    parser.add_argument("--out-summary", required=True, help="Path to evaluation summary JSON")
    parser.add_argument("--smoke", action="store_true", help="Use built-in smoke data")
    args = parser.parse_args()

    records = load_records(args)
    if not records:
        raise SystemExit("no evaluation records available")

    bundle = joblib.load(args.model)
    vectorizer = bundle["vectorizer"]
    model = bundle["model"]
    class_labels = list(bundle["class_labels"])
    class_to_index = {label: index for index, label in enumerate(class_labels)}
    expected = [class_to_index[record["label"]] for record in records]
    matrix = vectorizer.transform([record["features"] for record in records])
    predicted = model.predict(matrix)
    if hasattr(predicted, "ndim") and int(getattr(predicted, "ndim", 1)) > 1:
        predicted = predicted.argmax(axis=1)
    accuracy = float(accuracy_score(expected, predicted))

    os.makedirs(os.path.dirname(os.path.abspath(args.out_summary)), exist_ok=True)
    summary = {
        "schemaVersion": "open-silicon-triage.evaluation.v1",
        "evaluatedAt": now_iso(),
        "smokeMode": bool(args.smoke),
        "recordCount": len(records),
        "classLabels": class_labels,
        "accuracy": accuracy,
        "modelPath": args.model,
    }
    with open(args.out_summary, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
