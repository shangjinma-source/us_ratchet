import hashlib
from pathlib import Path
import unittest
from scripts.preflight_annual_risk_execution_20261016 import extend_pins,REQUIRED_PINS,ROOT

class PinClosure(unittest.TestCase):
    def setUp(self):
        self.real={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in REQUIRED_PINS}
    def test_adds_actual_v2_implementation_without_mutating_draft(self):
        draft=dict(source_hashes={'existing':'a'*64},windows=[{'target':'unchanged'}])
        result=extend_pins(draft,self.real)
        self.assertEqual(result['windows'],draft['windows'])
        self.assertEqual(set(result['source_hashes']),{'existing'}|set(REQUIRED_PINS))
        self.assertEqual(draft['source_hashes'],{'existing':'a'*64})
        for path in REQUIRED_PINS:self.assertEqual(result['source_hashes'][path],self.real[path])
    def test_conflict_cannot_replace_sealed_pin(self):
        draft=dict(source_hashes={REQUIRED_PINS[0]:'0'*64})
        with self.assertRaisesRegex(ValueError,'SOURCE_PIN_CONFLICT'):extend_pins(draft,self.real)
    def test_missing_selector_dependencies_rejected(self):
        missing=dict(self.real);missing.pop(REQUIRED_PINS[-1])
        with self.assertRaisesRegex(ValueError,'V2_METHOD_SOURCE_PINS_REQUIRED'):
            extend_pins(dict(source_hashes={}),missing)

if __name__=='__main__':unittest.main()
