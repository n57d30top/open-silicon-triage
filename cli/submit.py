#!/usr/bin/env python3
"""
Open Silicon Triage — One-command submission of OpenLane run results.

Usage:
    python submit.py ./runs/RUN_2026.03.27
    python submit.py ./runs/RUN_2026.03.27 --variant "picorv32" --outcome promoted_winner

No API keys needed — creates a fork + PR via GitHub CLI (gh).
Falls back to printing the record if gh is not installed.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone


REPO = "n57d30top/open-silicon-triage"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def find_metric_files(run_dir: str) -> dict:
    """Auto-detect and extract metrics from an OpenLane or ORFS run directory."""
    metrics = {}

    # --- ORFS Flow Detection ---
    orfs_metrics = os.path.join(run_dir, "reports", "metrics.json")
    if os.path.exists(orfs_metrics):
        try:
            with open(orfs_metrics, "r", encoding="utf-8") as f:
                d = json.load(f)
            if "route__wirelength__estimated" in d: metrics["hpwlUm"] = float(d["route__wirelength__estimated"])
            if "timing__setup__ws" in d: metrics["setupWnsNs"] = float(d["timing__setup__ws"])
            if "timing__setup__vio" in d: metrics["setupViolations"] = int(d["timing__setup__vio"])
            if "timing__hold__vio" in d: metrics["holdViolations"] = int(d["timing__hold__vio"])
            if "design__violations" in d: metrics["antennaViolations"] = int(d["design__violations"])
            if "cts__clock__wirelength" in d: metrics["averageSinkWireLengthUm"] = float(d["cts__clock__wirelength"])
            if metrics: return metrics
        except Exception:
            pass

    # --- HPWL: from placement logs or final summary ---
    for csv_name in ["metrics.csv", "final_summary_report.csv"]:
        csv_path = os.path.join(run_dir, "reports", csv_name)
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            if len(lines) >= 2:
                headers = [h.strip().lower() for h in lines[0].split(",")]
                values = [v.strip() for v in lines[1].split(",")]
                row = dict(zip(headers, values))
                if "hpwl" in row:
                    metrics["hpwlUm"] = float(row["hpwl"])
                if "wns" in row:
                    metrics["setupWnsNs"] = float(row["wns"])
                elif "setup_wns" in row:
                    metrics["setupWnsNs"] = float(row["setup_wns"])
                if "antenna_violations" in row:
                    metrics["antennaViolations"] = int(float(row["antenna_violations"]))
            break

    # --- Setup/Hold violations: from STA logs ---
    for subdir in ["signoff", "cts", "routing", ""]:
        for log_name in ["sta.log", "opensta.log", "sta-rcx.log"]:
            log_path = os.path.join(run_dir, "logs", subdir, log_name) if subdir else os.path.join(run_dir, "logs", log_name)
            if not os.path.exists(log_path):
                continue
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read()
            setup_match = re.search(r"worst\s+slack.*?(-?[\d.]+)", content, re.IGNORECASE)
            if setup_match and "setupWnsNs" not in metrics:
                metrics["setupWnsNs"] = float(setup_match.group(1))
            for pattern in [r"(\d+)\s+violation", r"setup\D+(\d+)", r"Setup:\s*(\d+)"]:
                m = re.search(pattern, content, re.IGNORECASE)
                if m and "setupViolations" not in metrics:
                    metrics["setupViolations"] = int(m.group(1))
            for pattern in [r"hold\D+(\d+)", r"Hold:\s*(\d+)"]:
                m = re.search(pattern, content, re.IGNORECASE)
                if m and "holdViolations" not in metrics:
                    metrics["holdViolations"] = int(m.group(1))
            break

    # --- Antenna: from DRC ---
    for drc_name in ["antenna.rpt", "drc.rpt"]:
        drc_path = os.path.join(run_dir, "reports", "signoff", drc_name)
        if os.path.exists(drc_path):
            with open(drc_path, "r", encoding="utf-8") as f:
                content = f.read()
            antenna_matches = re.findall(r"antenna", content, re.IGNORECASE)
            if "antennaViolations" not in metrics:
                metrics["antennaViolations"] = len(antenna_matches)
            break

    # --- Sink wire length: from CTS report ---
    for cts_name in ["cts.rpt", "clock_tree.rpt"]:
        cts_path = os.path.join(run_dir, "reports", "cts", cts_name)
        if not os.path.exists(cts_path):
            cts_path = os.path.join(run_dir, "reports", cts_name)
        if os.path.exists(cts_path):
            with open(cts_path, "r", encoding="utf-8") as f:
                content = f.read()
            sink_match = re.search(r"avg.*?sink.*?wire.*?length.*?([\d.]+)", content, re.IGNORECASE)
            if sink_match:
                metrics["averageSinkWireLengthUm"] = float(sink_match.group(1))
            break

    return metrics


def build_record(metrics: dict, variant: str, pdk: str, tool: str, outcome: str, contributor: str) -> dict:
    record_hash = hashlib.sha256(json.dumps(metrics, sort_keys=True).encode()).hexdigest()[:12]
    return {
        "schemaVersion": "open-silicon-triage.corpus.v1",
        "recordId": f"ost-{record_hash}",
        "project": "community",
        "variant": variant,
        "pdk": pdk,
        "tool": tool,
        "metrics": {
            "hpwlUm": metrics.get("hpwlUm", 0),
            "averageSinkWireLengthUm": metrics.get("averageSinkWireLengthUm", 0),
            "setupWnsNs": metrics.get("setupWnsNs", 0),
            "setupViolations": metrics.get("setupViolations", 0),
            "holdViolations": metrics.get("holdViolations", 0),
            "antennaViolations": metrics.get("antennaViolations", 0),
        },
        "outcome": outcome,
        "observedAt": now_iso(),
        "contributor": contributor,
    }


def has_gh_cli() -> bool:
    try:
        subprocess.run(["gh", "--version"], capture_output=True, check=True)
        return True
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False


def submit_via_gh(record: dict, variant: str) -> bool:
    """Submit via GitHub CLI: fork → branch → commit → PR."""
    with tempfile.TemporaryDirectory() as tmpdir:
        print("📥 Cloning repository...")
        result = subprocess.run(
            ["gh", "repo", "fork", REPO, "--clone", "--remote"],
            cwd=tmpdir, capture_output=True, text=True
        )
        repo_dir = os.path.join(tmpdir, "open-silicon-triage")
        if not os.path.isdir(repo_dir):
            # Try cloning directly
            subprocess.run(
                ["gh", "repo", "clone", REPO],
                cwd=tmpdir, capture_output=True, text=True
            )

        if not os.path.isdir(repo_dir):
            return False

        # Write record
        safe_variant = re.sub(r"[^a-z0-9_-]", "-", variant.lower())[:30]
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        filename = f"corpus/community-{safe_variant}-{timestamp}.json"
        filepath = os.path.join(repo_dir, filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, indent=2)
            f.write("\n")

        # Branch, commit, push, PR
        branch = f"submit-{safe_variant}-{timestamp}"
        subprocess.run(["git", "checkout", "-b", branch], cwd=repo_dir, capture_output=True)
        subprocess.run(["git", "add", filename], cwd=repo_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", f"feat(corpus): add community run ({variant})"],
            cwd=repo_dir, capture_output=True
        )
        subprocess.run(["git", "push", "origin", branch], cwd=repo_dir, capture_output=True)

        pr_result = subprocess.run(
            ["gh", "pr", "create",
             "--title", f"Add community run: {variant}",
             "--body", f"Auto-submitted via `submit.py`.\n\n```json\n{json.dumps(record, indent=2)}\n```",
             "--repo", REPO],
            cwd=repo_dir, capture_output=True, text=True
        )

        if pr_result.returncode == 0:
            print(f"🔗 Pull Request created: {pr_result.stdout.strip()}")
            return True
        else:
            print(f"⚠️  PR creation output: {pr_result.stderr.strip()}")
            return False

    return False


def main():
    parser = argparse.ArgumentParser(
        description="Submit your OpenLane run to the Open Silicon Triage community corpus",
        epilog="Example: python submit.py ./runs/RUN_2026.03.27 --variant picorv32"
    )
    parser.add_argument("run_dir", help="Path to your OpenLane run directory")
    parser.add_argument("--variant", default="unknown", help="Design name (e.g. 'picorv32', 'aes-128')")
    parser.add_argument("--pdk", default="sky130A", help="PDK used (default: sky130A)")
    parser.add_argument("--tool", default="OpenLane 2.x", help="EDA tool used")
    parser.add_argument("--outcome", choices=["negative_evidence", "strategic_progress", "promoted_winner"],
                        default="negative_evidence", help="How did the run go?")
    parser.add_argument("--contributor", default="anonymous", help="Your name or GitHub handle")
    parser.add_argument("--dry-run", action="store_true", help="Just print the record, don't submit")
    args = parser.parse_args()

    if not os.path.isdir(args.run_dir):
        print(f"❌ Directory not found: {args.run_dir}")
        sys.exit(1)

    print(f"🔍 Scanning {args.run_dir} ...")
    metrics = find_metric_files(args.run_dir)

    found = sum(1 for v in metrics.values() if v != 0)
    print(f"📊 Found {found} metrics: {list(metrics.keys())}")

    if found == 0:
        print("⚠️  No metrics found. Are you sure this is an OpenLane run directory?")
        print("   Expected structure: runs/RUN_*/reports/ and runs/RUN_*/logs/")
        sys.exit(1)

    record = build_record(metrics, args.variant, args.pdk, args.tool, args.outcome, args.contributor)

    print("\n" + json.dumps(record, indent=2))

    if args.dry_run:
        print("\n🏁 Dry run — record not submitted.")
        return

    print("\n📤 Submitting to Open Silicon Triage...")

    if has_gh_cli():
        if submit_via_gh(record, args.variant):
            print("\n✅ Done! Your run has been submitted. Thank you! 🙏")
        else:
            print("\n⚠️  Automatic PR failed. You can submit manually:")
            print(f"   1. Copy the JSON above")
            print(f"   2. Add it as a file in corpus/ via GitHub web UI")
            print(f"   3. Open a Pull Request")
    else:
        print("\n💡 GitHub CLI (gh) not installed. To submit automatically:")
        print("   Install: https://cli.github.com")
        print("   Then re-run this script.")
        print("\n   Or submit manually:")
        print(f"   1. Copy the JSON above")
        print(f"   2. Go to https://github.com/{REPO}")
        print(f"   3. Add a file in corpus/ and open a Pull Request")


if __name__ == "__main__":
    main()
