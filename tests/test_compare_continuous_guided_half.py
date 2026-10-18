import json,hashlib,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from test_compare_continuous_guided_monthly_book import ComparisonTests
from scripts import compare_continuous_guided_monthly_book as old_module
from scripts import compare_continuous_guided_half as module


class HalfComparisonTests(unittest.TestCase):
    def fixture(self,root):
        save,base_sha=ComparisonTests().fixture(root)
        for directory in (old_module.RUN,old_module.BASE):
            pre=json.loads((root/directory/'preflight.json').read_bytes());pre['search_parameters']=[{'fixed_seed':'same','max_objective_evaluations':8192}];save(directory+'/preflight.json',pre)
        with patch.object(old_module,'BASE_SHA',base_sha):old=old_module.build(root)
        old_sha=save(module.OLD,old)
        candidate_raw=(root/old_module.RUN/'outcome.json').read_bytes();candidate=json.loads(candidate_raw)
        sealed={'B0':(old_module.BASE+'/outcome.json',base_sha),'continuous32':(old_module.RUN+'/outcome.json',hashlib.sha256(candidate_raw).hexdigest())}
        save(module.RUN+'/preflight.json',pre);save(module.RUN+'/terminal.json',dict(status='COMPLETE',source_pins_unchanged=True))
        h=save(module.RUN+'/outcome.json',candidate);save(module.RUN+'/independent_review_v1.json',dict(status=module.REVIEW_STATUS,outcome_sha256=h))
        path=root/'scripts/compare_continuous_guided_half.py';path.write_bytes((module.ROOT/'scripts/compare_continuous_guided_half.py').read_bytes())
        return save,old_sha,sealed

    def test_three_arms_exact_main_and_secondary_comparisons(self):
        with TemporaryDirectory() as d:
            root=Path(d);save,h,sealed=self.fixture(root)
            with patch.object(module,'OLD_SHA',h),patch.object(module,'SEALED',sealed):report=module.build(root)
            self.assertEqual(len(report['arms']),3)
            self.assertFalse(report['comparisons']['continuous32']['joint_improvement'])
            self.assertTrue(report['comparisons']['B0']['joint_improvement'])
            self.assertTrue(report['descriptive_2026']['not_primary_acceptance'])
            self.assertIn('新候选搜索，趋势走弱半仓',module.markdown(report))
            self.assertFalse((root/module.OUTPUT).exists())

    def test_markdown_handles_large_cash_fraction(self):
        with TemporaryDirectory() as d:
            root=Path(d);save,h,sealed=self.fixture(root)
            with patch.object(module,'OLD_SHA',h),patch.object(module,'SEALED',sealed):report=module.build(root)
            huge='9'*12000
            report['arms']['continuous32_half']['cash_fraction_mean']=huge+'/'+huge
            self.assertIn('100.00%',module.markdown(report))

    def test_incomplete_review_hash_and_budget_rejected(self):
        for kind in ('review','terminal','hash','budget'):
            with self.subTest(kind=kind),TemporaryDirectory() as d:
                root=Path(d);save,h,sealed=self.fixture(root)
                if kind=='review':save(module.RUN+'/independent_review_v1.json',dict(status='NOT_READY'))
                if kind=='terminal':save(module.RUN+'/terminal.json',dict(status='RUNNING'))
                if kind=='hash':save(module.RUN+'/outcome.json',{})
                if kind=='budget':
                    p=json.loads((root/module.RUN/'preflight.json').read_bytes());p['continuous_iterations']=64;save(module.RUN+'/preflight.json',p)
                with patch.object(module,'OLD_SHA',h),patch.object(module,'SEALED',sealed),self.assertRaises(ValueError):module.build(root)

    def test_transitions_distinguish_month_reset_and_actual_fills(self):
        rows=[]
        for day,month,on in [('2026-01-01','m1',False),('2026-01-02','m1',True),('2026-01-03','m1',False),('2026-02-01','m2',True)]:
            rows.append(dict(target_decision_date=month,risk_overlay=dict(signal_date=day,diagnostics={'A':{'on':on}}),orders=[dict(id=day,security_id='A',side='BUY' if on else 'SELL')]))
        r=module.overlay_activity(dict(provider_audit=rows,order_log=[dict(event='ASSUMED_NEXT_OPEN_FILLED',id='2026-01-02')]))
        self.assertEqual((r['reduction_signals'],r['recovery_signals']),(1,1))
        self.assertEqual((r['reduction_fills'],r['recovery_fills']),(0,1))


if __name__=='__main__':unittest.main()
