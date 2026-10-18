import hashlib,json
from copy import deepcopy
from pathlib import Path
import unittest
from data.variable_cardinality_pullback_prospective_validation import validate_candidate
ROOT=Path(__file__).resolve().parents[1]

class DraftValidation(unittest.TestCase):
    def setUp(self):
        self.protocol=json.loads((ROOT/'research_contracts/variable_cardinality_pullback_prospective_candidate_20261016_v1.json').read_text())
    def validate(self,p=None,reader=None):
        return validate_candidate(p or self.protocol,read_bytes=reader or (lambda name:(ROOT/name).read_bytes()))
    def test_actual_draft_is_not_activation(self):
        result=self.validate()
        self.assertEqual(result['verified_reference_count'],21)
        self.assertFalse(result['activated']);self.assertFalse(result['transitive_implementation_closure_verified'])
        self.assertTrue(result['missing_registration']);self.assertFalse(result['benchmark_missing_is_activation_blocker'])
    def test_old_top1_and_parameter_changes_rejected(self):
        for section,key,value in [('selection','method','MONTHLY_TOP1'),('execution','minimum_discount','0'),
            ('execution','maximum_age_seconds',120.0),('selection','fee_bps','10')]:
            p=deepcopy(self.protocol);p[section][key]=value
            with self.assertRaises(ValueError):self.validate(p)
        p=deepcopy(self.protocol);p['execution']['stop_loss']='0.1'
        with self.assertRaises(ValueError):self.validate(p)
    def test_backdate_or_activation_never_accepted(self):
        for key,value in [('registered_at','2026-01-01T00:00:00+00:00'),('account_id','existing'),
                          ('independent_year_started',True),('forward_account_created',True)]:
            p=deepcopy(self.protocol);p['activation'][key]=value
            with self.assertRaises(ValueError):self.validate(p)
    def test_benchmark_not_start_gate(self):
        p=deepcopy(self.protocol);p['background_comparators']['012922']['required']=True
        with self.assertRaises(ValueError):self.validate(p)
        p=deepcopy(self.protocol);p['activation_gates'].append('require benchmark')
        with self.assertRaises(ValueError):self.validate(p)
    def test_reporting_failure_duration_and_preference_scope_drift_rejected(self):
        changes=[('failure_gates',None,[]),('reporting','incomplete','Drop losing days'),
                 ('activation','intended_duration','Use old results as completed forward year'),
                 ('user_return_drawdown_priority','runtime_gap','Current runtime already optimizes drawdown'),
                 ('user_return_drawdown_priority','current_strategy_control','Use old TOP1 instead'),
                 ('background_comparators','purpose','Benchmarks are mandatory before starting')]
        for section,key,value in changes:
            with self.subTest(section=section,key=key):
                p=deepcopy(self.protocol)
                if key is None:p[section]=value
                else:p[section][key]=value
                with self.assertRaises(ValueError):self.validate(p)

    def test_hash_drift_resign_and_unbound_link_rejected(self):
        path=next(iter(self.protocol['candidate_code_hashes']))
        with self.assertRaises(ValueError):
            self.validate(reader=lambda name:b'tampered' if name==path else (ROOT/name).read_bytes())
        p=deepcopy(self.protocol);p['candidate_code_hashes'][path]=hashlib.sha256(b'tampered').hexdigest()
        with self.assertRaises(ValueError):self.validate(p,lambda name:b'tampered' if name==path else (ROOT/name).read_bytes())
        p=deepcopy(self.protocol);p['supersedes_draft']['sha256']='0'*64
        with self.assertRaises(ValueError):self.validate(p)

if __name__=='__main__':unittest.main()
