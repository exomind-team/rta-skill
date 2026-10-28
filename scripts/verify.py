#!/usr/bin/env python3
"""Run synthetic EPUB transformation tests for this skill."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
result = subprocess.run(
    [sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-v"],
    cwd=root,
)
raise SystemExit(result.returncode)
