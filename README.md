# Open Silicon Triage

**The first open-source, community-driven ML predictor for chip design outcomes.**

> Before you burn 30 minutes on an OpenLane run, ask the model:  
> *"Will this design work?"*

[![License: Dual](https://img.shields.io/badge/License-Dual%20(Academic%20Free%20%2F%20Commercial%20Licensed)-blue)](#license)

## What is this?

Open Silicon Triage is a lightweight ML tool that predicts whether a chip layout will pass physical verification (timing, antenna, hold) **before** you run the full EDA flow. It learns from a growing corpus of real OpenLane/OpenROAD run results contributed by the community.

### The Problem
Every day, hundreds of students and engineers run OpenLane to synthesize chip designs. Most runs fail. The knowledge from those failures is lost — nobody else learns from them.

### The Solution
Open Silicon Triage collects anonymized run metrics (HPWL, sink wire length, timing slack, violations) into an open database. An XGBoost model trained on this data predicts outcomes for new designs with **92%+ accuracy** on the seed corpus.

## Quick Start

### 1. Install

```bash
git clone https://github.com/n57d30top/open-silicon-triage.git
cd open-silicon-triage
pip install -r cli/requirements.txt
```

### 2. Train (smoke test — no data needed)

```bash
python cli/train.py --smoke --out-model tmp/model.joblib --out-summary tmp/train.json
```

### 3. Evaluate

```bash
python cli/eval.py --smoke --model tmp/model.joblib --out-summary tmp/eval.json
```

### 4. Predict

```bash
python cli/predict.py --model tmp/model.joblib --features corpus/seed-corpus.json --out-summary tmp/predict.json
```

### 5. Contribute your own runs

```bash
# From an OpenLane run directory:
python cli/ingest.py --openlane-dir ./runs/RUN_2026.03.27 --out corpus/my-run.json

# Or manually:
python cli/ingest.py \
  --metrics '{"hpwl": 10937, "sink": 312, "wns": -7.93, "setup": 459, "hold": 0, "antenna": 0}' \
  --variant "my-riscv-core" \
  --outcome promoted_winner \
  --out corpus/my-run.json
```

## How it works

```
┌─────────────────────┐     ┌──────────────┐     ┌───────────────────┐
│  Your Design (.v)   │────▶│   OpenLane    │────▶│  Run Metrics      │
│                     │     │   Run         │     │  (HPWL, WNS, ...) │
└─────────────────────┘     └──────────────┘     └─────────┬─────────┘
                                                           │
                                                           ▼
                                                 ┌─────────────────────┐
                                                 │  Open Silicon       │
                                                 │  Triage Predictor   │
                                                 │                     │
                                                 │  → reject (68%)     │
                                                 │  → review (15%)     │
                                                 │  → run    (7%)      │
                                                 └─────────────────────┘
```

**Predictions:**
- **reject** — This design will almost certainly fail. Don't waste compute.
- **review** — Uncertain. Worth a closer look before committing resources.
- **run** — Looks promising. Run the full flow.

## Corpus Statistics (Seed)

| Metric | Value |
|--------|-------|
| Total Records | 76 |
| Training Accuracy | 92.4% |
| Evaluation Accuracy | 100% (21 held-out samples) |
| Model | XGBoost (24 estimators, depth 4) |
| PDK | sky130A |
| Architecture Types | MAC arrays, inner-cores, systolic tiles |

## Schema

Every record in the corpus follows a simple JSON schema. See [`schema/dataset.schema.json`](schema/dataset.schema.json) for the full specification.

**Core metrics per run:**
- `hpwlUm` — Half-Perimeter Wire Length (micrometers)
- `averageSinkWireLengthUm` — Average capacitive load wire length
- `setupWnsNs` — Worst Negative Slack for setup timing
- `setupViolations` — Number of setup timing violations
- `holdViolations` — Number of hold timing violations
- `antennaViolations` — Number of antenna rule violations

## 📡 Community-Driven — This Is Where You Come In

The predictor is only as good as the data behind it. Right now it knows 76 runs from one architecture family. **But it's designed to learn from all of you.**

Think of it like **Waze, but for chip design** — the more people share their run data, the better the routing predictions get for everyone. At 1,000 records it'll be scary good. At 10,000 it could become the standard pre-check for every OpenLane user worldwide.

### Contributing a run takes 30 seconds

```bash
# Directly from your OpenLane run directory:
python cli/ingest.py --openlane-dir ./runs/RUN_2026.03.27 \
  --variant "my-riscv-core" --outcome negative_evidence \
  --out corpus/my-run.json

# Or manually if you just have the numbers:
python cli/ingest.py \
  --metrics '{"hpwl": 12345, "sink": 400, "wns": -5.0, "setup": 200, "hold": 0, "antenna": 3}' \
  --variant "my-crypto-block" --outcome negative_evidence \
  --out corpus/my-run.json
```

Then just open a PR adding your JSON file to `corpus/`. The ingest tool **automatically strips all local paths** — your IP and file structure stay private. Only the raw physical metrics go into the database.

### What we especially need

- 🔲 **RISC-V cores** (any size — from picorv32 to full CVA6)
- 🔐 **Crypto/AES blocks**
- 📡 **DSP designs**
- 🏭 **Runs on gf180 or IHP PDKs** (we're sky130-only right now)
- ❌ **Failed runs** — these are just as valuable as successes!

Every single run — pass or fail — makes the predictor smarter for the entire community.

See [CONTRIBUTING.md](CONTRIBUTING.md) for full details.

## License

This project uses a **dual license**:

- **Academic & Open-Source Use:** Free under the [Academic Free License](LICENSE.md)
- **Commercial Use:** Requires a separate license agreement

See [LICENSE.md](LICENSE.md) for full details.

## Acknowledgments

Built with data from [OpenLane](https://github.com/The-OpenROAD-Project/OpenLane), [OpenROAD](https://github.com/The-OpenROAD-Project/OpenROAD), and the [sky130 PDK](https://github.com/google/skywater-pdk).

Seed corpus contributed by the Sovereign Factory autonomous chip design project.
