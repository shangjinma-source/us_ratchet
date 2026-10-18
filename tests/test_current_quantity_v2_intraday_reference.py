import json
import unittest
from copy import deepcopy
from datetime import datetime,timedelta
from fractions import Fraction
from hashlib import sha256
from data.current_quantity_v2_intraday_reference import CurrentQuantityV2IntradayReference,VERSION,METHOD

NOW=datetime.fromisoformat('2026-10-15T12:00:30-04:00')

def raw(ticker,price=9):
    t=int(NOW.timestamp())
    return json.dumps({'chart':{'error':None,'result':[{'meta':{'symbol':ticker,'currency':'USD','instrumentType':'EQUITY','exchangeTimezoneName':'America/New_York','dataGranularity':'1m','regularMarketPrice':price,'regularMarketTime':t-5,'currentTradingPeriod':{'regular':{'start':t-9030,'end':t+14370}}},'timestamp':[t-90],'indicators':{'quote':[{'open':[price],'high':[price+1],'low':[price-1],'close':[price],'volume':[10]}]}}]}}).encode()

def fixture():
    args={'prices':{'a':'10','b':'20'},'metadata':{'a':{'ticker':'AAA','issuer_id':'ia'},'b':{'ticker':'BBB','issuer_id':'ib'}}}
    inp=json.dumps({'search_arguments':args}).encode()
    manifest={'candidates':[{'security_id':sid,'ticker':m['ticker'],'issuer_id':m['issuer_id'],'status':'READY_CONDITIONAL','identity_reviewed':True,'coordinate_reviewed':True,'identity_source_references':['identity.json'],'true_share_events':[]} for sid,m in args['metadata'].items()]}
    files={'manifest.json':json.dumps(manifest).encode(),'identity.json':b'{"synthetic":true}'}
    pins={k:sha256(v).hexdigest() for k,v in files.items()}
    snapshot={'research_id':'a'*24,'research_version':VERSION,'method_version':METHOD,'research_only':True,'execution_blocked':True,'orders_created':False,'executable_buy_quantities':None,'status':'AVAILABLE','as_of':'2026-10-13','input_sha256':sha256(inp).hexdigest(),'sources':pins,'available_cash_exact':'100','investable_equity_exact':'100','budget_identity_exact':{'entered_cash':'100','stock_notional':'90','residual_cash':'10','fees':'0'},'target_quantities':{'a':3,'b':3},'stocks':[{'security_id':'a','ticker':'AAA','units':3},{'security_id':'b','ticker':'BBB','units':3}]}
    clock=[NOW];quotes={'AAA':raw('AAA'), 'BBB':raw('BBB',24)}
    pack={'manifest_path':'manifest.json','source_hashes':pins,'files':files}
    service=CurrentQuantityV2IntradayReference(snapshot_reader=lambda _:deepcopy(snapshot), input_reader=lambda _:inp,identity_reader=lambda *args:deepcopy(pack),quote_reader=lambda s:{'raw':quotes[s['ticker']],'captured_at':NOW},clock=lambda:clock[0])
    return service,snapshot,clock,quotes,pack

class ReferenceTests(unittest.TestCase):
    def test_multi_cash_exact_no_per_stock_full_cash_and_no_mutation(self):
        s,snapshot,_,_,_=fixture();before=deepcopy(snapshot);r=s.preview('a'*24)
        self.assertEqual(r['status'],'AVAILABLE');self.assertEqual([x['quantity'] for x in r['stocks']],[3,2])
        self.assertEqual([x['limit_price'] for x in r['stocks']],['8.00','23.00'])
        self.assertEqual(Fraction(r['indicative_notional']),70);self.assertEqual(Fraction(r['remaining_cash']),30)
        self.assertEqual(snapshot,before);self.assertFalse(r['orders_created']);self.assertFalse(r['source_authenticated'])
    def test_missing_stale_future_and_failed_quotes_never_fallback(self):
        for mode in ('missing','stale','future'):
            s,_,clock,quotes,_=fixture()
            if mode=='missing':quotes.pop('AAA')
            elif mode=='stale':clock[0]+=timedelta(seconds=121)
            else:
                p=json.loads(quotes['AAA']);p['chart']['result'][0]['meta']['regularMarketTime']=int(NOW.timestamp())+1;quotes['AAA']=json.dumps(p).encode()
            r=s.preview('a'*24);self.assertIsNone(r['stocks'][0]['limit_price']);self.assertEqual(r['stocks'][0]['quantity'],0)
            self.assertEqual(Fraction(r['indicative_notional'])+Fraction(r['remaining_cash']),100)
    def test_identity_bytes_equity_and_known_split_rejected_per_stock(self):
        for mode in ('bytes','equity','split','sid'):
            s,_,_,quotes,pack=fixture()
            if mode=='bytes':pack['files']['identity.json']=b'changed'
            else:
                p=json.loads(quotes['AAA']);q=p['chart']['result'][0]
                if mode=='equity':q['meta']['instrumentType']='ETF'
                elif mode=='sid':q['meta']['symbol']='BBB'
                else:q['events']={'splits':{'x':{'date':int(NOW.timestamp())}}}
                quotes['AAA']=json.dumps(p).encode()
            self.assertIsNone(s.preview('a'*24)['stocks'][0]['limit_price'])
    def test_global_gate_cash_targets_input_and_incomplete(self):
        for change in (lambda p:p.update(status='INCOMPLETE'),lambda p:p.update(input_sha256='0'*64),lambda p:p['target_quantities'].update(a=True),lambda p:p.update(available_cash_exact='99'),lambda p:p.update(research_version='TOP1')):
            s,p,_,_,_=fixture();change(p)
            with self.assertRaises(ValueError):s.preview('a'*24)
    def test_slow_second_quote_expires_first_and_all_cash_needs_no_quotes(self):
        s,p,clock,quotes,_=fixture()
        def reader(stock):
            if stock['ticker']=='BBB':clock[0]+=timedelta(seconds=121)
            return {'raw':quotes[stock['ticker']],'captured_at':NOW}
        s.quote_reader=reader;r=s.preview('a'*24)
        self.assertTrue(all(row['limit_price'] is None for row in r['stocks']))
        s,p,_,_,_=fixture();p.update(status='ALL_CASH',stocks=[],target_quantities={});p['budget_identity_exact'].update(stock_notional='0',residual_cash='100')
        s.quote_reader=lambda _:self.fail('ALL_CASH quote read');s.identity_reader=lambda *a:self.fail('ALL_CASH identity read')
        r=s.preview('a'*24);self.assertEqual(r['status'],'ALL_CASH');self.assertEqual(r['remaining_cash'],'100')

if __name__=='__main__':unittest.main()
