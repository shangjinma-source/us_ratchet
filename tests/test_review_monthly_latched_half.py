from copy import deepcopy
import unittest
import test_continuous_guided_cost_stress as fixture
from scripts import run_continuous_guided_monthly_latched_half as runner
from scripts import review_monthly_latched_half as reviewer

class ReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assembled,cls.bars,resolver=fixture.CostStressTests().data()
        cls.pins={runner.CONTRACT:runner.CONTRACT_SHA}
        cls.outcome=runner.run_candidate(scenario='fee1_slippage10',assembled=cls.assembled,ohlc=cls.bars,
            resolver=resolver,pins=cls.pins,progress=None,run_receipt_sha256='c'*64)
    def check(self,outcome):
        return reviewer.review(assembled=self.assembled,ohlc=self.bars,outcome=outcome,
            scenario='fee1_slippage10',expected_pins=self.pins,expected_receipt_sha256='c'*64)
    def test_real_synthetic_candidate_passes(self):
        result=self.check(self.outcome)
        self.assertEqual(result['status'],'MONTHLY_LATCHED_HALF_SAVED_EVIDENCE_VERIFIED')
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
            if field=='state':row['risk_overlay']['monthly_latch']['latched_security_ids']=['FAKE']
            if field=='target':row['target_shares']={'A':1}
            if field=='signal':row['risk_overlay']['diagnostics']['A']['on']=not row['risk_overlay']['diagnostics']['A']['on']
            if field=='coverage':bad['provider_audit'].pop()
            with self.assertRaises(ValueError):self.check(bad)

if __name__=='__main__':unittest.main()

class LatchActionTests(unittest.TestCase):
    def data(self):
        days=['2026-01-28','2026-01-29','2026-01-30','2026-02-02','2026-02-03']
        action=dict(date=days[1],security_id='A',new_security_id='B',type='split_identity',new_shares=2,old_shares=1)
        a=dict(session_dates=days,monthly_inputs=[dict(decision_date=days[0]),dict(decision_date=days[3])],
            provider_actions=[action],close_prices={sid:{d:'10' for d in days} for sid in ('A','B')})
        def row(index,sid,ceiling,target,month,weak,held,selection=False,latched=True):
            day=days[index];delta=target-held
            risk=dict(signal_date=day,base_target=dict(quantities={sid:ceiling},monthly_decision_date=month),
                target_quantities={sid:target},diagnostics={sid:dict(on=not weak,close='10',sma20='20' if weak else '5',monthly_ceiling=ceiling)},
                monthly_latch=dict(monthly_decision_date=month,latched_security_ids=[sid] if latched else [],
                    reset='NEW_SUCCESSFUL_MONTHLY_SELECTION_ONLY',rounding='FLOOR_ADJUSTED_MONTHLY_CEILING_NOT_CURRENT_HOLDINGS'))
            orders=[] if not delta else [dict(security_id=sid,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),
                decision_date=day,active_date=days[index+1],decision_mark='10')]
            return dict(status='READY',action='NEXT_OPEN_RISK_DIFFERENCES',target_decision_date=month,
                monthly_ceiling={sid:ceiling},target_shares={sid:target},risk_overlay=risk,orders=orders,
                selection=dict(binding=dict(decision_date=day),target_quantities={sid:ceiling}) if selection else None)
        wait=dict(status='READY',action='WAIT_POST_ACTION_MARK',selection=None,orders=[],target_shares={'B':14},
            target_adjustments=[dict(date=days[1],security_id='A',new_security_id='B',target_after=14)])
        o=dict(provider_audit=[row(0,'A',7,3,days[0],True,0,True),wait,
            row(2,'B',14,7,days[0],False,6),row(3,'B',15,15,days[3],False,7,True,False)],
            daily_ledger=[dict(date=days[1],shares={'A':3}),dict(date=days[2],shares={'B':6}),dict(date=days[3],shares={'B':7})],
            after_close_records=[dict(date=days[1],phase='AFTER_CLOSE_UNVALUED_STATE',shares={'B':6})])
        return a,o
    def test_wait_migration_odd_ceiling_and_newmonth_reset(self):
        a,o=self.data()
        self.assertEqual(reviewer.review_latches(assembled=a,outcome=o)['sessions'],4)
    def test_missing_adjustment_even_with_fabricated_target_rejected(self):
        a,o=self.data();o['provider_audit'][1]['target_adjustments']=[]
        o['provider_audit'][1]['target_shares']={'A':7}
        with self.assertRaisesRegex(ValueError,'ADJUSTMENT_COMPLETENESS'):reviewer.review_latches(assembled=a,outcome=o)
    def test_fake_wait_without_after_close_evidence_rejected(self):
        a,o=self.data();o['after_close_records']=[]
        with self.assertRaisesRegex(ValueError,'WAIT_COORDINATE_EVIDENCE'):reviewer.review_latches(assembled=a,outcome=o)
    def test_missing_order_or_same_month_recovery_rejected(self):
        for kind in ('order','recovery','reset'):
            a,o=self.data()
            if kind=='order':o['provider_audit'][2]['orders']=[]
            if kind=='recovery':o['provider_audit'][2]['target_shares']={'B':14}
            if kind=='reset':o['provider_audit'][2]['target_decision_date']=a['session_dates'][2]
            with self.assertRaises(ValueError):reviewer.review_latches(assembled=a,outcome=o)
