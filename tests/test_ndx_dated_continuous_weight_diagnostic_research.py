from copy import deepcopy
from datetime import date,timedelta
from decimal import localcontext,Inexact
from fractions import Fraction
import hashlib
from pathlib import Path
import unittest
from backtest import ndx_dated_continuous_weight_diagnostic_research as m

def fixture():
    days=['2026-03-20'];d=date(2026,3,23)
    while len(days)<126:
        if d.weekday()<5:days.append(d.isoformat())
        d+=timedelta(days=1)
    days.append('2026-09-21')
    positions=[dict(security_id='sid:a',ticker='A',target_weight=0.6),dict(security_id='sid:b',ticker='B',target_weight=0.4)]
    quotes={p['security_id']:[dict(session=d,nominal_open_exact='10',nominal_close_exact=str(10+i%7)) for i,d in enumerate(days)] for p in positions}
    return dict(calendar=days,positions=positions,nominal_quotes=quotes,split_events=[],transaction_cost_bps=10,source_references={'synthetic':True})

class Tests(unittest.TestCase):
    def test_cross_original_actionfree(self):
        import pandas as pd
        from backtest.ndx_challenger_forward_evaluation import _continuous_nav
        source=Path(__file__).resolve().parents[1]/'backtest/ndx_challenger_forward_evaluation.py'
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),'e80be16c783fce0a28ee9792359bced6e0e9ee786bfe345745ea513af799438e')
        a=fixture();r=m.diagnose_continuous_weights(**a);dates=pd.DatetimeIndex(a['calendar'][1:]);prices={p['ticker']:pd.DataFrame({'Open':[10.0]*126,'Close':[float(q['nominal_close_exact']) for q in a['nominal_quotes'][p['security_id']][1:]]},index=dates) for p in a['positions']}
        old=_continuous_nav(pd.DataFrame(a['positions']),prices,dates,.001)
        for actual,expected in zip(r['path'][1:],old):self.assertAlmostEqual(float(m.number(actual['normalized_value'])),expected,places=14)
    def test_split_before_purchase_and_later_once(self):
        a=fixture();days=a['calendar'];a['positions']=[dict(security_id='sid:a',ticker='A',target_weight='1')];a['nominal_quotes']={'sid:a':[dict(session=d,nominal_open_exact='10' if i<3 else '5',nominal_close_exact='10' if i<3 else '5') for i,d in enumerate(days)]}
        a['split_events']=[dict(security_id='sid:a',effective_session=days[i],numerator='2',denominator='1',source_reference={'path':'split'+str(i),'sha256':'a'*64}) for i in (1,3)]
        r=m.diagnose_continuous_weights(**a);self.assertTrue(all(m.number(p['normalized_value'])==Fraction(999,1000) for p in r['path'][1:]));self.assertEqual(m.number(r['path'][3]['security_rows'][0]['fractional_quantity']),Fraction(1,5))
    def test_buyhold_not_daily_rebalanced(self):
        a=fixture();a['positions'][0]['target_weight']='0.5';a['positions'][1]['target_weight']='0.5'
        for sid,rows in a['nominal_quotes'].items():
            for i,r in enumerate(rows):r['nominal_close_exact']='20' if (sid=='sid:a' and i==1) else '10'
        r=m.diagnose_continuous_weights(**a);self.assertEqual(m.number(r['path'][2]['normalized_value']),Fraction(999,1000));self.assertNotEqual(m.number(r['path'][2]['normalized_value']),Fraction(3,2)*Fraction(3,4)*Fraction(999,1000))
    def test_weights_zero_loss_initial_drawdown_context(self):
        a=fixture();a['positions'][0]['target_weight']='0.7';a['positions'][1]['target_weight']=0
        for rows in a['nominal_quotes'].values():
            for q in rows:q['nominal_close_exact']='5'
        before=deepcopy(a)
        with localcontext() as c:c.prec=2;c.traps[Inexact]=True;r=m.diagnose_continuous_weights(**a)
        self.assertEqual(a,before);self.assertEqual(r['positions_preserved'],a['positions']);self.assertEqual(m.number(r['weight_sum_exact']),Fraction(7,10));self.assertLess(m.number(r['cumulative_return_exact']),0);self.assertEqual(r['drawdown_peak_index'],0);self.assertEqual(m.number(r['max_drawdown_exact']),1-Fraction(7,20)*Fraction(999,1000));self.assertEqual(m.number(r['path'][-1]['security_rows'][1]['fractional_quantity']),0)
    def test_no_compressed_calendar_duplicate_action_or_boolean(self):
        for mutation in ('missing','duplicate','bool','adjusted'):
            a=fixture()
            if mutation=='missing':a['nominal_quotes']['sid:a'].pop()
            elif mutation=='bool':a['positions'][0]['target_weight']=True
            elif mutation=='adjusted':a['nominal_quotes']['sid:a'][1]['nominal_open_exact']='0'
            else:
                e=dict(security_id='sid:a',effective_session=a['calendar'][2],numerator='2',denominator='1',source_reference={'path':'event','sha256':'a'*64});a['split_events']=[e,e]
            with self.assertRaises(ValueError):m.diagnose_continuous_weights(**a)

if __name__=='__main__':unittest.main()
