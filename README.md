# Open Silicon Triage

**The open-source toolkit for smarter OpenLane runs — check before, during, and after.**

> Stop wasting 30 minutes on runs that were doomed from the start.

[![License: Dual](https://img.shields.io/badge/License-Dual%20(Academic%20Free%20%2F%20Commercial%20Licensed)-blue)](#license)

## What is this?

Open Silicon Triage gives you three checkpoints around every OpenLane run:

```
BEFORE your run          DURING your run           AFTER your run
┌──────────────┐         ┌───────────────┐         ┌──────────────────┐
│ Config Check │         │ Early Abort   │         │ Benchmark        │
│              │         │               │         │                  │
│ "80% util +  │         │ "WNS is -18ns │         │ "Your HPWL is    │
│  10ns clock? │         │  after place— │         │  better than 75% │
│  Don't even  │         │  abort now,   │         │  of community    │
│  start."     │         │  save 25 min" │         │  runs."          │
└──────────────┘         └───────────────┘         └──────────────────┘
     0 min                    5 min                     30 min
```

### The Problem
Hundreds of engineers run OpenLane daily. Most runs fail. Nobody shares what went wrong, so everyone repeats the same mistakes.

### The Solution
Three tools that catch problems at every stage, backed by a growing, **100% genuine, zero-trust community database** of real OpenLane run results (no synthetic or "assumed" data).

**10/10 Quality Features:**
- **Learns from Data:** The pre-run config checker learns safe boundaries dynamically from community successes and failures.
- **Apples-to-Apples:** The benchmarking tool compares your run specifically against identical architectures (`--variant`) so you get a realistic ranking.
- **Robust:** Fully tested CI pipeline ensures Python 3.10-3.12 compatibility.

## Quick Start

```bash
git clone https://github.com/n57d30top/open-silicon-triage.git
cd open-silicon-triage
pip install -r cli/requirements.txt
```

### 1. Before your run — Check your config

Point it at your OpenLane config file. It learns safe thresholds from the community corpus and warns you about risky parameter combinations:

```bash
python cli/analyze-config.py --config ./openlane/config.json

# Or specify parameters directly:
python cli/analyze-config.py --clock-period 10 --utilization 0.70 --pdk sky130A
```

> *"🔴 HIGH RISK: Utilization 70% exceeds the typical max of 65% for sky130A."*
> *"🔴 HIGH RISK: High utilization + aggressive clock is the #1 cause of failed runs."*

### 2. During your run — Early abort check

After placement finishes (~5 min), check if it's worth continuing:

```bash
python cli/early-check.py --run-dir ./runs/RUN_2026.03.27
```

> *"🔴 ABORT: Setup WNS is -18.4 ns — too negative to recover during routing. Save 25 minutes."*

### 3. After your run — Benchmark against the community

See how your results compare to the community corpus. You can even filter by your specific design architecture (`--variant`) to get an apples-to-apples comparison!

```bash
python cli/benchmark.py --run-dir ./runs/RUN_2026.03.27 --variant "picorv32"

# Or with manual numbers:
python cli/benchmark.py --metrics '{"hpwl": 10937, "wns": -7.93, "setup": 459, "hold": 0, "antenna": 0}'
```

> *"✅ EXCELLENT: Your HPWL is better than 75% of similar 'picorv32' runs."*
> *"🔴 POOR: Setup violations are in the bottom quartile."*

### 4. (Bonus) ML Predictor

Train and run the XGBoost-based triage predictor on the corpus:

```bash
python cli/train.py --features corpus/seed-corpus.json --out-model my-model.joblib --out-summary results.json
python cli/predict.py --model my-model.joblib --features my-run.json --out-summary verdict.json
```

## How it works
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

## 🛠️ Use It For Your Own Designs

Want to use the predictor to check your own OpenLane runs? Here's how:

### Step 1: Train a model on the community corpus

This takes a few seconds and creates a trained model file:

```bash
python cli/train.py --features corpus/seed-corpus.json --out-model my-model.joblib --out-summary train-results.json
```

> **What this does:** Reads all genuine zero-trust community run records and trains an XGBoost model that learns which metric patterns lead to success or failure.

### Step 2: Check your design

After an OpenLane run, use `ingest.py` to extract your metrics, then `predict.py` to get a verdict:

```bash
# Extract metrics from your OpenLane run folder:
python cli/ingest.py --openlane-dir ./runs/RUN_2026.03.27 --variant "my-design" --out my-run.json

# Ask the predictor:
python cli/predict.py --model my-model.joblib --features my-run.json --out-summary verdict.json
```

The output will tell you for each design:
- **`reject`** → Your metrics look like those of designs that failed. Consider changing your approach before running again.
- **`review`** → The model isn't sure. Check the weak spots manually.
- **`run`** → Your metrics look like those of designs that succeeded. Go for the full run.

### Step 3 (optional): Retrain as the corpus grows

As more people contribute runs, download the latest corpus and retrain:

```bash
git pull
python cli/train.py --features corpus/seed-corpus.json --out-model my-model.joblib --out-summary train-results.json
```

More data = better predictions. It's that simple.

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

### How to contribute a run

**Step 1:** Clone this repo (if you haven't already):
```bash
git clone https://github.com/n57d30top/open-silicon-triage.git
```

**Step 2:** After your OpenLane run finishes, find the run folder. It's usually something like `./runs/RUN_2026.03.27_15-30-00` and contains subfolders like `reports/` and `logs/`.

**Step 3:** Run this one command — replace the path with your actual run folder, and give your design a name:
```bash
python open-silicon-triage/cli/submit.py ./runs/RUN_2026.03.27 --variant "my-design-name"
```

| Part | What it means |
|------|---------------|
| `python` | Run a Python script |
| `open-silicon-triage/cli/submit.py` | The submit script from the cloned repo |
| `./runs/RUN_2026.03.27` | **Your** OpenLane run output folder |
| `--variant "my-design-name"` | A name for your design (e.g. "picorv32", "aes-128") |

**That's it.** The script automatically:
1. 🔍 Scans your run folder for OpenLane reports and logs
2. 📊 Extracts the key metrics (wire length, timing, violations)
3. 🔒 Strips all local file paths — **your design files stay completely private**. Only anonymous performance numbers are shared.
4. 📤 Creates a Pull Request on GitHub (requires [GitHub CLI](https://cli.github.com))

> **No GitHub CLI?** No problem — the script will print the data as JSON so you can submit it manually.

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
