import copy
import json
import unittest
from hashlib import sha256
from data.current_quantity_v2_pullback_chain_review import verify_chain
from data.current_quantity_v2_pullback_entry import digest
from data.current_quantity_v2_pullback_sources import candidate_from_yahoo_bytes
from test_current_quantity_v2_pullback_sources import payload


class ChainReviewTests(unittest.TestCase):
    def fixture(self):
        raw = json.dumps(payload()).encode()
        rows = []; prior = None; parent = ''
        for ordinal in range(2):
            at = '2026-10-15T13:32:%02d+00:00' % (15 + ordinal)
            parameters = dict(expected_sha256=sha256(raw).hexdigest(), security_id='SNDK-ID', ticker='SNDK',
                session='2026-10-15', session_open='2026-10-15T13:30:00+00:00', session_close='2026-10-15T20:00:00+00:00',
                captured_at=at, checked_at=at, now=at, rebound_fraction='1/2', minimum_discount='1/200', maximum_age_seconds=120)
            result = candidate_from_yahoo_bytes(raw=raw, previous_cap=prior, **parameters)
            record_hash = digest(dict(ordinal=ordinal, parameters=parameters, result=result, previous_hash=parent))
            rows.append(dict(binding=result['candidate']['binding'], ordinal=ordinal, parameters=parameters,
                result=result, previous_hash=parent, record_hash=record_hash, raw_hex=raw.hex()))
            pullback = dict(result['candidate'], prior_cap=prior, cap_record_hash=record_hash, status='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED')
            prior = result['candidate']['cap_declaration']; parent = record_hash
        return dict(schema='LOCAL_PULLBACK_CHAIN_EXPORT_V1', rows=rows), raw, pullback

    def test_full_prior_prefix_and_mutations(self):
        chain, raw, pullback = self.fixture()
        def replay(value, pb=pullback, quote=raw):
            return verify_chain(json.dumps(value).encode(), pullback['cap_record_hash'], quote, pb)
        self.assertEqual(replay(chain), chain['rows'][-1]['result']['candidate'])
        with self.assertRaisesRegex(ValueError,'PULLBACK_CHAIN_AFTER_OBSERVATION'):
            verify_chain(json.dumps(chain).encode(),pullback['cap_record_hash'],raw,pullback,observed_at='2026-10-15T13:32:15+00:00')
        for mutation in ('parent', 'ordinal', 'raw', 'result', 'missing_prefix', 'prior', 'quote'):
            c = copy.deepcopy(chain); p = copy.deepcopy(pullback); q = raw
            if mutation == 'parent': c['rows'][1]['previous_hash'] = 'a'*64
            if mutation == 'ordinal': c['rows'][1]['ordinal'] = 3
            if mutation == 'raw': c['rows'][0]['raw_hex'] = b'{}'.hex()
            if mutation == 'result': c['rows'][0]['result']['candidate']['limit_price'] = '1'
            if mutation == 'missing_prefix': c['rows'].pop(0)
            if mutation == 'prior': p['prior_cap']['limit_price'] = '1'
            if mutation == 'quote': q += b' '
            with self.subTest(mutation=mutation), self.assertRaises(ValueError): replay(c, p, q)


if __name__ == '__main__': unittest.main()
