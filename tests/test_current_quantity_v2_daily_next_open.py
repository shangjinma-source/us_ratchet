from fractions import Fraction
import hashlib
import json
import unittest
from copy import deepcopy
from pathlib import Path
from backtest.current_quantity_v2_next_open_book import run_next_open_book
from backtest.current_quantity_v2_daily_next_open import run_daily_next_open, drawdown_summary
from backtest.return_priority_monthly_execution_inputs_v4 import assemble_monthly_execution_inputs_v4
from data.current_research_capital_decision_v2 import REQUIRED_PINS

D=['2026-01-01','2026-01-02','2026-01-05']
def bar(p): return dict(open=str(p), high=str(p), low=str(p), close=str(p))
def order(sid,side,q):
    return dict(id=sid,security_id=sid,side=side,quantity=q,decision_mark='10',decision_date=D[0],active_date=D[1])

class NextOpenTests(unittest.TestCase):
    def book(self,**kw):
        args=dict(session_dates=D[:2],orders=[order('A','BUY',10)],ohlc={'A':{D[1]:bar(20)}},initial_cash='100',fee_bps='0',slippage_bps='0')
        args.update(kw)
        return run_next_open_book(**args)

    def test_gap_up_rations_and_does_not_use_low(self):
        r=self.book(ohlc={'A':{D[1]:dict(open='20',high='30',low='1',close='15')}})
        self.assertEqual(r['shares']['A'],5);self.assertEqual(r['cash'],'0')
        self.assertTrue(any(x['event']=='UNFILLED_CASH_RATIONED_INTEGER_FLOOR' for x in r['order_log']))

    def test_sell_fill_proceeds_before_buy_and_costs(self):
        r=self.book(initial_cash='0',initial_shares={'B':10},orders=[order('A','BUY',10),order('B','SELL',10)],
            ohlc={'A':{D[1]:bar(10)},'B':{D[1]:bar(10)}},fee_bps='100',slippage_bps='100')
        fills=[x for x in r['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED']
        self.assertEqual([x['side'] for x in fills],['SELL','BUY']);self.assertEqual(r['shares']['A'],9)
        self.assertGreater(Fraction(r['cash']),0);self.assertGreater(Fraction(r['fees']),0)

    def test_split_units_once(self):
        r=self.book(initial_cash='0',initial_shares={'A':10},orders=[order('A','SELL',10)],
            ohlc={'A':{D[1]:bar(5)}},events=[dict(date=D[1],security_id='A',type='split',new_shares=2,old_shares=1,source_references=['official'])])
        self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['cash'],'100');self.assertEqual(r['shares']['A'],0)

    def test_unrecovered_drawdown(self):
        r=drawdown_summary([dict(date=str(i),equity=str(v)) for i,v in enumerate([100,90,80,85])])
        self.assertEqual(r['maximum_close_drawdown'],'1/5');self.assertFalse(r['recovered_at_end'])
        self.assertEqual(r['current_underwater_observations'],3)

    def test_distribution_existing_helper_keeps_rights(self):
        from test_return_priority_limit_book_v4 import event
        r=self.book(session_dates=D,initial_cash='0',initial_shares={'P':2},orders=[],
            ohlc={'P':{D[1]:bar(90),D[2]:bar(90)},'C':{D[1]:bar(20),D[2]:bar(20)}},
            distribution_events=[event('BEFORE_OPEN')],price_source_references={'P':['raw'],'C':['raw']})
        self.assertEqual(r['status'],'COMPLETE');self.assertEqual(r['daily_ledger'][-1]['equity'],'200')

    def test_ads_even_and_unpriced_fraction(self):
        from test_return_priority_ads_conversion import event, ACCOUNT_MODEL, D as dates
        args=dict(session_dates=dates,orders=[],initial_cash='100',
            ohlc={'ordinary':{dates[1]:bar(200),dates[2]:bar(210)}},events=[event()],
            account_model=ACCOUNT_MODEL,price_source_references={'ordinary':['raw']},fee_bps='0',slippage_bps='0')
        even=run_next_open_book(**args,initial_shares={'ads':4})
        odd=run_next_open_book(**args,initial_shares={'ads':3})
        self.assertEqual(even['status'],'COMPLETE');self.assertEqual(even['shares']['ordinary'],2)
        self.assertEqual(odd['status'],'BLOCKED');self.assertEqual(odd['distribution_rights'][0]['units'],'1/2')

    def test_real_saved_tiny_subset_v2_future_open_isolation(self):
        # One security/one opening session from saved data: mechanism integration,
        # not a full-domain economic experiment or new optimized result.
        p=json.loads(Path('tmp/next12_execution_prepare_20261014_v3/prepared.json').read_text())
        a=assemble_monthly_execution_inputs_v4(p)
        a['session_dates']=a['session_dates'][:2];a['monthly_inputs']=a['monthly_inputs'][:1]
        w=a['monthly_inputs'][0];args=w['search_arguments'];sid=sorted(args['prices'])[0]
        args['prices']={sid:args['prices'][sid]};args['metadata']={sid:args['metadata'][sid]}
        args['training_scenarios']=[{sid:x[sid]} for x in args['training_scenarios']]
        for path in REQUIRED_PINS:w['source_hashes'][path]=hashlib.sha256(Path(path).read_bytes()).hexdigest()
        base=dict(assembled=a,ohlc=p['ohlc'],initial_cash='2000',fee_bps='0',slippage_bps='0')
        first=run_daily_next_open(**base)
        changed=deepcopy(p['ohlc']);day=a['session_dates'][1]
        changed[sid][day]=bar('100000')
        second=run_daily_next_open(**dict(base,ohlc=changed))
        self.assertEqual(first['status'],'COMPLETE');self.assertEqual(second['status'],'COMPLETE')
        self.assertEqual(first['provider_audit'][0]['selection'],second['provider_audit'][0]['selection'])
        self.assertEqual(first['provider_audit'][0]['selection']['method'],'EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2')
        self.assertEqual(first['provider_audit'][0]['reserved_cash'],'0')
        self.assertEqual(first['provider_audit'][0]['orders'],second['provider_audit'][0]['orders'])
        self.assertTrue(all('decision_mark' in row and 'limit' not in row for row in first['provider_audit'][0]['orders']))

if __name__=='__main__':unittest.main()

