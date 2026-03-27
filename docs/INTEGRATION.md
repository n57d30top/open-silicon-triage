# Integration Guide — Open Silicon Triage + OpenLane

## After an OpenLane Run

Once your OpenLane run completes, you can automatically ingest the results:

```bash
python cli/ingest.py --openlane-dir /path/to/runs/RUN_TAG --out corpus/my-run.json
```

The ingest tool will attempt to parse:
- `reports/final_summary_report.csv` or `reports/metrics.csv` for HPWL and WNS
- `logs/signoff/sta.log` for setup and hold violation counts
- Antenna violation counts from DRC reports

## CI/CD Integration

Add this to your OpenLane CI pipeline to auto-report every run:

```yaml
# .github/workflows/openlane.yml
- name: Ingest triage data
  run: |
    python open-silicon-triage/cli/ingest.py \
      --openlane-dir ./runs/${{ env.RUN_TAG }} \
      --project "${{ github.repository }}" \
      --variant "${{ env.DESIGN_NAME }}" \
      --outcome negative_evidence \
      --out triage-report.json
```

## Pre-Run Prediction

Before committing to a full OpenLane run, predict the outcome:

```bash
# 1. Create a feature file from your design parameters
# 2. Run prediction
python cli/predict.py \
  --model models/latest.joblib \
  --features my-design-features.json \
  --out-summary prediction.json
```

If the prediction says `reject` with high confidence, consider modifying your design first.

## Supported Tools

| Tool | Ingest Support | Notes |
|------|---------------|-------|
| OpenLane 1.x | ✅ Partial | Reads `final_summary_report.csv` |
| OpenLane 2.x | ✅ Full | Reads `metrics.csv` + STA logs |
| Manual Entry | ✅ Full | Use `--metrics` flag |
| Yosys/OpenROAD (standalone) | 🔜 Planned | Contributions welcome |
