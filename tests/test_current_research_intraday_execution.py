import unittest
from copy import deepcopy
from datetime import datetime,timedelta
from data.current_research_intraday_execution import IntradayExecutionService,decode_intraday_reference,TOP1_METHOD,TOP1_VERSION
from fractions import Fraction as F

NOW=datetime.fromisoformat('2026-10-15T12:00:30-04:00')
def payload():
    ts=int(NOW.timestamp());opening=int(NOW.replace(hour=9,minute=30,second=0).timestamp());closing=int(NOW.replace(hour=16,minute=0,second=0).timestamp())
    return {'chart':{'error':None,'result':[{'meta':dict(symbol='SNDK',currency='USD',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=1412.349,regularMarketTime=ts-5,currentTradingPeriod={'regular':dict(start=opening,end=closing)}),
        'timestamp':[ts-90,ts-30,ts-1], 'indicators':{'quote':[dict(open=[1413,None,1400],high=[1414,None,1500],low=[1412.125,None,1],close=[1413,None,1400],volume=[10,None,0])]}}]}}
def snapshot(_):return dict(research_id='a'*24,research_only=True,execution_blocked=True,status='AVAILABLE',method=TOP1_METHOD,research_version=TOP1_VERSION,
    budget=20000,budget_identity_exact=dict(entered_cash='20000',stock_notional='19270.29',fees='0',residual_cash='729.71'),
    selected_security=dict(security_id='sndk',ticker='SNDK'),selected_ranking_security_id='sndk',as_of='2026-10-13',stocks=[dict(security_id='sndk',ticker='SNDK',units=13,close=1482.33)])

