from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import compare_continuous_guided_monthly_book as module


class ComparisonTests(unittest.TestCase):
    def selection(self,date):
        return dict(decision_date=date,target_quantities={'A':10},binding=dict(decision_date=date,investable_equity='20000',search_arguments=dict(entered_cash='20000',prices={'A':'1000'},metadata={'A':{'ticker':'AAA'}},fee_bps='0')),search_result=dict(selected=dict(quantities={'A':10},actual_k=1,actual_weights={'A':'1/2'},notional='10000',fees='0',residual_cash='10000',cash_fraction='1/2')))

    def fixture(self,root):
        def save(name,value):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
            raw=json.dumps(value).encode();p.write_bytes(raw);return sha256(raw).hexdigest()
        for name in ['scripts/compare_continuous_guided_monthly_book.py','scripts/compare_monthly_latched_exit.py','backtest/continuous_calendar_year_metrics.py']:
            target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((module.ROOT/name).read_bytes())
        sessions=['2023-12-29','2024-12-31','2025-12-31','2026-10-13']
        prepared_sha=save('prepared.json',dict(session_dates=sessions,windows=[dict(decision_date=sessions[0])]))
        def outcome(values):return dict(provider_audit=[dict(selection=self.selection(sessions[0]))],status='COMPLETE',fees='0',order_log=[],daily_ledger=[dict(date=day,equity=str(v),cash=str(v),stock_value='0') for day,v in zip(sessions[1:],values)])
        base_sha=save(module.BASE+'/outcome.json',outcome([22000,18000,23000]))
        candidate_sha=save(module.RUN+'/outcome.json',outcome([22000,20000,24000]))
        pre=dict(prepared_path='prepared.json',prepared_sha256=prepared_sha,source_hashes={'prepared.json':prepared_sha},initial_cash='20000',fee_bps='0',slippage_bps='0',continuous_iterations=32)
        for directory in (module.BASE,module.RUN):
            save(directory+'/preflight.json',pre);save(directory+'/terminal.json',dict(status='COMPLETE',source_pins_unchanged=True))
        save(module.RUN+'/independent_review_v1.json',dict(status=module.REVIEW_STATUS,outcome_sha256=candidate_sha))
        return save,base_sha

    def test_exact_joint_comparison_and_chinese_table(self):
        with TemporaryDirectory() as directory:
            root=Path(directory);save,base_sha=self.fixture(root)
            with patch.object(module,'BASE_SHA',base_sha):report=module.build(root)
            self.assertEqual(report['monthly_target_comparison']['B0']['concentration']['maximum_target_weight'],'1/2')
            self.assertEqual(report['monthly_target_comparison']['continuous32']['months'][0]['targets'][0]['ticker'],'AAA')
            self.assertTrue(report['joint_improvement_against_B0']);self.assertFalse(report['automatic_promotion'])
            self.assertEqual(report['arms']['continuous32']['years'][-1]['return_fraction'],'1/5')
            self.assertNotIn('elapsed_day_annualized_return',report['arms']['continuous32']['years'][-1])
            table=module.markdown(report)
            self.assertIn('改进选股搜索，每月换股',table);self.assertIn('原选股搜索，每月换股',table)
            self.assertIn('2026截至2026-10-13',table);self.assertFalse((root/module.OUTPUT).exists())

    def test_monthly_missing_duplicate_and_weight_mismatch_rejected(self):
        for mutation in ('missing','duplicate','weight'):
            with self.subTest(mutation=mutation),TemporaryDirectory() as directory:
                root=Path(directory);save,base_sha=self.fixture(root)
                outcome=json.loads((root/module.RUN/'outcome.json').read_bytes())
                if mutation=='missing':outcome['provider_audit']=[]
                elif mutation=='duplicate':outcome['provider_audit']*=2
                else:outcome['provider_audit'][0]['selection']['search_result']['selected']['actual_weights']['A']='3/4'
                h=save(module.RUN+'/outcome.json',outcome)
                save(module.RUN+'/independent_review_v1.json',dict(status=module.REVIEW_STATUS,outcome_sha256=h))
                with patch.object(module,'BASE_SHA',base_sha),self.assertRaises(ValueError):module.build(root)

    def test_review_terminal_hash_and_calendar_gates(self):
        for change in ('review','terminal','hash','calendar','incomplete_ledger'):
            with self.subTest(change=change),TemporaryDirectory() as directory:
                root=Path(directory);save,base_sha=self.fixture(root)
                if change=='review':save(module.RUN+'/independent_review_v1.json',dict(status='NOT_READY'))
                if change=='terminal':save(module.RUN+'/terminal.json',dict(status='RUNNING',source_pins_unchanged=True))
                if change=='hash':(root/module.RUN/'outcome.json').write_bytes(b'{}')
                if change=='calendar':save('prepared.json',dict(session_dates=[]))
                if change=='incomplete_ledger':
                    outcome=json.loads((root/module.RUN/'outcome.json').read_bytes());outcome['daily_ledger'].pop(0)
                    h=save(module.RUN+'/outcome.json',outcome);save(module.RUN+'/independent_review_v1.json',dict(status=module.REVIEW_STATUS,outcome_sha256=h))
                with patch.object(module,'BASE_SHA',base_sha),self.assertRaises(ValueError):module.build(root)
                self.assertFalse((root/module.OUTPUT).exists())


if __name__=='__main__':unittest.main()
