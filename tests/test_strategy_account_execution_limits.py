from copy import deepcopy
from datetime import datetime,timedelta,timezone
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from core.strategy_account_ledger import create_account,apply_event,canonical
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_account_unit_review import review_interval
from data.strategy_account_execution_limits import build_execution_limits
from data.strategy_account_live_pullback_cap_store import PullbackCapStore
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.strategy_account_preview import preview_scoped_account
from test_strategy_account_market_capture import Identity

class ExecutionLimitsTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.now=datetime(2026,10,16,14,tzinfo=timezone.utc);self.price=10;self.attempt=0
        self.state=create_account('real')
        self.event('DIRECT_FILL',security_id='BBB',side='BUY',quantity=2,price='10',fees='0',executed_at='2026-10-15T14:00:00Z',identity_evidence=Identity()('BBB'))
        self.event('CASH_CONFIRM',amount='100',cash_basis='TOTAL_UNINVESTED')
        self.cap=PullbackCapStore(self.root/'cap.db',clock=lambda:self.now.isoformat(),max_history_rows=32,max_history_bytes=8*1024*1024)
    def event(self,kind,**fields):
        self.state,_=apply_event(self.state,dict(event_id=str(len(self.state['events'])),kind=kind,**fields),expected_revision=self.state['revision'])
    def raw(self,ticker):
        opening=int(datetime(2026,10,16,13,30,tzinfo=timezone.utc).timestamp());count=30
        return canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=self.price,regularMarketTime=int(self.now.timestamp()),currentTradingPeriod=dict(regular=dict(start=opening,end=opening+23400))),timestamp=[opening+60*i for i in range(count)],indicators=dict(quote=[dict(open=[10]*count,high=[12]*count,low=[9]*count,close=[10]*count,volume=[10]*count)]))])))
    def package(self):
        self.attempt+=1
        package=StrategyAccountMarketCapture(identity_resolver=Identity(),fetch=self.raw,clock=lambda:self.now).capture(state=self.state,candidate_metadata={'AAA':{'ticker':'AAA'},'BBB':{'ticker':'BBB'}},output_directory=self.root/str(self.attempt))
        def daily(ticker,start,end):return dict(status=200,body=canonical(dict(chart=dict(error=None,result=[dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY'),events={})]))))
        rss=b'<rss><channel><title>Nasdaq</title><item><title>Unrelated notice</title><pubDate>Fri, 16 Oct 2026 13:00:00 GMT</pubDate></item></channel></rss>'
        sources=PaperActionEvidenceSources(fetch=daily,rss_fetch=lambda:dict(status=200,body=rss),clock=lambda:self.now)
        closed='2026-10-14T20:00:00Z';securities={s:{'ticker':s} for s in package['marks']}
        actions=sources.capture(dict(account_id=self.state['account_id'],state_revision=self.state['revision'],window_start=closed,observed_floor=closed,securities=securities,current_target_quantities={}))
        review=review_interval(state=self.state,securities=securities,marks=package['marks'],action_package=actions,training_manifest_sha256='a'*64,historical_search_arguments_sha256='b'*64,historical_price_basis='HISTORICAL',training_closed_at=closed,marks_sha256=sha256(canonical(package['marks'])).hexdigest(),now=self.now.isoformat())
        return package,review
    def build(self,package,review,**kwargs):
        return build_execution_limits(state=self.state,target_quantities=kwargs.pop('target_quantities',{'AAA':5}),market_capture=package,unit_review=review,cap_store=self.cap,now=self.now.isoformat(),**kwargs)
    def test_real_capture_review_buy_sell_and_no_raising_cap(self):
        package,review=self.package();first=self.build(package,review)
        self.assertEqual(set(first),{'marks','limits'});self.assertLess(Fraction(first['limits']['AAA']['buy']),10)
        self.assertEqual(first['limits']['BBB']['sell'],'10');self.assertIsNone(first['limits']['BBB']['cap_record_hash'])
        diff=preview_scoped_account(state=self.state,legacy_shares={},target_quantities={'AAA':5},now=self.now.isoformat(),maximum_mark_age_seconds=120,fee_bps='0',**first)
        self.assertEqual({o['side'] for o in diff['new_orders']},{'BUY','SELL'})
        self.assertEqual(next(o['quantity'] for o in diff['new_orders'] if o['side']=='SELL'),2)
        self.now+=timedelta(seconds=10);self.price=11;package,review=self.package();second=self.build(package,review)
        self.assertLessEqual(Fraction(second['limits']['AAA']['buy']),Fraction(first['limits']['AAA']['buy']))
        self.assertEqual(second['limits']['BBB']['sell'],'11')
        with self.assertRaisesRegex(ValueError,'CAP_INPUT_NOT_NEWER'):self.build(package,review)
    def test_expired_changed_source_and_review_binding_refused(self):
        package,review=self.package()
        bad=deepcopy(package);raw=next(p for p in bad['files'] if p.endswith('.raw'));bad['files'][raw]+=b' '
        with self.assertRaisesRegex(ValueError,'MARK_SOURCE_CHANGED'):self.build(bad,review)
        altered=deepcopy(review);altered['account_revision']='f'*64
        with self.assertRaisesRegex(ValueError,'UNIT_REVIEW_BINDING_INVALID'):self.build(package,altered)
        self.now+=timedelta(seconds=121)
        with self.assertRaises(ValueError):self.build(package,review)
    def test_initial_quote_domain_is_not_target(self):
        package,review=self.package();result=self.build(package,review,target_quantities=None,quote_domain={'AAA','BBB'})
        self.assertEqual(set(result['limits']),{'AAA','BBB'})
        with self.assertRaisesRegex(ValueError,'QUOTE_DOMAIN_OMITS_EXPOSURE'):self.build(package,review,target_quantities=None,quote_domain={'AAA'})
    def test_sell_limit_rounds_up_to_cent_without_buy_cap(self):
        self.price=10.001;package,review=self.package()
        result=self.build(package,review,target_quantities={})
        self.assertEqual(set(result['limits']),{'BBB'})
        self.assertEqual(result['limits']['BBB']['sell'],'1001/100')
        self.assertIsNone(result['limits']['BBB']['cap_record_hash'])
    def test_recent_minute_sell_does_not_require_full_buy_pullback_history(self):
        original=self.raw
        def recent_only(ticker):
            document=json.loads(original(ticker));chart=document['chart']['result'][0]
            chart['timestamp']=chart['timestamp'][-1:]
            for key,values in chart['indicators']['quote'][0].items():chart['indicators']['quote'][0][key]=values[-1:]
            return canonical(document)
        self.raw=recent_only
        package,review=self.package()
        result=self.build(package,review,target_quantities={})
        self.assertEqual(result['limits']['BBB']['sell'],'10')
        self.assertFalse(result['limits']['BBB']['buy_evaluated'])
        difference=preview_scoped_account(state=self.state,legacy_shares={},target_quantities={},now=self.now.isoformat(),maximum_mark_age_seconds=120,fee_bps='0',**result)
        self.assertEqual([(o['side'],o['quantity']) for o in difference['new_orders']],[('SELL',2)])
        with self.assertRaisesRegex(ValueError,'NONCONTIGUOUS_OR_FUTURE_MINUTE'):self.build(package,review)
        with self.assertRaisesRegex(ValueError,'NONCONTIGUOUS_OR_FUTURE_MINUTE'):
            self.build(package,review,target_quantities=None,quote_domain={'AAA','BBB'})

if __name__=='__main__':unittest.main()
