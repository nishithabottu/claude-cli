"""Pytest config: put the repo root on sys.path so ``schemas.py`` imports
from tests, just like it does when an end-user runs the CLI from their
project directory.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
