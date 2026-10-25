from copy import deepcopy
import unittest
import test_continuous_guided_cost_stress as fixture
from scripts import run_continuous_guided_ma9_sma20_half as runner
from scripts import review_ma9_sma20_half as reviewer

class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembled,cls.bars,resolver=fixture.CostStressTests().data()
        cls.resolver=staticmethod(resolver)
        cls.pins={runner.CONTRACT:runner.CONTRACT_SHA}
        cls.outcome=runner.run_candidate(scenario='fee1_slippage10',assembled=cls.assembled,ohlc=cls.bars,
            resolver=resolver,pins=cls.pins,progress=None,run_receipt_sha256='c'*64)
    def check(self,outcome):
        return reviewer.review(assembled=self.assembled,ohlc=self.bars,outcome=outcome,
            scenario='fee1_slippage10',expected_pins=self.pins,expected_receipt_sha256='c'*64)
    def test_exact_signal_recomputation_rejects_forged_suffix(self):
        from scripts.review_ma9_sma20_signals import review as signals
        valid=signals(assembled=self.assembled,outcome=self.outcome,history_resolver=self.resolver)
        self.assertEqual(valid['status'],'SMA9_SMA20_DIAGNOSTICS_RECOMPUTED_FROM_SUPPLIED_HISTORY')
        bad=deepcopy(self.outcome);bad['provider_audit'][0]['risk_overlay']['diagnostics']['A']['sma9']='99'
        with self.assertRaises(ValueError):signals(assembled=self.assembled,outcome=bad,history_resolver=self.resolver)

    def test_real_synthetic_candidate_passes(self):
        result=self.check(self.outcome)
        self.assertEqual(result['status'],'MA9_SMA20_SAVED_EVIDENCE_VERIFIED')
    def test_receipt_contract_and_arm_tamper(self):
        for field in ('receipt_sha256','contract_sha256','candidate'):
            bad=deepcopy(self.outcome);bad['research_run_binding'][field]='bad'
            with self.assertRaisesRegex(ValueError,'RESEARCH_RUN_BINDING'): self.check(bad)
        bad=deepcopy(self.outcome);bad['cost_stress_arm']='continuous32_half'
        with self.assertRaisesRegex(ValueError,'ARM_LABEL'):self.check(bad)
    def test_fill_fee_cash_and_monthly_source_tamper(self):
        for field in ('fee','price','cash_after'):
            bad=deepcopy(self.outcome)
            next(r for r in bad['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED')[field]='999'
            with self.assertRaises(ValueError):self.check(bad)
        bad=deepcopy(self.outcome);bad['selection_account_states'][0]['source_hashes']['x']='f'*64
        with self.assertRaisesRegex(ValueError,'MONTHLY_SOURCE'):self.check(bad)
    def test_latch_state_target_signal_coverage_tamper(self):
        for field in ('state','target','signal','coverage'):
            bad=deepcopy(self.outcome);row=bad['provider_audit'][0]
            if field=='state':row['risk_overlay']['diagnostics']['A']['sma9']='999'
            if field=='target':row['target_shares']={'A':1}
            if field=='signal':row['risk_overlay']['diagnostics']['A']['on']=not row['risk_overlay']['diagnostics']['A']['on']
            if field=='coverage':bad['provider_audit'].pop()
            with self.assertRaises(ValueError):self.check(bad)

if __name__=='__main__':unittest.main()



class ActionBoundaryTests(unittest.TestCase):
    def data(self):
        from test_review_monthly_latched_half import LatchActionTests
        a,o=LatchActionTests().data()
        for row in o['provider_audit']:
            if 'risk_overlay' not in row:continue
            for d in row['risk_overlay']['diagnostics'].values():
                d.update(sma9=d['sma20'],on_sma9=d['on'],on_sma20=d['on'])
        # Under dynamic dual-MA, the post-action strong day restores full14.
        row=o['provider_audit'][2];row['target_shares']={'B':14};row['risk_overlay']['target_quantities']={'B':14};row['orders'][0]['quantity']=8
        return a,o
    def test_action_completeness_and_wait_evidence(self):
        a,o=self.data();self.assertEqual(reviewer.review_targets(assembled=a,outcome=o)['sessions'],4)
        for fault in ('adjustment','wait','orders'):
            bad=deepcopy(o)
            if fault=='adjustment':bad['provider_audit'][1]['target_adjustments']=[]
            if fault=='wait':bad['after_close_records']=[]
            if fault=='orders':bad['provider_audit'][2]['orders']=[]
            with self.assertRaises(ValueError):reviewer.review_targets(assembled=a,outcome=bad)
