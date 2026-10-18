import copy
import json
import unittest
from decimal import Decimal
from pathlib import Path
from backtest import ndx_single_window_benchmark_metrics_research as m


def fixture():
    value=json.loads(Path('data/cache/research/latest_twenty_historical_inputs_20260919_v1/inputs.json').read_bytes())
    calendar=value['prices']['calendar'][126:]
    daily=[dict(session=d,total_value_usd=25000) for d in calendar]
    return dict(calendar=calendar,candidate_daily=daily,incumbent_daily=copy.deepcopy(daily),nav_csv='Date,Close\n2026-03-17,1\n2026-09-18,999\n')


class IndependentMetricsTests(unittest.TestCase):
    def test_future_nav_never_enters_and_peak_path_matters(self):
        args=fixture();args['candidate_daily'][1]['total_value_usd']=50000
        result=m.compare(**args)
        self.assertEqual(Decimal(result['candidate']['path_max_drawdown']),Decimal('.5'))
        self.assertEqual(Decimal(result['candidate']['annualized_return_252_over_126']),0)
        self.assertTrue(all(r['nav_source_date']=='2026-03-17' for r in result['nav']['rows']))
        self.assertFalse(result['formal_dual_benchmark_admission'])

    def test_drawdown_sign_and_fixed_interval_annualization(self):
        args=fixture();args['candidate_daily'][-1]['total_value_usd']=30000
        result=m.compare(**args)
        self.assertEqual(Decimal(result['candidate']['annualized_return_252_over_126']),Decimal('.44'))
        self.assertEqual(Decimal(result['candidate_minus_reference']['original_incumbent']['path_return']),Decimal('.2'))

    def test_invalid_dates_and_cash_and_future_only_nav_rejected(self):
        for mutation in ('duplicate','reverse','boolcash','infinity','futureonly','duplicatenav','boolnav'):
            args=fixture()
            if mutation=='duplicate':args['candidate_daily'][1]=copy.deepcopy(args['candidate_daily'][0])
            elif mutation=='reverse':args['calendar'][1:3]=reversed(args['calendar'][1:3])
            elif mutation=='boolcash':args['candidate_daily'][1]['total_value_usd']=True
            elif mutation=='infinity':args['candidate_daily'][1]['total_value_usd']=float('inf')
            elif mutation=='futureonly':args['nav_csv']='Date,Close\n2026-03-19,1\n'
            elif mutation=='duplicatenav':args['nav_csv']='Date,Close\n2026-03-17,1\n2026-03-17,2\n'
            else:args['candidate_daily'][0]['total_value_usd']=False
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):m.compare(**args)


if __name__=='__main__':unittest.main()
