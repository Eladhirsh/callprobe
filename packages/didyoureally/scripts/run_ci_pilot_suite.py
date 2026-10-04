"""Repeat the frozen seven-model screen and two-model qualification locally."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS = [
    "mistral-nemo:latest",
    "qwen2.5:7b",
    "llama3.2:3b",
    "hermes3:8b",
    "llama3.1:8b",
    "phi4-mini:latest",
    "granite3.3:8b",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=False)
    for name, cases, models in [
        ("screen", "examples/reliability-challenge", MODELS),
        ("development", "src/didyoureally/benchmark", MODELS[:2]),
        ("validation", "examples/ci-pilot-validation", MODELS[:2]),
    ]:
        command = [
            sys.executable,
            str(ROOT / "scripts/run_llm_bench.py"),
            "--json-mode",
            "--cases",
            str(ROOT / cases),
            "--out",
            str(args.out / name),
        ]
        for model in models:
            command += ["--endpoint", args.base_url, model]
        result = subprocess.run(command, cwd=ROOT)
        if result.returncode not in (0, 1):
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
