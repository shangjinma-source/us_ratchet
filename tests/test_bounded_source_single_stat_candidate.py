import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
import test_strategy_bounded_source_gate_v1 as original
import test_bounded_source_gate_path_safety as safety
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('single_stat_candidate',root/'docs/candidates/strategy_bounded_source_gate_single_stat.py')
candidate=importlib.util.module_from_spec(spec);spec.loader.exec_module(candidate)
# Emulate its proposed deployment path for executing-source checks.
candidate.__file__=str(root/'data/strategy_bounded_source_gate_v1.py')
class CandidateGateTests(original.BoundedGateTests):
 def setUp(self):
  p=patch.object(original,'module',candidate);p.start();self.addCleanup(p.stop)
class CandidatePathTests(safety.PathSafetyTests):
 def setUp(self):
  p=patch.object(safety,'gate',candidate);p.start();self.addCleanup(p.stop)
if __name__=='__main__':unittest.main()
