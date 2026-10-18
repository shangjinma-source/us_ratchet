"""Deterministic concurrency tests: injected fetch only, no network."""
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from threading import Event
from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_journal import IntradayObservationJournal
from test_current_research_intraday_execution import NOW,payload,snapshot


def two_snapshots(research_id):
    result=snapshot(research_id);result['research_id']=research_id
    if research_id=='b'*24:
        result['selected_security']=dict(security_id='other',ticker='OTHER')
        result['selected_ranking_security_id']='other'
        result['stocks'][0].update(security_id='other',ticker='OTHER')
    return result


class InflightTests(unittest.TestCase):
    def test_busy_no_second_fetch_other_ticker_independent_and_journal_order(self):
        entered=Event();release=Event();calls=[]
        def fetch(ticker):
            calls.append(ticker)
            if ticker=='SNDK':
                entered.set()
                if not release.wait(3):raise RuntimeError('test release timeout')
            result=payload();result['chart']['result'][0]['meta']['symbol']=ticker
            return result
        with tempfile.TemporaryDirectory() as root:
            journal=IntradayObservationJournal(root)
            service=IntradayExecutionService(snapshot_reader=two_snapshots,fetch=fetch,clock=lambda:NOW,journal=journal)
            with ThreadPoolExecutor(max_workers=3) as pool:
                first=pool.submit(service.preview,'a'*24)
                try:
                    self.assertTrue(entered.wait(1))
                    busy=pool.submit(service.preview,'a'*24).result(timeout=1)
                    other=pool.submit(service.preview,'b'*24).result(timeout=1)
                    self.assertEqual(busy['stocks'][0]['reason'],'FETCH_IN_PROGRESS')
                    self.assertIsNone(busy['stocks'][0]['limit_price'])
                    self.assertNotIn('fresh_cash_reference',busy['stocks'][0])
                    self.assertEqual(other['status'],'AVAILABLE')
                    self.assertEqual(calls,['SNDK','OTHER'])
                    self.assertEqual([busy['observation_sequence'],other['observation_sequence']],[1,2])
                    receipt=busy['observation_record']
                    saved=journal.read_event(receipt['event_path'],expected_sha256=receipt['event_sha256'])
                    self.assertEqual(saved['captures'],[])
                finally:release.set()
                result=first.result(timeout=1)
            self.assertEqual(result['status'],'AVAILABLE');self.assertEqual(result['observation_sequence'],3)
            follow=service.preview('a'*24)
            self.assertEqual(follow['stocks'][0]['prior_cap_event_id'],result['observation_record']['event_id'])

    def test_network_and_bad_quote_release_gate(self):
        service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:(_ for _ in ()).throw(OSError('offline')),clock=lambda:NOW)
        self.assertEqual(service.preview('a'*24)['stocks'][0]['reason'],'offline')
        bad=payload();bad['chart']['result'][0]['meta']['currency']='HKD';service.fetch=lambda _:bad
        self.assertEqual(service.preview('a'*24)['stocks'][0]['reason'],'QUOTE_IDENTITY_CURRENCY_MISMATCH')
        service.fetch=lambda _:payload()
        self.assertEqual(service.preview('a'*24)['status'],'AVAILABLE')

    def test_capture_precedes_state_lock_wait_and_partial_never_matures(self):
        entered=Event();release=Event();captured=Event();time=[NOW];fetched=[False]
        p=payload();q=p['chart']['result'][0]['indicators']['quote'][0]
        for key in ('open','high','low','close'):q[key][1]=99
        q['volume'][1]=10
        def fetch(_):
            entered.set()
            if not release.wait(3):raise RuntimeError('test release timeout')
            fetched[0]=True
            return deepcopy(p)
        def clock():
            current=time[0]
            if fetched[0]:captured.set()
            return current
        service=IntradayExecutionService(snapshot_reader=snapshot,fetch=fetch,clock=clock)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(service.preview,'a'*24)
            self.assertTrue(entered.wait(1))
            with service.lock:
                release.set();self.assertTrue(captured.wait(1));time[0]=NOW+timedelta(seconds=60)
            result=future.result(timeout=1)
        row=result['stocks'][0]
        self.assertEqual(row['status'],'AVAILABLE')
        self.assertEqual(row['quote_response_age_seconds'],60)
        self.assertEqual(row['limit_price'],'1412.12')

if __name__=='__main__':unittest.main()
