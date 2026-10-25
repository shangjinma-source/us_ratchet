from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
import unittest
from unittest.mock import patch
from datetime import datetime
from backtest.original_fixed_weight_cost_next_open import run_original_fixed_weight_next_open as run
from scripts.prepare_original_fixed_weight_cost_control import build_inputs,TSM


class FixedCostControlTests(unittest.TestCase):
    def fixture(self,fee='0'):
        dates=['2024-01-02','2024-01-03','2024-01-04','2024-01-05']
        closes={'A':dict(zip(dates,['10','10','20','20'])),'B':dict(zip(dates,['10','10','10','10']))}
        bars={s:{d:dict(open=p,high=p,low=p,close=p) for d,p in series.items()} for s,series in closes.items()}
        plans=[dict(decision_date=d,active_date=dates[dates.index(d)+1],search_arguments=dict(fee_bps=fee),source_hashes={},valuation_quotes=[dict(security_id=s,as_of=d,price=closes[s][d]) for s in closes]) for d in (dates[0],dates[2])]
        a=dict(session_dates=dates,monthly_inputs=plans,close_prices=closes,actions=[],provider_actions=[],cash_stock_merger_events=[],fractional_settlements={},price_source_references={'A':['fixture'],'B':['fixture']},distribution_events=[],distribution_fractional_cash_values={},account_model=None)
        return a,bars

    def test_real_book_own_equity_fee_sell_first_and_no_search(self):
        for fee,slip in [('0','5'),('1','10')]:
            a,bars=self.fixture(fee)
            with patch('backtest.continuous_guided_account_decision.original_search',side_effect=AssertionError('NO SEARCH')):
                result=run(weights={'A':'.5','B':'.5'},assembled=a,ohlc=bars,initial_cash='1000',fee_bps=fee,slippage_bps=slip)
            self.assertEqual(result['status'],'COMPLETE');self.assertEqual(result['search_calls'],0)
            audits=[r for r in result['provider_audit'] if r.get('selection')]
            self.assertEqual(len(audits),2)
            state=result['selection_account_states'][1]['account_state']
            equity=F(state['cash'])+state['shares']['A']*20+state['shares']['B']*10
            self.assertEqual(F(audits[1]['selection']['investable_equity']),equity)
            self.assertEqual(audits[1]['selection']['target_quantities'],{'A':int(equity/40),'B':int(equity/20)})
            fills=[r for r in result['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED']
            last=[r for r in fills if r['date']==a['session_dates'][-1]]
            self.assertEqual([r['side'] for r in last],['SELL','BUY'])
            for r in fills:
                opening=F(bars[r['security_id']][r['date']]['open'])
                expected=opening*(1+(F(slip)/10000 if r['side']=='BUY' else -F(slip)/10000))
                self.assertEqual(F(r['price']),expected)
                self.assertEqual(F(r['fee']),r['quantity']*expected*F(fee)/10000)
                self.assertGreaterEqual(F(r['cash_after']),0)

    def test_next_open_not_used_for_target_and_split_once(self):
        a,bars=self.fixture();a['monthly_inputs']=a['monthly_inputs'][:1]
        action=dict(security_id='A',date=a['session_dates'][2],type='split',new_shares=2,old_shares=1,source_references=['fixture'])
        a['actions']=[action];a['provider_actions']=[action]
        result=run(weights={'A':'.5','B':'.5'},assembled=a,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5')
        self.assertEqual(result['status'],'COMPLETE')
        self.assertEqual(result['provider_audit'][0]['target_shares']['A'],50)
        self.assertEqual(result['provider_audit'][2]['target_shares']['A'],100)
        self.assertEqual(len(result['provider_audit'][2]['target_adjustments']),1)
        other=deepcopy(bars);other['A'][a['session_dates'][1]]={k:'100' for k in ('open','high','low','close')}
        changed=run(weights={'A':'.5','B':'.5'},assembled=a,ohlc=other,initial_cash='1000',fee_bps='0',slippage_bps='5')
        self.assertEqual(changed['provider_audit'][0]['target_shares'],result['provider_audit'][0]['target_shares'])

    def test_split_holdings_and_next_month_post_split_sizing_both_costs(self):
        for fee,slip in [('0','5'),('1','10')]:
            a,bars=self.fixture(fee)
            days=a['session_dates']+['2024-01-08']
            a['session_dates']=days
            a['close_prices']={'A':dict(zip(days,['100','100','10','11','11'])),'B':{d:'10' for d in days}}
            bars={sid:{d:{k:p for k in ('open','high','low','close')} for d,p in series.items()} for sid,series in a['close_prices'].items()}
            for plan,day in zip(a['monthly_inputs'],(days[0],days[3])):
                plan.update(decision_date=day,active_date=days[days.index(day)+1])
                plan['valuation_quotes']=[dict(security_id=sid,as_of=day,price=a['close_prices'][sid][day]) for sid in ('A','B')]
            split=dict(type='split',security_id='A',date=days[2],new_shares=10,old_shares=1,source_references=['fixture'])
            a['actions']=[split];a['provider_actions']=[split]
            saved=deepcopy((a,bars))
            r=run(weights={'A':'.5','B':'.5'},assembled=a,ohlc=bars,initial_cash='10000',fee_bps=fee,slippage_bps=slip)
            self.assertEqual(r['status'],'COMPLETE');self.assertEqual((a,bars),saved)
            ledger={x['date']:x for x in r['daily_ledger']}
            split_net=sum(x['quantity']*(1 if x['side']=='BUY' else -1) for x in r['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED' and x['date']==days[2] and x['security_id']=='A')
            self.assertEqual(ledger[days[2]]['shares']['A'],ledger[days[1]]['shares']['A']*10+split_net)
            self.assertEqual(r['provider_audit'][2]['target_shares']['A'],r['provider_audit'][1]['target_shares']['A']*10)
            state=r['selection_account_states'][1]['account_state']
            self.assertEqual(state['shares'],ledger[days[3]]['shares'])
            equity=F(state['cash'])+state['shares']['A']*11+state['shares']['B']*10
            self.assertEqual(r['provider_audit'][3]['selection']['target_quantities'],{'A':int(equity/22),'B':int(equity/20)})

    def test_invalid_weights_cost_and_quote_fail_closed(self):
        a,bars=self.fixture()
        with self.assertRaisesRegex(ValueError,'WEIGHT_SUM'):run(weights={'A':'.8','B':'.8'},assembled=a,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5')
        with self.assertRaisesRegex(ValueError,'FEE_MISMATCH'):run(weights={'A':'.5','B':'.5'},assembled=a,ohlc=bars,initial_cash='1000',fee_bps='1',slippage_bps='10')
        a['monthly_inputs'][0]['valuation_quotes'][0]['as_of']='2099-01-01'
        self.assertEqual(run(weights={'A':'.5','B':'.5'},assembled=a,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5')['status'],'BLOCKED')

    def test_unheld_merger_zero_position_does_not_block_next_reset(self):
        a,bars=self.fixture()
        a['actions']=[dict(type='merger',security_id='EXTERNAL',date=a['session_dates'][1],share_cash='10',source_references=['fixture'])]
        r=run(weights={'A':'.5','B':'.5'},assembled=a,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5')
        self.assertEqual(r['status'],'COMPLETE')
        self.assertEqual(r['selection_account_states'][1]['account_state']['shares']['EXTERNAL'],0)
        self.assertEqual(len([x for x in r['provider_audit'] if x.get('selection')]),2)

    def test_nonzero_unquoted_successor_still_blocks(self):
        a,bars=self.fixture();a['close_prices']['X']=deepcopy(a['close_prices']['A']);bars['X']=deepcopy(bars['A'])
        event=dict(type='split_identity',security_id='A',new_security_id='X',date=a['session_dates'][2],new_shares=1,old_shares=1,source_references=['fixture'])
        a['actions']=[event];a['provider_actions']=[event]
        r=run(weights={'A':'.5','B':'.5'},assembled=a,ohlc=bars,initial_cash='1000',fee_bps='0',slippage_bps='5')
        self.assertEqual(r['status'],'BLOCKED')
        self.assertGreater(r['selection_account_states'][1]['account_state']['shares']['X'],0)

    def builder_fixture(self):
        dates=['2024-01-02','2024-01-03'];tickers=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
        definitions=[dict(ticker=t,security_id=TSM if t=='TSM' else t,issuer_id=t,target_weight=.125) for t in tickers]
        meta={r['security_id']:dict(ticker=r['ticker'],issuer_id=r['issuer_id']) for r in definitions if r['ticker']!='TSM'}
        closes={s:{d:'10' for d in dates} for s in meta};bars={s:{d:{k:'10' for k in ('open','high','low','close')} for d in dates} for s in meta}
        assembled=dict(session_dates=dates,metadata=meta,close_prices=closes,price_source_references={s:['fixture'] for s in meta},monthly_inputs=[dict(decision_date=dates[0],valuation_quotes=[],search_arguments={})])
        chart=dict(meta=dict(symbol='TSM',currency='USD',exchangeName='NYQ',instrumentType='EQUITY',exchangeTimezoneName='America/New_York'),timestamp=[int(datetime.fromisoformat(d+'T16:00:00-05:00').timestamp()) for d in dates],indicators={'quote':[{k:[10,10] for k in ('open','high','low','close')}]},events={})
        raw=json.dumps({'chart':{'result':[chart]}}).encode()
        return dict(assembled=assembled,prepared=dict(session_dates=dates,initial_cash='20000',initial_shares={},ohlc=bars),control={'definition':{'securities':definitions}},raw=raw,receipt=dict(raw_sha256=sha256(raw).hexdigest(),status='RAW_CAPTURED',http_status=200,body_truncated=False))

    def test_builder_exact_calendar_and_preserves_existing_channels(self):
        args=self.builder_fixture();saved=deepcopy(args);r=build_inputs(**args)
        self.assertEqual(args,saved);self.assertEqual(len(r['weights']),8)
        self.assertEqual(r['ohlc']['NVDA'],args['prepared']['ohlc']['NVDA'])
        self.assertEqual(len(r['assembled']['monthly_inputs'][0]['valuation_quotes']),8)
        self.assertEqual(set(r['ohlc'][TSM]),set(args['assembled']['session_dates']))

    def test_action_closure_retains_child_successors_excludes_unrelated(self):
        args=self.builder_fixture();a=args['assembled']
        related=dict(parent_sid='NVDA',post_parent_sid='NVDA2',child_sid='CHILD')
        child=dict(security_id='CHILD',new_security_id='CHILD2')
        unrelated=dict(parent_sid='WDC',post_parent_sid='WDC2',child_sid='SNDK')
        a['distribution_events']=[related,unrelated];a['actions']=[child]
        r=build_inputs(**args,event_scope='ORIGINAL_IDENTITY_CLOSURE_CANDIDATE')['assembled']
        self.assertEqual(r['distribution_events'],[related]);self.assertEqual(r['actions'],[child])
        scope=r['original_control_action_scope']
        self.assertIn('CHILD2',scope['reachable_security_ids'])
        self.assertEqual(scope['excluded_events'][0]['event'],unrelated)
        default=build_inputs(**args)['assembled']
        self.assertEqual(default['distribution_events'],[related,unrelated])
        self.assertEqual(default['original_control_action_scope']['excluded_events'],[])

    def test_builder_rejects_missing_coordinate_action_and_hash(self):
        for mode in ['missing','currency','split','hash']:
            args=self.builder_fixture();v=json.loads(args['raw']);chart=v['chart']['result'][0]
            if mode=='missing':chart['timestamp'][1]+=86400
            if mode=='currency':chart['meta']['currency']='TWD'
            if mode=='split':chart['events']['splits']={'x':{'ratio':'2:1'}}
            args['raw']=json.dumps(v).encode()
            if mode!='hash':args['receipt']['raw_sha256']=sha256(args['raw']).hexdigest()
            else:args['receipt']['raw_sha256']='0'*64
            with self.subTest(mode=mode),self.assertRaises(ValueError):build_inputs(**args)


if __name__=='__main__':unittest.main()
