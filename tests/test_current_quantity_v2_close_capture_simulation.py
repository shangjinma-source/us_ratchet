import json
import unittest
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse,parse_qs

from backtest.current_quantity_v2_close_capture_simulation import prepare_close_captures
from backtest.current_quantity_v2_simulation_store import SimulationStore
from backtest.current_quantity_v2_simulated_settlement import settle
from test_current_quantity_v2_simulated_settlement import valuation_fixture,evidence_for


def setup(folder,missing=False,flat=False):
    root=Path(folder);state,_,args,_=valuation_fixture()
    evidence,at=evidence_for(state['chain'],args['execution_references'],fill=False,full_day=True)
    for oid,item in evidence.items():
        side=state['chain']['ledger']['orders'][oid]['side']
        if (flat and side=='SELL') or (not flat and side=='BUY'):
            price='51' if side=='SELL' else '.9'
            for bar in item['minutes']:bar.update(open=price,high=price,low=price,close=price)
    state=settle(simulation=state,evidence=evidence,observed_through=at,evaluated_at=at)
    store=SimulationStore(root/'store.db');current=store.create(state)
    schedule=dict(schema='SCHEDULED_REGULAR_SESSIONS_V1',sessions=[dict(date='2026-10-15',
        open_at='2026-10-15T09:30:00-04:00',close_at='2026-10-15T16:00:00-04:00')])
    raw=json.dumps(schedule).encode();(root/'schedule.json').write_bytes(raw);calls=[]
    def fetch(url):
        calls.append(url);query=parse_qs(urlparse(url).query);ticker=urlparse(url).path.rsplit('/',1)[1]
        times=list(range(int(query['period1'][0]),int(query['period2'][0]),60))
        if missing:times.pop()
        row=dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',dataGranularity='1m',exchangeTimezoneName='America/New_York'),
            timestamp=times,events={},indicators=dict(quote=[dict(**{k:[1]*len(times) for k in ('open','high','low','close')},volume=[1]*len(times))]))
        return json.dumps(dict(chart=dict(error=None,result=[row]))).encode()
    return dict(store=store,simulation_id=state['simulation_id'],expected_revision=current['revision'],
        session='2026-10-15',root=root,schedule_path='schedule.json',schedule_sha256=sha256(raw).hexdigest(),
        directory=root/'close',fetch=fetch,clock=lambda:datetime.fromisoformat('2026-10-16T09:00:00-04:00')),calls


class CloseCaptureTests(unittest.TestCase):
    def test_all_holdings_including_non_target_closed_orders_and_restart(self):
        with TemporaryDirectory() as folder:
            args,calls=setup(folder);result=prepare_close_captures(**args)
            self.assertEqual(set(result['captures']),{'A','X'})
            self.assertTrue(all(o['closed'] for o in args['store'].read(args['simulation_id'])['simulation']['chain']['ledger']['orders'].values()))
            self.assertEqual(len(calls),2)
            again=prepare_close_captures(**dict(args,store=SimulationStore(args['store'].path)))
            self.assertEqual(again,result);self.assertEqual(len(calls),2)
            self.assertFalse(result['official_close']);self.assertFalse(result['initial_valuation_supported'])

    def test_full_and_partial_reuse_validates_and_only_fetches_missing(self):
        for subset in (False,True):
            with self.subTest(subset=subset),TemporaryDirectory() as folder:
                args,calls=setup(folder);saved=prepare_close_captures(**args)
                capture={sid:{k:'close/'+p for k,p in paths.items()} for sid,paths in saved['captures'].items() if not subset or sid=='A'}
                pins={'close/'+p:h for p,h in saved['source_hashes'].items()}
                before=len(calls)
                reused=prepare_close_captures(**dict(args,directory=Path(folder)/'reuse',existing_captures=capture,existing_source_hashes=pins))
                self.assertEqual(set(reused['captures']),{'A','X'});self.assertEqual(len(calls)-before,1 if subset else 0)

    def test_unknown_final_minute_empty_holdings_and_fail_closed(self):
        with TemporaryDirectory() as folder:
            args,calls=setup(folder,missing=True);result=prepare_close_captures(**args)
            self.assertEqual(set(result['statuses'].values()),{'UNKNOWN'})
        with TemporaryDirectory() as folder:
            args,calls=setup(folder,flat=True);result=prepare_close_captures(**args)
            self.assertEqual(result['captures'],{});self.assertEqual(calls,[])
        with TemporaryDirectory() as folder:
            args,calls=setup(folder)
            with self.assertRaisesRegex(ValueError,'STALE_SIMULATION_REVISION'):
                prepare_close_captures(**dict(args,expected_revision='bad'))
            with self.assertRaisesRegex(ValueError,'CLOSE_CAPTURE_TOO_EARLY'):
                prepare_close_captures(**dict(args,clock=lambda:datetime.fromisoformat('2026-10-15T15:59:00-04:00')))
            self.assertEqual(calls,[])
            result=prepare_close_captures(**args)
            raw=Path(result['root'])/result['captures']['A']['raw'];raw.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):prepare_close_captures(**args)
            self.assertEqual(len(calls),2)
        with TemporaryDirectory() as folder:
            args,calls=setup(folder)
            def fail(url):calls.append(url);raise OSError('synthetic failure')
            with self.assertRaises(OSError):prepare_close_captures(**dict(args,fetch=fail))
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_NO_RETRY'):prepare_close_captures(**args)
            self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
