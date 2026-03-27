#!/usr/bin/env python3
"""Tests for Open Silicon Triage CLI tools."""
import importlib.util
import json
import os
import sys
import tempfile
from unittest.mock import patch
import io

os.environ["OMP_NUM_THREADS"] = "1"

REPO_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI_DIR = os.path.join(REPO_DIR, "cli")
CORPUS_PATH = os.path.join(REPO_DIR, "corpus", "seed-corpus.json")

# Import all CLI modules dynamically to run them in-process (avoid Windows subprocess hang with XGBoost)
def load_cli_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

train_mod = load_cli_module("train", os.path.join(CLI_DIR, "train.py"))
eval_mod = load_cli_module("eval", os.path.join(CLI_DIR, "eval.py"))
predict_mod = load_cli_module("predict", os.path.join(CLI_DIR, "predict.py"))
ingest_mod = load_cli_module("ingest", os.path.join(CLI_DIR, "ingest.py"))
analyze_config_mod = load_cli_module("analyze_config", os.path.join(CLI_DIR, "analyze-config.py"))
benchmark_mod = load_cli_module("benchmark", os.path.join(CLI_DIR, "benchmark.py"))


def run_cli_in_process(module, args, expect_fail=False):
    """Run a CLI directly via its main() function with mocked sys.argv."""
    stdout_capture = io.StringIO()
    stderr_capture = io.StringIO()
    
    raised_exit = False
    exit_code = 0
    
    with patch("sys.argv", [module.__file__] + args), \
         patch("sys.stdout", stdout_capture), \
         patch("sys.stderr", stderr_capture):
        try:
            module.main()
        except SystemExit as e:
            raised_exit = True
            exit_code = e.code if isinstance(e.code, int) else (1 if e.code else 0)
            if expect_fail and exit_code != 0:
                pass # expected
            elif not expect_fail and exit_code != 0:
                raise AssertionError(f"{module.__name__} failed with code {exit_code}: {e}\n{stderr_capture.getvalue()}")
        except Exception as e:
            if not expect_fail:
                raise AssertionError(f"{module.__name__} raised exception: {e}\n{stderr_capture.getvalue()}")
    
    stdout = stdout_capture.getvalue()
    stderr = stderr_capture.getvalue()
    
    if not expect_fail and not raised_exit and exit_code != 0:
         raise AssertionError(f"{module.__name__} failed silently?\n{stderr}")
         
    return {"stdout": stdout, "stderr": stderr, "code": exit_code}


# ===========================================================================
# train.py
# ===========================================================================

def test_train_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = os.path.join(tmpdir, "model.joblib")
        summary_path = os.path.join(tmpdir, "summary.json")
        run_cli_in_process(train_mod, [
            "--smoke",
            "--out-model", model_path,
            "--out-summary", summary_path,
        ])
        assert os.path.exists(model_path)
        assert os.path.exists(summary_path)
        summary = json.loads(open(summary_path).read())
        assert summary["recordCount"] == 9
        assert summary["classLabels"] == ["likely_clear_loser", "uncertain", "worth_alpha_run"]
        print(f"  ✅ train smoke: {summary['recordCount']} records, {summary['trainingAccuracy']:.0%} accuracy")


def test_train_corpus():
    if not os.path.exists(CORPUS_PATH):
        print("  ⏭️  train corpus: skipped (no seed corpus)")
        return
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = os.path.join(tmpdir, "model.joblib")
        summary_path = os.path.join(tmpdir, "summary.json")
        run_cli_in_process(train_mod, [
            "--features", CORPUS_PATH,
            "--out-model", model_path,
            "--out-summary", summary_path,
        ])
        summary = json.loads(open(summary_path).read())
        assert summary["recordCount"] >= 50
        assert summary["trainingAccuracy"] >= 0.85
        print(f"  ✅ train corpus: {summary['recordCount']} records, {summary['trainingAccuracy']:.0%} accuracy")

# ===========================================================================
# eval.py
# ===========================================================================

def test_eval_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = os.path.join(tmpdir, "model.joblib")
        run_cli_in_process(train_mod, ["--smoke", "--out-model", model_path, "--out-summary", os.path.join(tmpdir, "t.json")])
        eval_path = os.path.join(tmpdir, "eval.json")
        run_cli_in_process(eval_mod, ["--smoke", "--model", model_path, "--out-summary", eval_path])
        summary = json.loads(open(eval_path).read())
        assert summary["accuracy"] >= 0.9
        print(f"  ✅ eval smoke: {summary['recordCount']} records, {summary['accuracy']:.0%} accuracy")

# ===========================================================================
# predict.py
# ===========================================================================

