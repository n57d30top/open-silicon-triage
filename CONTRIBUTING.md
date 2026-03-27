# Contributing to Open Silicon Triage

Thank you for helping build the world's first open chip design outcome database!

## How to Contribute Run Data

### Option A: From an OpenLane run

```bash
python cli/ingest.py \
  --openlane-dir ./runs/YOUR_RUN \
  --project "your-project-name" \
  --variant "your-design-variant" \
  --pdk sky130A \
  --outcome negative_evidence \
  --out corpus/your-run-description.json
```

### Option B: Manual entry

```bash
python cli/ingest.py \
  --metrics '{"hpwl": 12345, "sink": 400, "wns": -5.0, "setup": 200, "hold": 0, "antenna": 3}' \
  --project "your-project" \
  --variant "your-design" \
  --outcome strategic_progress \
  --out corpus/your-run-description.json
```

### Outcome Labels

- **`negative_evidence`** — The design failed or showed no improvement over the baseline
- **`strategic_progress`** — The design showed improvement in some metrics but wasn't promoted
- **`promoted_winner`** — The design passed all checks and was promoted as the new baseline

### Submit

1. Fork this repository
2. Add your record(s) to the `corpus/` directory
3. Open a Pull Request with a brief description

## Code Contributions

- Bug fixes and improvements to the CLI tools are welcome
- New ingest parsers for other EDA tools (Yosys, Genus, Innovus) are especially valuable
- Please include tests for new functionality

## Data Privacy

- **Do not include** file paths, IP addresses, proprietary design names, or internal identifiers
- Use the `--project` and `--contributor anonymous` flags to control what is shared
- The `ingest.py` tool strips local paths by default

## Questions?

Open an issue on GitHub.
