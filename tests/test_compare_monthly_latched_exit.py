import unittest
import json
import sys
from copy import deepcopy
from fractions import Fraction as F
from tempfile import TemporaryDirectory
from pathlib import Path
from scripts.compare_monthly_latched_exit import statistics,build,markdown,ROOT,SEALED


class ComparisonTests(unittest.TestCase):
    def test_exact_continuous_years_turnover_cash_and_fees(self):
        dates=['2023-12-29','2024-12-31','2025-12-31','2026-10-13']
        out=dict(status='COMPLETE',fees='3/2',daily_ledger=[
            dict(date=dates[1],equity='30000',cash='15000',stock_value='15000'),
            dict(date=dates[2],equity='15000',cash='0',stock_value='15000'),
            dict(date=dates[3],equity='22500',cash='22500',stock_value='0')],order_log=[
            dict(event='ASSUMED_NEXT_OPEN_FILLED',price='10/3',quantity=3),
            dict(event='ASSUMED_INTRADAY_LIMIT_FILLED',price='10',quantity=2),
            dict(event='NOT_FILLED')])
        value=statistics(out,dates)
        self.assertEqual([r['return_fraction'] for r in value['years']],['1/2','-1/2','1/2'])
        self.assertEqual(value['maximum_close_drawdown'],'1/2')
        self.assertEqual(value['maximum_drawdown_peak_date'],dates[1])
        self.assertEqual(value['maximum_drawdown_trough_date'],dates[2])
        self.assertEqual(value['longest_underwater_close_sessions'],2)
        self.assertTrue(value['end_still_underwater'])
        self.assertEqual(value['stock_held_close_fraction'],'2/3')
        self.assertEqual(value['cash_fraction_mean'],'1/2')
        self.assertEqual(value['turnover_gross_traded_dollars'],'30')
        self.assertEqual(F(value['turnover_gross_over_mean_close_nav']),F(30,22500))
        self.assertEqual(value['fees'],'3/2');self.assertEqual(value['fills'],2)
        bad=deepcopy(out);bad['daily_ledger'].pop(1)
        with self.assertRaisesRegex(ValueError,'INCOMPLETE'):statistics(bad,dates)
        bad=deepcopy(out);bad['daily_ledger'][0]['external_flow']='1'
        with self.assertRaisesRegex(ValueError,'EXTERNAL_FLOW'):statistics(bad,dates)

    def test_unready_inputs_do_not_create_outputs(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaises(FileNotFoundError):build(root)
            self.assertEqual(list(root.iterdir()),[])

    def test_failed_candidate_review_blocks_after_valid_baseline_inputs(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('tmp/daily_strategy_comparison_20261016_v2.json',
                         'tmp/partial_comparison_windows_independent_20261016_v1.json'):
                target=root/name
                target.parent.mkdir(parents=True,exist_ok=True)
                target.write_bytes((ROOT/name).read_bytes())
            candidate=root/'tmp/monthly_latched_sma20_exit_20261016_v1'
            candidate.mkdir()
            (candidate/'independent_review_v1.json').write_text(
                json.dumps({'status':'REVIEW_BLOCKED','reason':'LATCH_STATE_MISMATCH'}))
            with self.assertRaisesRegex(ValueError,'INDEPENDENT_REVIEW_REQUIRED'):
                build(root)
            self.assertFalse((root/'tmp/monthly_latched_exit_comparison_20261016_v1').exists())

    def test_saved_b0_half_exact_cash_serialization_and_rendering(self):
        sessions=json.loads((ROOT/'tmp/daily_verified_domain_experiment_20261016_v2/prepared.json').read_bytes())['session_dates']
        previous=sys.get_int_max_str_digits();arms={}
        for arm in ('B0','half'):
            out=json.loads((ROOT/SEALED[arm][0]).read_bytes())
            arms[arm]=statistics(out,sessions)
            self.assertEqual(json.loads(json.dumps(arms[arm])),arms[arm])
            self.assertEqual(sys.get_int_max_str_digits(),previous)
        rendered=markdown(dict(arms=arms,scope='test'))
        self.assertIn('趋势走弱半仓',rendered)
        self.assertEqual(sys.get_int_max_str_digits(),previous)


if __name__=='__main__':unittest.main()
