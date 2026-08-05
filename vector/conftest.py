"""conftest.py — make vector/src/ importable without pip install.

This is the lightest-touch path fix: since vector/ lives inside the
hermes-agent monorepo but has its own src/ layout, we add src/ to
sys.path here so every test under vector/tests/ can `import vector`
without a pip install step.
"""

import sys
from pathlib import Path

_src = str(Path(__file__).resolve().parent / "src")
if _src not in sys.path:
    sys.path.insert(0, _src)
