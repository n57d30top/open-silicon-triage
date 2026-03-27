#!/usr/bin/env python3
"""Open Silicon Triage — Train a triage predictor from a corpus of OpenLane runs."""
import argparse
import json
import os
from datetime import datetime, timezone

import joblib
from sklearn.feature_extraction import DictVectorizer
from sklearn.metrics import accuracy_score
from xgboost import XGBClassifier


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def smoke_records():
    """Built-in smoke data for quick demos — no external files needed."""
    return [
        {"features": {"family": "v1", "touches_observe": 1, "sink_delta_um": 105.0, "antenna_reopen": 1, "hold_delta": 140}, "label": "likely_clear_loser"},
        {"features": {"family": "v1", "touches_command": 1, "sink_delta_um": 120.0, "antenna_reopen": 1, "hold_delta": 120}, "label": "likely_clear_loser"},
        {"features": {"family": "v2", "touches_observe": 0, "sink_delta_um": -21.0, "antenna_reopen": 0, "hold_delta": -395}, "label": "worth_alpha_run"},
        {"features": {"family": "v2", "touches_retire": 1, "sink_delta_um": 3.0, "antenna_reopen": 1, "hold_delta": -395}, "label": "uncertain"},
        {"features": {"family": "v2", "touches_retire": 1, "sink_delta_um": 0.0, "antenna_reopen": 0, "hold_delta": -380}, "label": "uncertain"},
        {"features": {"family": "v1", "touches_neighbor": 1, "sink_delta_um": 155.0, "antenna_reopen": 1, "hold_delta": 98}, "label": "likely_clear_loser"},
        {"features": {"family": "v2", "touches_observe": 0, "sink_delta_um": -14.0, "antenna_reopen": 0, "hold_delta": -395}, "label": "worth_alpha_run"},
        {"features": {"family": "v2", "touches_retire": 0, "sink_delta_um": -8.0, "antenna_reopen": 0, "hold_delta": -390}, "label": "worth_alpha_run"},
        {"features": {"family": "v2", "touches_command": 1, "sink_delta_um": 12.0, "antenna_reopen": 0, "hold_delta": -395}, "label": "uncertain"},
    ]


def load_records(args):
    if args.smoke:
        return smoke_records()

    with open(args.features, "r", encoding="utf-8") as handle:
        payload = json.load(handle)

    records = payload if isinstance(payload, list) else payload.get("records", [])
    normalized = []
    for record in records:
        if record.get("datasetSplit") == "eval":
            continue
        features = record.get("metrics") or record.get("features") or record.get("featureVector") or {}
        label = record.get("outcome") or record.get("label") or record.get("classification")
        if not isinstance(features, dict) or not label:
            continue
        normalized.append({"features": features, "label": str(label)})
    return normalized


def main():
    parser = argparse.ArgumentParser(description="Train an XGBoost triage model from silicon run data")
    parser.add_argument("--features", help="Path to normalized features JSON")
    parser.add_argument("--out-model", required=True, help="Path to write model bundle (.joblib)")
    parser.add_argument("--out-summary", required=True, help="Path to write training summary JSON")
    parser.add_argument("--smoke", action="store_true", help="Use built-in smoke data for quick demo")
    args = parser.parse_args()

    records = load_records(args)
    if not records:
        raise SystemExit("no training records available")

    labels = [record["label"] for record in records]
    classes = sorted(set(labels))
    class_to_index = {label: index for index, label in enumerate(classes)}
    y = [class_to_index[label] for label in labels]

    vectorizer = DictVectorizer(sparse=False)
    x = vectorizer.fit_transform([record["features"] for record in records])

    model = XGBClassifier(
        n_estimators=24,
        max_depth=4,
        learning_rate=0.25,
        subsample=1.0,
        colsample_bytree=1.0,
        objective="multi:softprob",
        num_class=len(classes),
        eval_metric="mlogloss",
        random_state=42,
    )
    model.fit(x, y)
    predictions = model.predict(x)
    if hasattr(predictions, "ndim") and int(getattr(predictions, "ndim", 1)) > 1:
        predictions = predictions.argmax(axis=1)
    accuracy = float(accuracy_score(y, predictions))

    os.makedirs(os.path.dirname(os.path.abspath(args.out_model)), exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(args.out_summary)), exist_ok=True)

    joblib.dump({
        "model": model,
        "vectorizer": vectorizer,
        "class_labels": classes,
        "trained_at": now_iso(),
        "smoke_mode": bool(args.smoke),
    }, args.out_model)

    summary = {
        "schemaVersion": "open-silicon-triage.training.v1",
        "trainedAt": now_iso(),
        "smokeMode": bool(args.smoke),
        "recordCount": len(records),
        "featureCount": len(vectorizer.feature_names_),
        "classLabels": classes,
        "trainingAccuracy": accuracy,
        "modelBinaryPath": args.out_model,
    }

    with open(args.out_summary, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
