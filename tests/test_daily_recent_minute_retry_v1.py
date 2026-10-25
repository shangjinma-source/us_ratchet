from copy import deepcopy
from datetime import timedelta
from functools import partial
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from fractions import Fraction
import json
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_daily_composition_v7 import DailyCompositionV7
from data.strategy_recent_minute_retry_v1 import build_execution_limits, RecentClosedMinuteUnavailable, retry_evidence, classify_recent_null
from data.strategy_halt_aware_pullback_cap_store_v2 import PullbackCapStore
from data.strategy_account_market_capture import StrategyAccountMarketCapture
from data.strategy_halt_market_capture_v1 import HaltMarketCaptureV1
from data.strategy_halt_gap_diagnostic_v1 import HEADER, SOURCE_URL
from test_daily_composition_v3 import CompositionTests, POLICY


class RecentMinuteRetryTests(unittest.TestCase):
    def setup(self, directory, mode='normal'):
        c=CompositionTests().setup_case(directory,'A')
        c.clock[0]=c.clock[0].replace(second=0,microsecond=500000)
        c.store.append(dict(event_id='cash-retry',kind='CASH_CONFIRM',amount='1000',cash_basis='TOTAL_UNINVESTED'),expected_revision=c.store.read()['revision'])
        c.state=c.store.read();c.round=0;c.sleeps=[];c.mono=[0.0]
        class Identity:
            def __call__(self,ticker):return dict(ticker=ticker,security_id={'AAA':'A','BBB':'B'}[ticker],source_references=['identity-only'],source_hashes={'identity-only':sha256(b'id').hexdigest()})
            def _read(self,path,h):return b'id'
        def raw(ticker):
            opening=c.clock[0].replace(hour=14,minute=30,second=0,microsecond=0)
            count=int((c.clock[0]-opening).total_seconds()//60)
            q={k:[10]*count for k in ('open','high','low','close','volume')}
            bad=ticker=='BBB' and (c.round==1 or mode=='repeat')
            if bad:
                index=-2 if mode=='older' else -1
                for k in q:q[k][index]=None
                if mode=='partial':q['volume'][index]=0
            if mode=='sell_bad' and c.round>=3 and ticker=='AAA':raise ValueError('MARKET_HTTP_FAILED')
            meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',exchangeTimezoneName='America/New_York',dataGranularity='1m',regularMarketPrice=10,regularMarketTime=int(c.clock[0].timestamp()),currentTradingPeriod=dict(regular=dict(start=int(opening.timestamp()),end=int((opening+timedelta(hours=6,minutes=30)).timestamp()))))
            chart=dict(meta=meta,timestamp=[int(opening.timestamp())+i*60 for i in range(count)],indicators=dict(quote=[q]))
            if mode=='prior_minute_snapshot' and ticker=='BBB':
                meta['regularMarketTime']=int(c.clock[0].replace(second=0,microsecond=0).timestamp())-1
                chart['timestamp'].append(meta['regularMarketTime'])
                for key in q:q[key].append(0 if key=='volume' else 10)
            return canonical(dict(chart=dict(error=None,result=[chart])))
        c.raw=raw
        html=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode()
        capture=HaltMarketCaptureV1(StrategyAccountMarketCapture(identity_resolver=Identity(),fetch=raw,clock=lambda:c.clock[0]),fetch=lambda:dict(url=SOURCE_URL,status=200,body=html),clock=lambda:c.clock[0])
        def market(**kwargs):
            c.round+=1
            return capture.capture(**kwargs)
        c.provider.market=SimpleNamespace(capture=market)
        c.caps=PullbackCapStore(Path(directory)/'haltcaps.sqlite3',clock=lambda:c.clock[0].isoformat(),max_history_rows=100,max_history_bytes=8*1024*1024)
        c.provider.limits=partial(build_execution_limits,cap_store=c.caps)
        def sleep(seconds):
            c.sleeps.append(seconds);c.mono[0]+=seconds
            c.clock[0]+=timedelta(seconds=-1 if mode=='clock_back' else seconds)
            if mode=='account_changed':c.store.append(dict(event_id='othercash',kind='CASH_CONFIRM',amount='999',cash_basis='TOTAL_UNINVESTED'),expected_revision=c.store.read()['revision'])
            if mode=='target_changed':c.target['payload']['target_quantities']['B']=22
        c.service=DailyCompositionV7(monthly_service=c.monthly,evidence_reader=c.reader,execution_provider=c.provider.execution,clock=lambda:c.clock[0],policy_execution_enabled=True,policy_id=POLICY,fee_bps='10',sleep=sleep,monotonic=lambda:c.mono[0])
        return c

    def preview(self,c):return c.service.preview(expected_revision=c.state['revision'],target_id=c.target['target_id'])

    def test_full_provider_corrected_raw_once_and_no_state_change(self):
        with TemporaryDirectory() as d:
            c=self.setup(d);before=c.store.path.read_bytes();target=deepcopy(c.target)
            result=self.preview(c)
            self.assertEqual(result['status'],'READY');self.assertEqual(c.round,2);self.assertEqual(c.sleeps,[2])
            self.assertEqual({o['side'] for o in result['new_orders']},{'BUY','SELL'})
            self.assertEqual(result['minute_recapture']['eligibility']['all_buy_security_ids'],['B'])
            self.assertEqual(result['minute_recapture']['eligibility']['recent_nulls'][0]['security_id'],'B')
            self.assertEqual(c.store.path.read_bytes(),before);self.assertEqual(c.target,target)
            self.assertEqual(len(list(c.provider.output.glob('daily-*/*/failed.json'))),1)
            self.assertTrue(Path(result['minute_recapture']['audit_path']).is_file())

    def test_repeat_fails_to_independent_sells_without_third_buy_capture(self):
        with TemporaryDirectory() as d:
            c=self.setup(d,'repeat');result=self.preview(c)
            self.assertEqual(c.round,3);self.assertEqual(c.sleeps,[2])
            self.assertEqual([(o['security_id'],o['side']) for o in result['new_orders']],[('A','SELL')])
            self.assertEqual(result['waiting_data'][0]['security_id'],'B')
            self.assertEqual(len(list(c.provider.output.glob('daily-*/*/failed.json'))),2)

    def test_older_and_partial_never_wait_or_retry_buy(self):
        for mode in ('older','partial'):
            with self.subTest(mode=mode),TemporaryDirectory() as d:
                c=self.setup(d,mode);result=self.preview(c)
                self.assertEqual(c.sleeps,[]);self.assertEqual(c.round,2)
                self.assertTrue(all(o['side']=='SELL' for o in result['new_orders']))

    def test_wait_clock_and_snapshot_changes_block_new_capture(self):
        for mode in ('clock_back','account_changed','target_changed'):
            with self.subTest(mode=mode),TemporaryDirectory() as d:
                c=self.setup(d,mode)
                with self.assertRaises(ValueError):self.preview(c)
                self.assertEqual(c.round,1);self.assertEqual(c.sleeps,[2])

    def test_recapture_expiry_cannot_return_orders(self):
        with TemporaryDirectory() as d:
            c=self.setup(d);original=c.provider.limits
            def late(**kwargs):
                result=original(**kwargs)
                if c.round==2:c.clock[0]+=timedelta(seconds=121)
                return result
            c.provider.limits=late
            with self.assertRaises(ValueError):self.preview(c)
            self.assertEqual(c.round,2)

    def test_sell_capture_failure_is_not_hidden(self):
        with TemporaryDirectory() as d:
            c=self.setup(d,'repeat');original=c.provider.market.capture
            def reject(**kwargs):
                if c.round==2:raise ValueError('SELL_SOURCE_BLOCKED')
                return original(**kwargs)
            c.provider.market.capture=reject
            with self.assertRaisesRegex(ValueError,'SELL_SOURCE_BLOCKED'):self.preview(c)
            self.assertEqual(c.sleeps,[2])

    def test_existing_cap_never_raised_by_recapture(self):
        with TemporaryDirectory() as d:
            c=self.setup(d);c.clock[0]-=timedelta(seconds=10)
            doc=json.loads(c.raw('BBB'));row=doc['chart']['result'][0]
            row['meta']['regularMarketPrice']=8
            for key in ('open','high','low','close'):row['indicators']['quote'][0][key]=[8]*len(row['timestamp'])
            raw=canonical(doc);period=row['meta']['currentTradingPeriod']['regular']
            from datetime import datetime,timezone
            cap=c.caps.candidate(raw=raw,expected_sha256=sha256(raw).hexdigest(),security_id='B',ticker='BBB',session='2026-11-02',
                session_open=datetime.fromtimestamp(period['start'],timezone.utc).isoformat(),session_close=datetime.fromtimestamp(period['end'],timezone.utc).isoformat(),
                captured_at=c.clock[0].isoformat(),checked_at=c.clock[0].isoformat(),now=c.clock[0].isoformat(),rebound_fraction='1/2',minimum_discount='1/200',maximum_age_seconds=120)
            c.clock[0]+=timedelta(seconds=10)
            result=self.preview(c)
            self.assertLessEqual(Fraction(result['reference_quotes']['B']['buy']),Fraction(cap['candidate']['limit_price']))
            self.assertEqual(c.round,2)

    def test_all_buy_sids_checked_not_only_first_exception(self):
        import test_strategy_account_execution_limits as fixtures
        f=fixtures.ExecutionLimitsTests();f.setUp()
        try:
            original=f.raw
            def raw(ticker):
                doc=json.loads(original(ticker));quote=doc['chart']['result'][0]['indicators']['quote'][0]
                for values in quote.values():values[-1 if ticker=='AAA' else -2]=None
                return canonical(doc)
            f.raw=raw;package,review=f.package()
            html=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode()
            receipt=canonical(dict(url=SOURCE_URL,http_status=200,bytes=len(html),raw_sha256=sha256(html).hexdigest(),started_at=f.now.isoformat(),received_at=f.now.isoformat()))
            package['files'].update({'halt.raw':html,'halt.receipt':receipt})
            package['source_hashes'].update({key:sha256(value).hexdigest() for key,value in [('halt.raw',html),('halt.receipt',receipt)]})
            package['halt_evidence']=dict(raw_path='halt.raw',receipt_path='halt.receipt')
            with self.assertRaises(ValueError) as error:
                build_execution_limits(state=f.state,target_quantities={'AAA':5,'BBB':5},market_capture=package,unit_review=review,cap_store=f.cap,now=f.now.isoformat())
            self.assertNotIsInstance(error.exception,RecentClosedMinuteUnavailable)
        finally:f.doCleanups()

    def test_signal_expiry_during_wait_blocks_recapture(self):
        from data.strategy_daily_rebinding_reader import ArchivedRebindingDailyEvidenceReader
        with TemporaryDirectory() as d:
            c=self.setup(d);real=c.reader
            class ShortSignal(ArchivedRebindingDailyEvidenceReader):
                def __call__(self,*args):
                    result=real(*args)
                    result['signal']['valid_until']=(c.clock[0]+timedelta(seconds=1)).isoformat()
                    return result
            c.service.reader=ShortSignal.__new__(ShortSignal)
            with self.assertRaisesRegex(ValueError,'DAILY_SIGNAL_EXPIRED_BEFORE_RECAPTURE'):self.preview(c)
            self.assertEqual(c.round,1);self.assertEqual(c.sleeps,[2])

    def test_prior_minute_snapshot_only_earns_retry_not_price(self):
        with TemporaryDirectory() as d:
            c=self.setup(d,'prior_minute_snapshot');result=self.preview(c)
            self.assertEqual(c.sleeps,[2]);self.assertEqual(c.round,3)
            self.assertEqual(result['buy_data_failure'],'RAW_NOT_MINUTE_ALIGNED')
            self.assertTrue(all(o['side']=='SELL' for o in result['new_orders']))
            old=result['minute_recapture']['eligibility']['recent_nulls'][0]['retry_only_prior_minute_snapshot']
            self.assertEqual(old['role'],'RECAPTURE_ELIGIBILITY_ONLY_NOT_BAR_OR_ACCEPTED_PRICE')

    def test_snapshot_age_and_fields_bounded(self):
        from datetime import datetime,timezone
        with TemporaryDirectory() as d:
            c=self.setup(d,'prior_minute_snapshot');c.round=1
            base=json.loads(c.raw('BBB'))
            html=('All times are Eastern Time<h3>Non-Cboe Listed Halts</h3><table><tr>'+''.join('<th>'+h+'</th>' for h in HEADER)+'</tr></table>').encode()
            for mode in ('old','nonflat','volume','metamismatch','capture_late'):
                with self.subTest(mode=mode):
                    doc=deepcopy(base);r=doc['chart']['result'][0];q=r['indicators']['quote'][0]
                    if mode=='old':r['timestamp'][-1]-=3;r['meta']['regularMarketTime']-=3
                    elif mode=='nonflat':q['high'][-1]+=1
                    elif mode=='volume':q['volume'][-1]=1
                    elif mode=='metamismatch':r['meta']['regularMarketTime']-=1
                    raw=canonical(doc);period=r['meta']['currentTradingPeriod']['regular'];at=c.clock[0]+timedelta(seconds=2 if mode=='capture_late' else 0)
                    parameters=dict(expected_sha256=sha256(raw).hexdigest(),security_id='B',ticker='BBB',session='2026-11-02',
                        session_open=datetime.fromtimestamp(period['start'],timezone.utc).isoformat(),session_close=datetime.fromtimestamp(period['end'],timezone.utc).isoformat(),
                        captured_at=at.isoformat(),checked_at=at.isoformat(),now=at.isoformat(),maximum_age_seconds=120,halt_raw=html,
                        halt_receipt=dict(url=SOURCE_URL,http_status=200,bytes=len(html),raw_sha256=sha256(html).hexdigest(),started_at=c.clock[0].isoformat(),received_at=c.clock[0].isoformat()))
                    with self.assertRaises(ValueError):classify_recent_null(raw=raw,parameters=parameters)

if __name__=='__main__':unittest.main()

