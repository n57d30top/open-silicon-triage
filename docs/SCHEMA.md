# Open Silicon Triage — Schema Documentation

## Overview

Every run record in the Open Silicon Triage corpus follows a standardized JSON schema. This ensures that data from different contributors, tools, and PDKs can be trained together.

## Record Schema (`open-silicon-triage.corpus.v1`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `schemaVersion` | string | ✅ | Always `open-silicon-triage.corpus.v1` |
| `recordId` | string | ✅ | Unique record identifier |
| `project` | string | ✅ | Project or organization name |
| `variant` | string | ✅ | Design variant identifier |
| `pdk` | string | ✅ | Process Design Kit (e.g. `sky130A`, `gf180mcuD`) |
| `tool` | string | ✅ | EDA tool and version |
| `metrics` | object | ✅ | Physical metrics (see below) |
| `outcome` | enum | ✅ | `negative_evidence`, `strategic_progress`, or `promoted_winner` |
| `observedAt` | string | ✅ | ISO 8601 timestamp |
| `contributor` | string | ❌ | Contributor name (default: `anonymous`) |

## Metrics Object

| Metric | Type | Unit | Description |
|--------|------|------|-------------|
| `hpwlUm` | number | µm | Half-Perimeter Wire Length — total estimated wire length |
| `averageSinkWireLengthUm` | number | µm | Average sink (capacitive load) wire length |
| `setupWnsNs` | number | ns | Worst Negative Slack for setup timing (negative = violation) |
| `setupViolations` | integer | count | Number of setup timing violations |
| `holdViolations` | integer | count | Number of hold timing violations |
| `antennaViolations` | integer | count | Number of antenna rule violations |
| `maxCapViolations` | integer | count | Number of max capacitance violations (optional) |
| `maxSlewViolations` | integer | count | Number of max slew violations (optional) |

## Outcome Labels

- **`negative_evidence`** — The design failed physical verification or showed regression
- **`strategic_progress`** — Partial improvement; useful for learning but not promoted
- **`promoted_winner`** — Passed all checks; promoted as new baseline champion

## Feature Extraction

For ML training, the CLI tools extract features from the raw metrics. The current feature set includes:
- Delta values (candidate metric minus baseline metric)
- Binary flags (e.g. `antenna_reopen`, `hold_regression`)
- Architecture family indicators
- Mutation strategy type indicators
