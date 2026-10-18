import json
import unittest
from hashlib import sha256
from backtest.current_quantity_v2_simulated_settlement import _references
from backtest.current_quantity_v2_monthly_simulation import digest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse, parse_qs

from test_current_quantity_v2_simulated_settlement import fixture
from backtest.current_quantity_v2_simulation_store import SimulationStore
from backtest.current_quantity_v2_daily_settlement_simulation import prepare_daily_settlement, apply_daily_settlement


def setup(folder, missing=False, fees='0'):
    simulation, _, _ = fixture()
    store = SimulationStore(Path(folder)/'simulation.db')
    current = store.create(simulation); calls=[]
    def fetch(url):
        calls.append(url); ticker=urlparse(url).path.rsplit('/',1)[1]
        query=parse_qs(urlparse(url).query); start=int(query['period1'][0]); end=int(query['period2'][0])
        times=list(range(start,end,60))
        if missing: times=[]
        price=51 if ticker=='XXX' else 0.9
        chart=dict(meta=dict(symbol=ticker,currency='USD',instrumentType='EQUITY',dataGranularity='1m',
            exchangeTimezoneName='America/New_York'),timestamp=times,events={},
            indicators=dict(quote=[dict(**{k:[price]*len(times) for k in ('open','high','low','close')},volume=[1]*len(times))]))
        return json.dumps(dict(chart=dict(error=None,result=[chart]))).encode()
    args=dict(store=store,simulation_id=simulation['simulation_id'],expected_revision=current['revision'],
        session='2026-10-15',fees={oid:fees for oid in simulation['chain']['ledger']['orders']},
        calendar_source_reference='synthetic-reviewed-calendar',directory=Path(folder)/'capture',fetch=fetch,
        clock=lambda:datetime.fromisoformat('2026-10-16T09:00:00-04:00'))
    return store,current,args,calls


def reviews(prepared, simulation):
    root=Path(prepared['directory']); pins={}; paths={}
    for sid, ref in _references(simulation['chain']).items():
        receipt=json.loads((root/digest(sid)/'receipt.json').read_bytes())
        name='review-'+sid+'.json'; source='declaration-'+sid+'.txt'
        (root/source).write_text('Synthetic test review only')
        review=dict(security_id=sid,ticker=ref['ticker'],price_basis=ref['price_basis'],
            reference_sha256=digest(ref),reference_source_hashes=ref['source_hashes'],
            capture_raw_sha256=receipt['raw_sha256'],status='NO_UNPROCESSED_ACTIONS',
            covered_from=ref['captured_at'],covered_through=receipt['captured_at'],
            reviewed_at=receipt['captured_at'],source_references=[source])
        (root/name).write_text(json.dumps(review))
        paths[sid]=name
        for path in (name,source):pins[path]=sha256((root/path).read_bytes()).hexdigest()
    return dict(unit_reviews=paths,source_hashes=pins,evaluated_at='2026-10-16T09:00:01-04:00')


class DailySettlementTests(unittest.TestCase):
    def test_review_required_and_bound_to_reference_capture_and_actual_receipt(self):
        for mode in ('missing','close_only','capture_hash','reference_hash','pin'):
            with self.subTest(mode=mode),TemporaryDirectory() as folder:
                store,current,args,calls=setup(folder)
                prepared=prepare_daily_settlement(**args)
                review_args=reviews(prepared,current['simulation'])
                sid=next(iter(review_args['unit_reviews']))
                path=Path(prepared['directory'])/review_args['unit_reviews'][sid]
                review=json.loads(path.read_bytes())
                if mode=='missing':review_args['unit_reviews']={}
                else:
                    if mode=='close_only':review['covered_through']='2026-10-15T16:00:00-04:00'
                    if mode=='capture_hash':review['capture_raw_sha256']='0'*64
                    if mode=='reference_hash':review['reference_sha256']='0'*64
                    if mode=='pin':review['status']='UNKNOWN'
                    path.write_text(json.dumps(review))
                    if mode!='pin':review_args['source_hashes'][path.name]=sha256(path.read_bytes()).hexdigest()
                with self.assertRaises(ValueError):
                    apply_daily_settlement(store=store,prepared=prepared,**review_args)
                self.assertEqual(store.read('isolated-test'),current)

    def test_real_capture_reopen_apply_and_completed_retry(self):
        with TemporaryDirectory() as folder:
            store,current,args,calls=setup(folder)
            prepared=prepare_daily_settlement(**args)
            review_args=reviews(prepared,current['simulation'])
            self.assertEqual(len(calls),2)
            self.assertEqual(prepare_daily_settlement(**args),prepared)
            self.assertEqual(len(calls),2)
            fresh=SimulationStore(store.path)
            result=apply_daily_settlement(store=fresh,prepared=prepared,**review_args)
            orders=result['simulation']['chain']['ledger']['orders']
            self.assertTrue(all(o['closed']=='FILLED' for o in orders.values()))
            again=apply_daily_settlement(store=SimulationStore(store.path),prepared=prepared,**review_args)
            self.assertTrue(again['replayed']);self.assertEqual(again['revision'],result['revision'])
            self.assertEqual(len(calls),2)
            with self.assertRaisesRegex(ValueError,'STALE_SIMULATION_REVISION'):
                prepare_daily_settlement(**args)

    def test_unknown_keeps_orders_and_fees_cannot_use_same_time_sale(self):
        for missing,fee in ((True,'0'),(False,'1')):
            with self.subTest(missing=missing),TemporaryDirectory() as folder:
                store,current,args,calls=setup(folder,missing=missing,fees=fee)
                prepared=prepare_daily_settlement(**args)
                review_args=reviews(prepared,current['simulation'])
                result=apply_daily_settlement(store=store,prepared=prepared,**review_args)['simulation']
                statuses=result['batches'][-1]['results']
                self.assertTrue(any(row['status']=='UNKNOWN' for row in statuses.values()))
                self.assertTrue(any(not o['closed'] for o in result['chain']['ledger']['orders'].values()))
                if missing:self.assertEqual(result['chain'],current['simulation']['chain'])

    def test_missing_fees_partial_capture_and_tampering_block_without_retry(self):
        with TemporaryDirectory() as folder:
            store,current,args,calls=setup(folder)
            with self.assertRaisesRegex(ValueError,'EXACT_EXPLICIT_ORDER_FEES_REQUIRED'):
                prepare_daily_settlement(**dict(args,fees={}))
            self.assertEqual(calls,[])
            def fail(url):calls.append(url);raise RuntimeError('fixture failure')
            with self.assertRaises(RuntimeError):prepare_daily_settlement(**dict(args,fetch=fail))
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_NO_RETRY'):prepare_daily_settlement(**args)
            self.assertEqual(len(calls),1);self.assertEqual(store.read('isolated-test'),current)
        with TemporaryDirectory() as folder:
            store,current,args,calls=setup(folder)
            prepared=prepare_daily_settlement(**args)
            review_args=reviews(prepared,current['simulation'])
            path=next(Path(args['directory']).glob('*/response.bin'));path.write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'CAPTURE_BYTES_CHANGED'):
                apply_daily_settlement(store=store,prepared=prepared,**review_args)
            self.assertEqual(store.read('isolated-test'),current)
            with self.assertRaisesRegex(ValueError,'INCOMPLETE_NO_AUTOMATIC_RETRY'):
                apply_daily_settlement(store=store,prepared=prepared,**review_args)


if __name__=='__main__':unittest.main()
