from contextlib import closing
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from decimal import Decimal
from unittest.mock import patch
from data.current_research_intraday_cap_store import PersistentIntradayCapStore
from data.current_research_intraday_execution import IntradayExecutionService
from test_current_research_intraday_execution import NOW,payload,snapshot


def lower_worker(args):
    path,price,event=args
    return PersistentIntradayCapStore(path).lower(research_id='a'*24,security_id='sndk',ticker='SNDK',session='2026-10-15',observed_cap=price,event_id=event)


class CapTests(unittest.TestCase):
    def test_restart_and_concurrent_process_min(self):
        with tempfile.TemporaryDirectory() as root:
            path=str(Path(root)/'cap.db')
            first=lower_worker((path,'1412.12','a'*32))
            self.assertEqual(first['cap'],'1412.12')
            self.assertEqual(lower_worker((path,'1500','b'*32))['cap'],'1412.12')
            with ProcessPoolExecutor(max_workers=2) as workers:
                results=list(workers.map(lower_worker,[(path,str(p),format(i,'032x')) for i,p in enumerate([1400,1450,1390,1420],1)]))
            self.assertTrue(all(Decimal(r['cap'])<=Decimal('1412.12') for r in results))
            self.assertEqual(lower_worker((path,'1500','c'*32))['cap'],'1390')
    def test_service_restart_failure_and_freshness(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'cap.db'
            def service(fetch=payload):
                return IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:fetch(),clock=lambda:NOW,cap_store=PersistentIntradayCapStore(path))
            first=service().preview('a'*24)['stocks'][0]
            def higher():
                p=payload();c=p['chart']['result'][0];c['meta']['regularMarketPrice']+=100
                for key in ('open','high','low','close'):c['indicators']['quote'][0][key][0]+=100
                return p
            second=service(higher).preview('a'*24)['stocks'][0]
            self.assertEqual(second['limit_price'],first['limit_price'])
            self.assertEqual(second['cap_origin_event_id'],first['cap_origin_event_id'])
            def stale():
                p=payload();p['chart']['result'][0]['meta']['regularMarketTime']-=1000;return p
            self.assertEqual(service(stale).preview('a'*24)['stocks'][0]['status'],'UNAVAILABLE')
            with patch.object(PersistentIntradayCapStore,'lower',side_effect=OSError('commit failed')):
                row=service(higher).preview('a'*24)['stocks'][0]
                self.assertEqual(row['status'],'UNAVAILABLE');self.assertIsNone(row['limit_price']);self.assertNotIn('fresh_cash_reference',row)
            path.write_bytes(b'corrupt database')
            row=service(higher).preview('a'*24)['stocks'][0]
            self.assertEqual(row['status'],'UNAVAILABLE');self.assertIsNone(row['limit_price'])
    def test_slow_commit_rechecks_deadline_without_raising_cap(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'cap.db';store=PersistentIntradayCapStore(path);clock=[NOW]
            class SlowStore:
                def lower(self,**kwargs):
                    result=store.lower(**kwargs);clock[0]+=timedelta(seconds=120);return result
            service=IntradayExecutionService(snapshot_reader=snapshot,fetch=lambda _:payload(),clock=lambda:clock[0],cap_store=SlowStore())
            row=service.preview('a'*24)['stocks'][0]
            self.assertEqual(row['status'],'UNAVAILABLE');self.assertIsNone(row['limit_price'])
            self.assertNotIn('fresh_cash_reference',row)
            self.assertEqual(lower_worker((str(path),'1500','e'*32))['cap'],'1412.12')

    def test_key_separation_and_invalid_rows(self):
        import sqlite3
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'cap.db';lower_worker((str(path),'100','a'*32))
            store=PersistentIntradayCapStore(path)
            row=store.lower(research_id='b'*24,security_id='sndk',ticker='SNDK',session='2026-10-15',observed_cap='200',event_id='b'*32)
            self.assertEqual(row['cap'],'200')
            with closing(sqlite3.connect(path)) as c:
                c.execute("UPDATE session_caps SET origin_event='broken'");c.commit()
            with self.assertRaisesRegex(ValueError,'CORRUPT_CAP_ROW'):lower_worker((str(path),'300','c'*32))

if __name__=='__main__':unittest.main()
