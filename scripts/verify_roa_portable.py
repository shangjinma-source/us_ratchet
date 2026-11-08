"""Run ROA regression tests without requiring private historical evidence."""
import argparse
from pathlib import Path
import sys
import unittest

PRIVATE_EVIDENCE_MODULES = {
    "test_roa_current_signal_20261106",
    "test_roa_daily_signal_20261106",
    "test_roa_monthly_selection_20261106",
}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--with-private-fixtures", action="store_true",
                        help="Also run historical integration tests; local evidence must exist.")
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "tests"))
    (root / "tmp").mkdir(exist_ok=True)
    names = sorted(path.stem for path in (root / "tests").glob("test_roa*.py"))
    if not arguments.with_private_fixtures:
        print("Private-evidence integration tests not covered: " + ", ".join(sorted(PRIVATE_EVIDENCE_MODULES)), flush=True)
        names = [name for name in names if name not in PRIVATE_EVIDENCE_MODULES]
    result = unittest.TextTestRunner(verbosity=1).run(unittest.defaultTestLoader.loadTestsFromNames(names))
    return 0 if result.wasSuccessful() else 1

if __name__ == "__main__":
    raise SystemExit(main())
