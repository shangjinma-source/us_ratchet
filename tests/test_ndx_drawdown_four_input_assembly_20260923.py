import copy
import gzip
import hashlib
import json
import unittest
from unittest.mock import patch
from scripts import ndx_drawdown_four_input_assembly_20260923 as module


class AssemblyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.documents = {}
        for role, (path, digest) in module.BOUND.items():
            raw = (module.BASE / path).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest: raise ValueError('Fixture SHA differs')
            if role == 'raw': cls.raw = raw
            else: cls.documents[role] = json.loads(raw)

    def test_real_856_cells_and_identity_boundaries(self):
        before = copy.deepcopy(self.documents)
        result = module.assemble(self.documents, self.raw)
        self.assertEqual(before, self.documents)
        self.assertEqual(result['price_projection']['price_cell_count'], 856)
        self.assertEqual(result['calendar'], before['benchmark']['calendar'])
        self.assertTrue(all(result[key] is False for key in module.FALSE))
        self.assertEqual(result['identity_projection']['enph_original_conditional_window']['end'], '2023-05-01')
        self.assertFalse(result['identity_projection']['enph_original_interval_certification_extended'])
        for kind, matrix in result['price_projection']['matrices'].items():
            for day, row in matrix.items():
                self.assertEqual(set(row), set(module.COORDINATES))
                for ticker in ('BKR', 'CDNS', 'FTNT'):
                    self.assertEqual(row[ticker], before['parent']['price_projection']['matrices'][kind][day][ticker])
        for chains in result['selected_risk_chains_by_decision'].values():
            self.assertEqual(sum(v == 'energy_technology' for v in chains.values()), 2)

    def test_gzip_transport_and_decoded_hash_separate(self):
        raw = gzip.compress(self.raw, mtime=0)
        metadata = copy.deepcopy(self.documents['metadata'])
        metadata.update(response_sha256=hashlib.sha256(raw).hexdigest(), response_bytes=len(raw))
        result = module.decode_enph(raw, metadata, self.documents['benchmark']['calendar'])
        self.assertEqual(result['transport_encoding'], 'gzip')
        self.assertNotEqual(result['transport_sha256'], result['decoded_sha256'])
        self.assertEqual(result['decoded_sha256'], hashlib.sha256(self.raw).hexdigest())

    def test_changed_quote_currency_dates_events_fail(self):
        for change in ('null', 'currency', 'date', 'events', 'nan'):
            obj = json.loads(self.raw)
            chart = obj['chart']['result'][0]
            if change == 'currency': chart['meta']['currency'] = 'EUR'
            elif change == 'events': chart['events'] = {'splits': {'1': {}}}
            else:
                from datetime import datetime, timezone
                index = next(i for i,t in enumerate(chart['timestamp']) if datetime.fromtimestamp(t, timezone.utc).date().isoformat() == '2023-03-31')
                if change == 'date': chart['timestamp'][index] += 86400
                else: chart['indicators']['quote'][0]['open'][index] = None if change == 'null' else 'NaN'
            raw = json.dumps(obj).encode()
            metadata = copy.deepcopy(self.documents['metadata'])
            metadata.update(response_sha256=hashlib.sha256(raw).hexdigest(), response_bytes=len(raw))
            with self.subTest(change=change), self.assertRaises(ValueError):
                module.decode_enph(raw, metadata, self.documents['benchmark']['calendar'])

    def test_identity_risk_clock_permission_fail(self):
        for change in ('identity', 'risk', 'clock', 'permission', 'oldwindow'):
            docs = copy.deepcopy(self.documents)
            if change == 'identity': next(r for r in docs['identity']['rows'] if r['ticker']=='ENPH')['cusip'] = 'WRONG'
            elif change == 'risk': docs['lane']['decisions'][0]['lanes']['DRAWDOWN'][0]['selected']['security:0001463101:29355A107']['risk_chain'] = 'independent'
            elif change == 'clock': docs['lane']['decisions'][0]['execution_date'] = '2023-04-04'
            elif change == 'permission': docs['identity']['provider_price_binding_verified'] = True
            else: docs['identity']['conditional_window']['end'] = '2023-09-01'
            with self.subTest(change=change), self.assertRaises(ValueError): module.assemble(docs, self.raw)

    def test_source_lock_precedes_build(self):
        with patch.object(module, 'LOADED', {str(module.SOURCE): '0'*64}):
            with self.assertRaises(ValueError): module.build()

    def test_timezone_loaded_bytes_are_locked_before_decode(self):
        self.assertEqual(module.LOADED[str(module.NY_SOURCE)], hashlib.sha256(module.NY_BYTES).hexdigest())
        changed = dict(module.LOADED, **{str(module.NY_SOURCE): '0'*64})
        with patch.object(module, 'LOADED', changed):
            with self.assertRaises(ValueError):
                module.decode_enph(self.raw, self.documents['metadata'], self.documents['benchmark']['calendar'])


if __name__ == '__main__':
    unittest.main()
