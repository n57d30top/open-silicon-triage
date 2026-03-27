#!/usr/bin/env python3
"""Open Silicon Triage — Predict outcome for new chip design candidates."""
import argparse
import json
import os
from datetime import datetime, timezone

import joblib


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main():
    parser = argparse.ArgumentParser(description="Predict triage outcome for new candidates")
    parser.add_argument("--model", required=True, help="Path to trained model bundle (.joblib)")
    parser.add_argument("--features", required=True, help="Path to feature payload JSON")
    parser.add_argument("--out-summary", required=True, help="Path to prediction summary JSON")
    args = parser.parse_args()

    with open(args.features, "r", encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload if isinstance(payload, list) else payload.get("records", [])
    if not records:
        raise SystemExit("no prediction records available")

    normalized = []
    for record in records:
        features = record.get("features") or record.get("featureVector") or {}
        if not isinstance(features, dict):
            continue
        normalized.append(features)
    if not normalized:
        raise SystemExit("no valid prediction feature vectors available")

    bundle = joblib.load(args.model)
    vectorizer = bundle["vectorizer"]
    model = bundle["model"]
    class_labels = list(bundle["class_labels"])
    matrix = vectorizer.transform(normalized)
    probabilities = model.predict_proba(matrix)
    predicted = model.predict(matrix)
    if hasattr(predicted, "ndim") and int(getattr(predicted, "ndim", 1)) > 1:
        predicted = predicted.argmax(axis=1)

    # Map prediction class → human-readable decision
    DECISION_MAP = {
        "likely_clear_loser": "reject",
        "uncertain": "review",
        "worth_alpha_run": "run",
    }

    predictions = []
    for index, prediction in enumerate(predicted):
        class_index = int(prediction)
        probability_vector = probabilities[index]
        probability_by_class = {
            class_labels[label_index]: float(round(float(probability_vector[label_index]), 6))
            for label_index in range(len(class_labels))
        }
        pred_class = class_labels[class_index]
        predictions.append({
            "predictionClass": pred_class,
            "decision": DECISION_MAP.get(pred_class, "review"),
            "confidence": probability_by_class[pred_class],
            "probabilityByClass": probability_by_class,
        })

    os.makedirs(os.path.dirname(os.path.abspath(args.out_summary)), exist_ok=True)
    summary = {
        "schemaVersion": "open-silicon-triage.prediction.v1",
        "generatedAt": now_iso(),
        "modelPath": args.model,
        "predictionCount": len(predictions),
        "predictions": predictions,
    }
    with open(args.out_summary, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)
        handle.write("\n")

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
