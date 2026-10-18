import json
import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path
from data.current_research_intraday_execution import IntradayExecutionService
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_touch_review import review_intraday_touches,_complete_bars
from test_current_research_intraday_execution import NOW,payload,snapshot

START=NOW.replace(second=0)
def later(now,lows):
    p=payload();r=p['chart']['result'][0]
    r['meta']['regularMarketTime']=int(now.timestamp())-1
    r['timestamp']=[int(START.timestamp())+60*i for i in range(len(lows))]
    r['indicators']['quote']=[dict(open=[1413]*len(lows),high=[1414]*len(lows),low=lows,close=[1413]*len(lows),volume=[10]*len(lows))]
    return p

class TouchTests(unittest.TestCase):
    def setup_service(self,root):
        clock=[START];p=payload();p['chart']['result'][0]['meta']['regularMarketTime']=int(START.timestamp())
        current=[p];service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:json.dumps(current[0]).encode(),clock=lambda:clock[0],journal=IntradayObservationJournal(root))
        first=service.preview('a'*24)
        return service,clock,current,first
    def test_complete_window_no_touch_or_touch(self):
        for lows,expected in [([1413,1413],'NO_TOUCH_IN_COMPLETE_OBSERVED_WINDOW'),([1413,1410],'OBSERVED_TOUCH')]:
            with tempfile.TemporaryDirectory() as root:
                service,clock,current,first=self.setup_service(root)
                clock[0]=START+timedelta(minutes=2,seconds=5);current[0]=later(clock[0],lows);service.preview('a'*24)
                report=review_intraday_touches(root,'2026-10-15');row=next(r for r in report['observations'] if r['event_id']==first['observation_record']['event_id'])
                self.assertEqual(row['status'],expected,row);self.assertTrue(row['coverage_complete'])
                self.assertEqual(len(row['expected_complete_minute_starts']),2)
    def test_missing_minute_unknown_unless_observed_touch(self):
        for low,expected in [(1413,'UNKNOWN'),(1410,'OBSERVED_TOUCH')]:
            with tempfile.TemporaryDirectory() as root:
                service,clock,current,first=self.setup_service(root)
                clock[0]=START+timedelta(minutes=2,seconds=5);current[0]=later(clock[0],[low]);service.preview('a'*24)
                row=review_intraday_touches(root,'2026-10-15')['observations'][0]
                self.assertEqual(row['status'],expected,row);self.assertFalse(row['coverage_complete'])
    def test_conflicting_future_sources_never_pick_lower(self):
        with tempfile.TemporaryDirectory() as root:
            service,clock,current,first=self.setup_service(root)
            clock[0]=START+timedelta(minutes=2,seconds=5);current[0]=later(clock[0],[1413,1410]);service.preview('a'*24)
            clock[0]+=timedelta(seconds=5);current[0]=later(clock[0],[1413,1413]);service.preview('a'*24)
            row=review_intraday_touches(root,'2026-10-15')['observations'][0]
            self.assertEqual(row['status'],'UNKNOWN');self.assertTrue(row['conflicting_minutes'])
    def test_unavailable_response_and_restart_cut_window(self):
        for restart in (False,True):
            with tempfile.TemporaryDirectory() as root:
                service,clock,current,first=self.setup_service(root)
                clock[0]=START+timedelta(seconds=30)
                if restart:
                    service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:(_ for _ in ()).throw(OSError('offline')),clock=lambda:clock[0],journal=IntradayObservationJournal(root))
                else:service.fetch=lambda _:(_ for _ in ()).throw(OSError('offline'))
                service.preview('a'*24)
                rows=review_intraday_touches(root,'2026-10-15')['observations'];row=next(r for r in rows if r['event_id']==first['observation_record']['event_id'])
                self.assertEqual(row['status'],'UNKNOWN');self.assertIn('NO_FULL_MINUTE',str(row['reasons']))
    def test_restart_other_research_and_corrupt_event_are_safe(self):
        with tempfile.TemporaryDirectory() as root:
            service,clock,current,first=self.setup_service(root)
            clock[0]=START+timedelta(seconds=30)
            def alternate(research_id):
                s=snapshot(research_id);s['research_id']=research_id;return s
            other=IntradayExecutionService(snapshot_reader=alternate,fetch=lambda _:(_ for _ in ()).throw(OSError('offline')),clock=lambda:clock[0],journal=IntradayObservationJournal(root))
            second=other.preview('b'*24)
            row=review_intraday_touches(root,'2026-10-15')['observations'][0]
            self.assertEqual(row['status'],'UNKNOWN');self.assertIn('NO_FULL_MINUTE',str(row['reasons']))
            path=Path(root)/second['observation_record']['event_path'];event=json.loads(path.read_bytes())
            event['observation_sequence']='invalid';path.write_text(json.dumps(event),encoding='utf-8')
            report=review_intraday_touches(root,'2026-10-15')
            self.assertTrue(report['source_diagnostics']);self.assertEqual(report['saved_event_count'],2)
            self.assertEqual(report['observations'][0]['status'],'UNKNOWN')

    def test_invalid_later_source_cannot_be_ignored_beside_touch(self):
        with tempfile.TemporaryDirectory() as root:
            service,clock,current,first=self.setup_service(root)
            clock[0]=START+timedelta(minutes=2,seconds=5);current[0]=later(clock[0],[1410,1413]);service.preview('a'*24)
            clock[0]+=timedelta(seconds=5);current[0]=later(clock[0],[1410,1413]);current[0]['chart']['result'][0]['meta']['currency']='HKD'
            service.preview('a'*24)
            report=review_intraday_touches(root,'2026-10-15')
            self.assertEqual(report['observations'][0]['status'],'UNKNOWN')
            self.assertIn('INVALID_LATER_SOURCE',str(report['observations'][0]['reasons']))
            self.assertEqual(report['saved_response_counts']['UNAVAILABLE'],1)

    def test_capture_time_partial_bar_and_source_identity(self):
        captured=START+timedelta(minutes=1,seconds=30);p=later(captured,[1413,99]);raw=json.dumps(p).encode()
        bars=_complete_bars(raw,ticker='SNDK',session='2026-10-15',captured=captured)
        self.assertEqual(len(bars),1);self.assertNotIn(int(START.timestamp())+60,bars)
        with self.assertRaisesRegex(ValueError,'IDENTITY'):_complete_bars(raw,ticker='OTHER',session='2026-10-15',captured=captured)

if __name__=='__main__':unittest.main()
