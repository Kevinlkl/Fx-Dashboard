"""Put src/ on the import path so tests can import the project's flat modules.

pytest imports conftest.py before collecting tests, which makes this the
standard place to fix up sys.path for a non-packaged layout.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))