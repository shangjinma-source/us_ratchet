from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_price_identity_bridge_research as bridge


class PriceIdentityBridgeTests(unittest.TestCase):
    def fixture(self, directory, fault=None):
        root = Path(directory)
        identity = dict(security_id='SECURITY_A', issuer_id='ISSUER', cik='0000000001', cusip='000000001')
        days = ['2024-01-05', '2024-01-08', '2024-01-09']

        def save(name, value):
            path = root / name; raw = json.dumps(value, sort_keys=True).encode()
            path.write_bytes(raw)
            return dict(path=str(path), sha256=hashlib.sha256(raw).hexdigest())

        intervals = []
        for ticker, subset, price in [('A', days[:1], 10.), ('X', days[1:], 100.)]:
            evidence = dict(identity, schema='ndx_price_identity_evidence_v1', observed_ticker=ticker,
                provider_instrument_id='PROVIDER_SEC1', first_session=subset[0], last_session=subset[-1],
                evidence_available_session='2024-01-04')
            prices = dict(identity, schema='ndx_identity_price_artifact_v1', observed_ticker=ticker,
                provider_instrument_id='PROVIDER_SEC1', open_column='Open', close_column='Close',
                currency='USD', price_basis='UNADJUSTED',
                rows=[dict(session=day, Open=price, Close=price + 1.) for day in subset])
            if ticker == 'X':
                if fault == 'wrong_price_identity': prices['cusip'] = '000000002'
                if fault == 'wrong_evidence_identity': evidence['cusip'] = '000000002'
                if fault == 'future_ticker': prices['rows'].insert(0, dict(session=days[0], Open=100., Close=101.))
                if fault == 'missing_price': prices['rows'].pop()
                if fault == 'bool': prices['rows'][0]['Open'] = True
                if fault == 'duplicate_price': prices['rows'].append(deepcopy(prices['rows'][-1]))
            intervals.append(dict(first_session=subset[0], last_session=subset[-1], observed_ticker=ticker,
                provider_instrument_id='PROVIDER_SEC1', open_column='Open', close_column='Close',
                price_artifact=save(ticker+'_prices.json', prices),
                identity_evidence=save(ticker+'_identity.json', evidence)))
        rename = dict(identity, schema='ndx_same_security_rename_evidence_v1', event_id='A_TO_X',
            event_type='SAME_SECURITY_SYMBOL_CHANGE', effective_session=days[1], from_ticker='A', to_ticker='X',
            evidence_available_session='2024-01-04')
        if fault == 'wrong_rename_identity': rename['cusip'] = '000000002'
        events = [dict(event_id='A_TO_X', effective_session=days[1], from_ticker='A', to_ticker='X',
                       evidence=save('rename.json', rename))]
        if fault == 'missing_event': events = []
        if fault == 'event_date': events[0]['effective_session'] = days[2]
        if fault == 'overlap': intervals[1]['first_session'] = days[0]
        if fault == 'gap': intervals[1]['first_session'] = days[2]
        securities = {'SECURITY_A': dict(issuer_id='ISSUER', cik='0000000001', cusip='000000001',
                                        intervals=intervals, rename_events=events)}
        return dict(calendar=days, securities=securities)

    def test_verified_content_bridge_real_gap_not_adjusted_and_daily_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.fixture(directory)
            result = bridge.build_price_identity_bridge(**arguments)
            column = result['internal_columns_by_security']['SECURITY_A']
            self.assertEqual(result['opens'][column].tolist(), [10., 100., 100.])
            self.assertEqual(result['closes'][column].tolist(), [11., 101., 101.])
            self.assertEqual([row['SECURITY_A'] for row in result['tickers_by_session'].values()], ['A', 'X', 'X'])
            self.assertEqual(len(result['price_audit']), 3)
            self.assertEqual(len(result['rename_event_audit']), 1)
            self.assertEqual(column, column.upper())
            self.assertFalse(result['source_authenticity_verified'])
            self.assertFalse(result['point_in_time_verified'])
            self.assertFalse(result['execution_performed'])

    def test_missing_conflicting_identity_and_unproved_rename_rejected(self):
        for fault in ('wrong_price_identity', 'wrong_evidence_identity', 'wrong_rename_identity',
                      'future_ticker', 'missing_event', 'event_date', 'overlap', 'gap',
                      'missing_price', 'bool', 'duplicate_price'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    bridge.build_price_identity_bridge(**self.fixture(directory, fault))

    def test_hash_drift_and_noncanonical_calendar_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.fixture(directory)
            price = arguments['securities']['SECURITY_A']['intervals'][0]['price_artifact']
            Path(price['path']).write_text('{}', encoding='utf-8')
            with self.assertRaises(ValueError): bridge.build_price_identity_bridge(**arguments)
            arguments = self.fixture(directory)
            for days in (['2024-01-05T00:00:00'], ['2024-01-05', '2024-01-05'], ['2024-01-08','2024-01-05']):
                with self.assertRaises(ValueError): bridge.build_price_identity_bridge(**dict(arguments, calendar=days))
            with patch.object(bridge, '_LOADED_SHA', '0'*64):
                with self.assertRaises(ValueError): bridge.build_price_identity_bridge(**arguments)

    def test_late_evidence_rejected_and_missing_file_not_inferred(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.fixture(directory)
            reference = arguments['securities']['SECURITY_A']['rename_events'][0]['evidence']
            path = Path(reference['path']); content = json.loads(path.read_text())
            content['evidence_available_session'] = '2026-09-11'
            raw = json.dumps(content).encode(); path.write_bytes(raw)
            reference['sha256'] = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, 'unavailable'):
                bridge.build_price_identity_bridge(**arguments)
            path.unlink()
            with self.assertRaises(FileNotFoundError): bridge.build_price_identity_bridge(**arguments)

    def test_duplicate_security_pair_and_issuer_mapping_rejected(self):
        for fault in ('duplicate_pair', 'issuer'):
            with tempfile.TemporaryDirectory() as directory:
                arguments = self.fixture(directory)
                other = deepcopy(arguments['securities']['SECURITY_A'])
                if fault == 'issuer': other.update(issuer_id='OTHER_ISSUER', cusip='000000002')
                arguments['securities']['SECURITY_B'] = other
                with self.assertRaisesRegex(ValueError, 'identity mapping'):
                    bridge.build_price_identity_bridge(**arguments)

    def test_shareclasses_allowed_and_internal_coordinate_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            arguments = self.fixture(directory)
            alone = bridge.build_price_identity_bridge(**arguments)
            sibling = Path(directory) / 'sibling'; sibling.mkdir()
            other = self.fixture(sibling)
            substitutions = {'SECURITY_A': 'AAA_SECOND_CLASS', '000000001': '000000002',
                             'A': 'B', 'X': 'Y', 'PROVIDER_SEC1': 'PROVIDER_SEC2', 'A_TO_X': 'B_TO_Y'}

            def transform(value):
                if isinstance(value, dict): return {key: transform(item) for key, item in value.items()}
                if isinstance(value, list): return [transform(item) for item in value]
                return substitutions.get(value, value) if isinstance(value, str) else value

            spec = transform(other['securities']['SECURITY_A'])
            references = [reference for interval in spec['intervals']
                          for reference in (interval['identity_evidence'], interval['price_artifact'])]
            references.append(spec['rename_events'][0]['evidence'])
            for reference in references:
                path = Path(reference['path']); content = transform(json.loads(path.read_text()))
                raw = json.dumps(content).encode(); path.write_bytes(raw)
                reference['sha256'] = hashlib.sha256(raw).hexdigest()
            arguments['securities']['AAA_SECOND_CLASS'] = spec
            result = bridge.build_price_identity_bridge(**arguments)
            self.assertEqual(result['internal_columns_by_security']['SECURITY_A'],
                             alone['internal_columns_by_security']['SECURITY_A'])
            self.assertEqual(len(result['opens'].columns), 2)

            # Even correctly rehashed files cannot bind one provider instrument
            # to two concurrently distinct securities/share classes.
            for interval in spec['intervals']:
                interval['provider_instrument_id'] = 'PROVIDER_SEC1'
                for reference in (interval['identity_evidence'], interval['price_artifact']):
                    path = Path(reference['path'])
                    content = json.loads(path.read_text())
                    content['provider_instrument_id'] = 'PROVIDER_SEC1'
                    raw = json.dumps(content).encode()
                    path.write_bytes(raw)
                    reference['sha256'] = hashlib.sha256(raw).hexdigest()
            with self.assertRaisesRegex(ValueError, 'share provider instrument'):
                bridge.build_price_identity_bridge(**arguments)


if __name__ == '__main__': unittest.main()
