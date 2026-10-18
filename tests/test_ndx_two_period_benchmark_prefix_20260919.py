import json
import unittest
from copy import deepcopy
from decimal import Decimal
from scripts import ndx_two_period_benchmark_prefix_20260919 as m


def fixture():
    docs={k:json.loads((m.BASE/p).read_bytes()) for k,(p,h) in m.BOUND.items()}
    days=[d for d in docs['calendar']['calendar'] if m.START<=d<=m.END]
    prices={r['ticker']:m.nominal_from_raw(m.Path(r['price_response_path']).read_bytes(),r['ticker'],days) for r in docs['basis']['rows']}
    return docs,days,prices


class Tests(unittest.TestCase):
    def test_real_bounded_account_without_engine_or_fitter(self):
        docs,days,prices=fixture();value=m.audit_control(docs['control'],docs['old'],days,prices)
        self.assertEqual(len(value['daily']),21);self.assertEqual(len(value['trades']),13)
        self.assertEqual(len(value['decisions']),2);self.assertEqual(value['metrics']['return_interval_count'],20)
        self.assertLess(Decimal(value['decimal_max_error']),Decimal('1e-8'))
        nav=docs['nav'];path,=[p for p in nav['source_hashes'] if p.endswith('012922.csv')]
        result=m.audit_nav(nav,m.Path(path).read_bytes(),days)
        self.assertEqual(result['rows'][-1]['nav_date'],'2023-04-28')

    def test_cash_fee_trade_clock_and_weights_tampering_reject(self):
        for defect in ('cash','fee','trade','clock','weight','riskgate'):
            docs,days,prices=fixture();report=docs['control'];e=report['execution']
            if defect=='cash':e['daily'][10]['cash_usd']+=1
            if defect=='fee':e['trades'][0]['transaction_cost_usd']=0
            if defect=='trade':e['trades'].pop(0)
            if defect=='clock':e['decisions'][1]['execution_date']='2023-05-02'
            if defect=='weight':report['original_fixed_schedule']['original_weights']['GOOG']+=.01
            if defect=='riskgate':e['risk_is_order_gate']=True
            with self.subTest(defect=defect),self.assertRaises(ValueError):m.audit_control(report,docs['old'],days,prices)

    def test_metrics_use20_intervals_not295_summary(self):
        values=[Decimal(100)]*20+[Decimal(110)];metrics=m.metrics(values)
        self.assertEqual(Decimal(metrics['path_return']),Decimal('.1'))
        self.assertEqual(Decimal(metrics['path_max_drawdown']),0)
        self.assertGreater(Decimal(metrics['annualized_return_252_over_20']),2)
        with self.assertRaises(ValueError):m.metrics([100]*295)


if __name__=='__main__':unittest.main()