def test_predict_smoke():
    with tempfile.TemporaryDirectory() as tmpdir:
        model_path = os.path.join(tmpdir, "model.joblib")
        run_cli_in_process(train_mod, ["--smoke", "--out-model", model_path, "--out-summary", os.path.join(tmpdir, "t.json")])
        if not os.path.exists(CORPUS_PATH):
            return
        predict_path = os.path.join(tmpdir, "predict.json")
        run_cli_in_process(predict_mod, [
            "--model", model_path,
            "--features", CORPUS_PATH,
            "--out-summary", predict_path,
        ])
        summary = json.loads(open(predict_path).read())
        assert summary["predictionCount"] > 0
        print(f"  ✅ predict: {summary['predictionCount']} predictions, all valid")

# ===========================================================================
# ingest.py
# ===========================================================================

def test_ingest_manual():
    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = os.path.join(tmpdir, "record.json")
        run_cli_in_process(ingest_mod, [
            "--metrics", '{"hpwl": 10000, "sink": 300, "wns": -5.0, "setup": 200, "hold": 0, "antenna": 0}',
            "--variant", "test-design",
            "--pdk", "sky130A",
            "--out", out_path,
        ])
        record = json.loads(open(out_path).read())
        assert record["schemaVersion"] == "open-silicon-triage.corpus.v1"
        assert record["metrics"]["hpwlUm"] == 10000
        print(f"  ✅ ingest manual: record {record['recordId']} created")

# ===========================================================================
# analyze-config.py
# ===========================================================================

def test_analyze_config_safe():
    result = run_cli_in_process(analyze_config_mod, [
        "--clock-period", "25",
        "--utilization", "0.40",
        "--die-area", "0 0 500 500",
        "--pdk", "sky130A",
    ])
    assert "✅" in result["stdout"]
    print("  ✅ analyze-config safe: correctly identified as OK")

def test_analyze_config_risky():
    result = run_cli_in_process(analyze_config_mod, [
        "--clock-period", "8",
        "--utilization", "0.80",
        "--pdk", "sky130A",
    ])
    assert "HIGH RISK" in result["stdout"]
    print("  ✅ analyze-config risky: correctly identified HIGH RISK")

def test_analyze_config_json():
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = os.path.join(tmpdir, "config.json")
        with open(config_path, "w") as f:
            json.dump({
                "CLOCK_PERIOD": 20, "FP_CORE_UTIL": 45, "DIE_AREA": "0 0 600 600",
                "PDK": "sky130A", "DESIGN_NAME": "test_core",
            }, f)
        result = run_cli_in_process(analyze_config_mod, ["--config", config_path])
        assert "test_core" in result["stdout"]
        print("  ✅ analyze-config json: parsed config.json correctly")

# ===========================================================================
# benchmark.py
# ===========================================================================

def test_benchmark_manual():
    if not os.path.exists(CORPUS_PATH):
        return
    result = run_cli_in_process(benchmark_mod, [
        "--metrics", '{"hpwl": 10937, "wns": -7.93, "setup": 459, "hold": 0, "antenna": 0}',
        "--corpus", CORPUS_PATH,
    ])
    assert "Benchmark Report" in result["stdout"]
    print("  ✅ benchmark manual: report generated")

# ===========================================================================
# schema
# ===========================================================================

def test_corpus_schema():
    if not os.path.exists(CORPUS_PATH):
        return
    with open(CORPUS_PATH) as f:
        data = json.load(f)
    records = data.get("records", [])
    for i, record in enumerate(records):
        assert record["schemaVersion"] == "open-silicon-triage.corpus.v1"
        assert record["outcome"] in ["negative_evidence", "strategic_progress", "promoted_winner"]
        for key in ["hpwlUm", "averageSinkWireLengthUm", "setupWnsNs", "setupViolations", "holdViolations", "antennaViolations"]:
            assert key in record["metrics"]
    print(f"  ✅ corpus schema: all {len(records)} records valid")

# ===========================================================================
# Runner
# ===========================================================================

if __name__ == "__main__":
    tests = [
        test_train_smoke, test_train_corpus, test_eval_smoke, test_predict_smoke,
        test_ingest_manual, test_analyze_config_safe, test_analyze_config_risky,
        test_analyze_config_json, test_benchmark_manual, test_corpus_schema,
    ]

    print("=" * 60)
    print("  Open Silicon Triage — Test Suite (In-Process)")
    print("=" * 60)
    print()

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  ❌ {test.__name__}: {e}")
            failed += 1

    print()
    print("=" * 60)
    print(f"  Results: {passed} passed, {failed} failed, {len(tests)} total")
    print("=" * 60)

    sys.exit(1 if failed > 0 else 0)
