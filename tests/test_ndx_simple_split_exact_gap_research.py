from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_simple_split_quote_guard_v3_research import fixture, write_manifest
from backtest import ndx_simple_split_exact_gap_research as guard


class ExactGapGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sources = {}
        exceptions = {}
        for i in range(26):
            path = self.root / (str(i)+'.csv')
            path.write_bytes(b'current')
            old = hashlib.sha256(b'old').hexdigest()
            self.sources[str(path)] = old
            exceptions[str(path)] = dict(expected_historical_sha256=old, observed_current_sha256=guard.drift.file_sha(path))
        self.official = self.root/'official.txt'
        self.official.write_bytes(b'official')
        self.sources[str(self.official)] = guard.drift.file_sha(self.official)
        contract = dict(authority_source_hashes={}, exceptions=exceptions)
        self.patch = patch.object(guard.drift, 'load_contract', return_value=contract)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        sources = self.sources
        def registry_stub():
            nominal.verify(sources)
            return dict(event_count=25, guard_eligible_event_count=23, source_hashes=dict(sources),
                        events=[dict(ticker='AMZN', first_adjusted_trading_date='2022-06-06',
                                     new_shares=20, old_shares=1, simple_split_guard_eligible=True,
                                     specific_simple_share_split_event_supported=True)])
        self.loader = patch.object(guard.original, 'load_registry', registry_stub)
        self.loader.start()
        self.addCleanup(self.loader.stop)

    def test_private_registry_keeps_true_historical_hashes_and_globals(self):
        verify = guard.nominal.verify
        document = guard.load_registry()
        self.assertIs(guard.nominal.verify, verify)
        self.assertNotIn('source_hashes', document)
        self.assertFalse(document['old_strict_registry_passed'])
        self.assertEqual(len(document['historical_price_cache_gap_observations']),26)
        for path in guard.drift.load_contract()['exceptions']:
            self.assertNotIn(path, document['verified_source_hashes'])
            self.assertEqual(document['historical_expected_source_hashes'][path],self.sources[path])

    def test_official_source_drift_and_changed_again_csv_fail(self):
        self.official.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Non-exempt'):
            guard.load_registry()
        self.official.write_bytes(b'official')
        Path(next(iter(self.sources))).write_bytes(b'changed twice')
        with self.assertRaisesRegex(ValueError,'changed again'):
            guard.load_registry()

    def test_guard_original_nameless_capture_and_no_global_mutation(self):
        params,_=fixture(self.root)
        before=guard.nominal.verify
        result=guard.reconstruct_raw_addressed_nominal_quote(**params)
        self.assertIs(guard.nominal.verify,before)
        self.assertEqual([row['split_factor'] for row in result['reconstruction']['rows']],[20.,1.])
        self.assertNotIn('source_hashes',result)
        self.assertFalse(result['quote_basis_independently_authenticated'])
        self.assertEqual(len(result['historical_price_cache_gap_observations']),26)

    def test_complex_identity_duplicate_raw_and_receipt_reject(self):
        params,row=fixture(self.root)
        for ticker in guard.original.BLOCKED | guard.original.TRANSITIONS:
            with self.assertRaises(ValueError):
                guard.reconstruct_raw_addressed_nominal_quote(**dict(params,ticker=ticker))
        write_manifest(params,[row,deepcopy(row)])
        with self.assertRaisesRegex(ValueError,'Unique exact raw'):
            guard.reconstruct_raw_addressed_nominal_quote(**params)
        row['received_at_utc']='2022-06-06T16:00:00+00:00'
        write_manifest(params,[row])
        with self.assertRaisesRegex(ValueError,'Reception-day'):
            guard.reconstruct_raw_addressed_nominal_quote(**params)

    def test_missing_known_event_or_outside_calendar_null_reject(self):
        for fault in ('event','null'):
            params,row=fixture(self.root)
            data=json.loads(gzip.decompress(Path(row['raw_path']).read_bytes()))
            if fault=='event':data['chart']['result'][0]['events']['splits']={}
            else:
                params['calendar']=['2022-06-03']
                data['chart']['result'][0]['indicators']['quote'][0]['open'][1]=None
            content=json.dumps(data).encode();raw=gzip.compress(content)
            Path(row['raw_path']).write_bytes(raw)
            row.update(raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw),decoded_sha256=hashlib.sha256(content).hexdigest())
            params['raw_sha256']=row['raw_sha256'];write_manifest(params,[row])
            with self.assertRaises(ValueError):guard.reconstruct_raw_addressed_nominal_quote(**params)

    def test_drift_after_engine_rejects_result(self):
        params,_=fixture(self.root)
        engine=guard.nominal.reconstruct_nominal_quote_ticker
        def changed(**kwargs):
            result=engine(**kwargs)
            self.official.write_bytes(b'changed after calculation')
            return result
        with patch.object(guard.nominal,'reconstruct_nominal_quote_ticker',side_effect=changed):
            with self.assertRaisesRegex(ValueError,'Non-exempt'):
                guard.reconstruct_raw_addressed_nominal_quote(**params)


if __name__=='__main__':unittest.main()
