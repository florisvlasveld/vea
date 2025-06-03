import sys
from pathlib import Path

# Ensure project root is on sys.path so tests can import the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
