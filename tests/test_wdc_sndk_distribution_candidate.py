import json
from pathlib import Path
import unittest
from data.wdc_sndk_distribution_candidate import build_candidate
from backtest.return_priority_distribution_entitlements import apply_distribution

ROOT='tmp/wdc_sndk_distribution_evidence_20261016_v1/'

def arguments():
    facts=Path(ROOT+'event_candidate.json').read_bytes()
    pins=json.loads(facts)['source_hashes']
    return dict(facts_bytes=facts,readback_bytes=Path(ROOT+'root_fact_readback.json').read_bytes(),
        official_bytes={p:Path(p).read_bytes() for p in pins},facts_path=ROOT+'event_candidate.json',
        readback_path=ROOT+'root_fact_readback.json',parent_sid='security:0000106040:958102105',
        child_sid='security:0002023554:80004C200',previous_close_at='2025-02-21T16:00:00-05:00',
        next_open_at='2025-02-24T09:30:00-05:00')

class CandidateTests(unittest.TestCase):
    def test_actual_bytes_map_without_admitting(self):
        r=build_candidate(**arguments());e=r['event_candidate']
        self.assertEqual(e['effective_date'],'2025-02-21')
        self.assertEqual(e['legal_distribution_at_new_york'],'2025-02-22T02:59:00-05:00')
        self.assertEqual(e['child_ratio'],'1/3');self.assertIsNone(e['eligibility_confirmed'])
        self.assertFalse(r['broker_delivery_verified'])
        with self.assertRaisesRegex(ValueError,'eligibility_confirmed'):
            apply_distribution(state=dict(cash='0',shares={e['parent_sid']:3}),
                event=dict(e,eligible_parent_quantity=3),as_of='2025-02-21')

    def test_raw_tamper_and_invalid_clock_refused(self):
        a=arguments();key=next(iter(a['official_bytes']));a['official_bytes'][key]+=b'changed'
        with self.assertRaisesRegex(ValueError,'HASH_MISMATCH'):build_candidate(**a)
        a=arguments();a['previous_close_at']='2025-02-24T16:00:00-05:00'
        with self.assertRaises(ValueError):build_candidate(**a)

if __name__=='__main__':unittest.main()