class IntradayTests(unittest.TestCase):
    def test_completed_low_and_last_min_cent_no_partial_snapshot(self):
        r=decode_intraday_reference(payload(),ticker='SNDK',now=NOW)
        self.assertEqual(r['observed_cap'],'1412.12');self.assertEqual(r['minute_end'],(NOW-timedelta(seconds=30)).astimezone(__import__('datetime').timezone.utc).isoformat())
        p=payload();p['chart']['result'][0]['meta']['regularMarketPrice']='1410.999'
        self.assertEqual(decode_intraday_reference(p,ticker='SNDK',now=NOW)['observed_cap'],'1410.99')
    def test_nonincreasing_cap_failure_never_reuses_and_new_session_key(self):
        p=payload();clock=[NOW];service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:p,clock=lambda:clock[0])
        first=service.preview('a'*24)['stocks'][0];self.assertEqual(first['units'],13)
        q=p['chart']['result'][0]['indicators']['quote'][0]
        for key in ('open','high','low','close'):q[key][0]+=10
        p['chart']['result'][0]['meta']['regularMarketPrice']+=10
        second=service.preview('a'*24)['stocks'][0];self.assertEqual(second['limit_price'],first['limit_price']);self.assertTrue(second['cap_locked_below_observed'])
        clock[0]=NOW+timedelta(seconds=121)
        stale=service.preview('a'*24)['stocks'][0];self.assertEqual(stale['status'],'UNAVAILABLE');self.assertIsNone(stale['limit_price'])
        self.assertNotIn('observed_cap',stale)
        restarted=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:p,clock=lambda:NOW)
        self.assertEqual(restarted.preview('a'*24)['stocks'][0]['limit_price'],'1422.12')
    def test_stale_future_wrong_identity_and_session_rejected(self):
        changes=[lambda r:r['meta'].update(regularMarketTime=int(NOW.timestamp())+1),
                 lambda r:r['meta'].update(regularMarketTime=int(NOW.timestamp())-121),
                 lambda r:r['meta'].update(symbol='OTHER'),lambda r:r['meta'].update(currency='HKD'),
                 lambda r:r['meta'].update(dataGranularity='1d'),
                 lambda r:r['meta']['currentTradingPeriod']['regular'].update(end=int(NOW.timestamp())),
                 lambda r:r['indicators']['quote'][0]['low'].__setitem__(0,1415),
                 lambda r:r['indicators']['quote'][0]['close'].__setitem__(0,float('nan')),
                 lambda r:r['indicators']['quote'][0]['volume'].__setitem__(0,0)]
        for change in changes:
            p=payload();change(p['chart']['result'][0])
            with self.subTest(change=change),self.assertRaises(ValueError):decode_intraday_reference(p,ticker='SNDK',now=NOW)
    def test_minute_age_independent_of_fresh_last_and_boundary(self):
        p=payload();r=p['chart']['result'][0];r['timestamp'][0]-=120
        with self.assertRaisesRegex(ValueError,'MINUTE_STALE'):decode_intraday_reference(p,ticker='SNDK',now=NOW)
        p=payload();p['chart']['result'][0]['meta']['regularMarketTime']=int(NOW.timestamp())-120
        r=decode_intraday_reference(p,ticker='SNDK',now=NOW)
        self.assertEqual(datetime.fromisoformat(r['refresh_by']),NOW)
    def test_pending_future_response_only_after_successful_fetch_and_clock_arrival(self):
        now=[NOW];p=payload();p['chart']['result'][0]['meta']['regularMarketTime']=int(NOW.timestamp())+7
        fetched=[p]
        service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:deepcopy(fetched[0]),clock=lambda:now[0])
        first=service.preview('a'*24)['stocks'][0]
        self.assertEqual(first['reason'],'LAST_QUOTE_FUTURE');self.assertIsNone(first['limit_price'])
        now[0]=NOW+timedelta(seconds=10)
        fetched[0]=deepcopy(p);fetched[0]['chart']['result'][0]['meta']['regularMarketTime']=int(now[0].timestamp())+7
        second=service.preview('a'*24)['stocks'][0]
        self.assertEqual(second['status'],'AVAILABLE');self.assertEqual(second['quote_response_origin'],'PENDING_RESPONSE_NOW_VALID')
        self.assertEqual(second['quote_response_age_seconds'],10);self.assertEqual(second['limit_price'],'1412.12')
        service.fetch=lambda _:(_ for _ in ()).throw(OSError('offline'))
        self.assertEqual(service.preview('a'*24)['stocks'][0]['status'],'UNAVAILABLE')
        now[0]=NOW+timedelta(seconds=250)
        fresh=payload();fresh['chart']['result'][0]['meta']['regularMarketTime']=int(now[0].timestamp())+7
        fresh['chart']['result'][0]['timestamp'][0]=int(now[0].timestamp())//60*60-60
        service.fetch=lambda _:fresh
        stale=service.preview('a'*24)['stocks'][0]
        self.assertEqual(stale['status'],'UNAVAILABLE');self.assertIsNone(stale['limit_price'])
        self.assertEqual(stale['reason'],'LAST_QUOTE_STALE')

    def test_pending_partial_bar_never_matures_from_old_bytes(self):
        clock=[NOW];old=payload();r=old['chart']['result'][0]
        r['meta']['regularMarketTime']=int(NOW.timestamp())+7
        q=r['indicators']['quote'][0]
        for key,value in [('open',100),('high',101),('low',99),('close',100),('volume',10)]:q[key][1]=value
        current=[old]
        service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:deepcopy(current[0]),clock=lambda:clock[0])
        self.assertEqual(service.preview('a'*24)['stocks'][0]['status'],'UNAVAILABLE')
        clock[0]=NOW+timedelta(seconds=40)
        current[0]=payload();current[0]['chart']['result'][0]['meta']['regularMarketTime']=int(clock[0].timestamp())+7
        result=service.preview('a'*24)['stocks'][0]
        self.assertEqual(result['status'],'AVAILABLE');self.assertEqual(result['quote_response_origin'],'PENDING_RESPONSE_NOW_VALID')
        self.assertEqual(result['limit_price'],'1412.12')
        self.assertEqual(result['minute_end'],(NOW-timedelta(seconds=30)).astimezone(__import__('datetime').timezone.utc).isoformat())

    def test_fresh_cash_exact_identity_quantity_grows_without_target_change(self):
        p=payload();service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:p,clock=lambda:NOW)
        row=service.preview('a'*24)['stocks'][0];fresh=row['fresh_cash_reference']
        self.assertEqual(row['units'],13);self.assertEqual(row['sealed_target_units'],13);self.assertEqual(fresh['quantity'],14)
        self.assertEqual(F(fresh['notional'])+F(fresh['residual_cash'])+F(fresh['commission']),F(20000))
        p['chart']['result'][0]['meta']['regularMarketPrice']='1000'
        row=service.preview('a'*24)['stocks'][0];self.assertEqual(row['fresh_cash_reference']['quantity'],20);self.assertEqual(row['units'],13)
    def test_old_allcash_still_uses_same_winner_and_cash_binding_is_strict(self):
        snap=snapshot(None);snap.update(status='ALL_CASH',stocks=[],budget=1450,budget_identity_exact=dict(entered_cash='1450',stock_notional='0',fees='0',residual_cash='1450'))
        seen=[]
        service=IntradayExecutionService(snapshot_reader=lambda _:snap,fetch=lambda t:seen.append(t) or payload(),clock=lambda:NOW)
        row=service.preview('a'*24)['stocks'][0]
        self.assertEqual(seen,['SNDK']);self.assertEqual(row['units'],0);self.assertEqual(row['fresh_cash_reference']['quantity'],1)
        snap['budget_identity_exact']['residual_cash']='1451'
        with self.assertRaisesRegex(ValueError,'EXACT_BUDGET_IDENTITY_MISMATCH'):service.preview('a'*24)
        self.assertEqual(len(seen),1)
        snap['budget_identity_exact']['residual_cash']='1450';snap['method']='OTHER'
        with self.assertRaisesRegex(ValueError,'CURRENT_TOP1_METHOD_REQUIRED'):service.preview('a'*24)

    def test_fetch_failure_has_no_cash_reference(self):
        service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:(_ for _ in ()).throw(OSError('offline')),clock=lambda:NOW)
        row=service.preview('a'*24)['stocks'][0];self.assertEqual(row['status'],'UNAVAILABLE');self.assertIsNone(row['limit_price']);self.assertEqual(row['historical_reference']['close'],1482.33)
        self.assertNotIn('fresh_cash_reference',row)

if __name__=='__main__':unittest.main()
