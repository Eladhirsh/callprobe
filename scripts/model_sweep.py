#!/usr/bin/env python3
"""Backwards-compatible entry point for `callprobe sweep`.

    python scripts/model_sweep.py --models a b --out /tmp/sweep [--suite DIR] [--dry-run]
"""

import sys
from pathlib import Path

try:
    from callprobe.sweep import main
except ImportError:  # running from a checkout without an install
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from callprobe.sweep import main

if __name__ == "__main__":
    raise SystemExit(main())
