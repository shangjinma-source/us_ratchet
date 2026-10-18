"""Read-only sealed fixtures and in-memory attacks; no build or publication."""
from copy import deepcopy
import json
import unittest
import test_ndx_new_cutoff_identity_risk_wiring_20260923 as fixture

m=fixture.m


class IndependentWiringReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs={role:json.loads((m.BASE/path).read_bytes()) for role,(path,_) in m.BOUND.items()}

    def test_complete_evidence_and_each_saved_risk_observation_are_preserved(self):
        output=m.assemble(self.docs);rows={r['ticker']:r for r in output['rows']}
        original={r['ticker']:r for r in self.docs['panel']['panel']['observed_provenance_and_missing']}
        for ticker in m.PANEL_TICKERS:
            self.assertEqual(rows[ticker]['risk_sources'][0]['original_risk_assumption'],original[ticker]['risk_assumption'])
            self.assertNotIn('median_dollar_volume_usd',rows[ticker]['coordinate'])
        for original_row in self.docs['legacy']['rows']:
            ticker=original_row['ticker']
            if ticker not in rows:continue
            row=rows[ticker];sid=original_row['security_id']
            self.assertEqual(row['complete_original_evidence'][-1]['complete_original_fact'],original_row)
            expected=[dict(observation_date=d,risk_chain=mp[sid]) for d,mp in sorted(self.docs['legacy']['selected_risk_chains_by_decision'].items()) if sid in mp]
            self.assertEqual(row['risk_sources'][-1]['all_saved_observations'],expected)
            self.assertIn(self.docs['legacy']['conditional_window'],row['original_windows'])

    def test_old_window_and_provider_certification_upgrades_fail(self):
        for attack in ('window','provider','risk_interval'):
            docs=deepcopy(self.docs)
            row=next(r for r in docs['panel']['panel']['observed_provenance_and_missing'] if r['ticker']=='AMAT')
            if attack=='window':row['coordinate_assumption']['assumed_window']['last']='2026-09-21'
            elif attack=='provider':row['coordinate_assumption']['provider_binding_verified']=True
            else:row['risk_assumption']['latest_interval_verified']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_audit_exact_candidate_and_complete_denominator_required(self):
        for attack in ('hash','count_bool','missing','order'):
            docs=deepcopy(self.docs)
            if attack=='hash':docs['audit']['candidate_reference']['sha256']='0'*64
            elif attack=='count_bool':docs['audit']['completed']=True
            elif attack=='missing':docs['audit']['details'].pop()
            else:docs['audit']['details'][0],docs['audit']['details'][1]=docs['audit']['details'][1],docs['audit']['details'][0]
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(docs)

    def test_unassigned_and_unassembled_have_no_implied_authority(self):
        rows=m.assemble(self.docs)['rows']
        self.assertEqual(sum(r['coordinate'] is None for r in rows),80)
        for row in rows:
            self.assertTrue(all(row[k] is False for k in m.FALSE))
            if row['ticker'] in ('PCAR','CPRT'):
                self.assertIsNone(row['risk_chain']);self.assertIsNone(row['new_assumption'])
                self.assertEqual(row['risk_sources'],[])
            if row['coordinate'] is None:
                self.assertIsNone(row['risk_chain']);self.assertIsNone(row['new_assumption'])


if __name__=='__main__':unittest.main()
