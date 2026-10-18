"""Reference-only delta attacks; never builds or publishes a wiring artifact."""
from copy import deepcopy
import json
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_identity_risk_wiring_v2_20260924 as fixture

m=fixture.m


class IndependentIncrementReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.docs={k:json.loads((m.BASE/p).read_bytes()) for k,(p,_) in m.BOUND.items()}

    def test_all_increment_evidence_and_original_rows_remain_exact(self):
        value=m.assemble(self.docs);old={r['ticker']:r for r in self.docs['original_wiring']['rows']}
        for ext in value['extended_provenance']:
            role='pcar_adjudication' if ext['ticker']=='PCAR' else 'crwd_identity'
            self.assertEqual(ext['complete_increment_evidence'],self.docs[role])
            self.assertEqual(ext['original_row'],old[ext['ticker']])
            self.assertFalse(ext['prior_facts_modified'])
            self.assertFalse(ext['numerical_or_training_admission_inferred'])
        rows={r['ticker']:r for r in value['rows']}
        self.assertEqual(rows['GOOG'],old['GOOG']);self.assertEqual(rows['GOOGL'],old['GOOGL'])
        self.assertNotEqual(rows['GOOG']['coordinate']['security_id'],rows['GOOGL']['coordinate']['security_id'])
        self.assertEqual(rows['CPRT'],old['CPRT'])
        self.assertIsNone(value['fit_column_count']);self.assertFalse(value['typed_panel_rebuilt'])

    def test_old_unassigned_facts_cannot_be_rewritten_as_previous_assignment(self):
        for attack in ('row','nested'):
            d=deepcopy(self.docs);row=next(r for r in d['original_wiring']['rows'] if r['ticker']=='PCAR')
            if attack=='row':row['risk_chain']='automotive'
            else:row['complete_original_evidence'][0]['complete_original_fact']['risk_chain_assigned']=True
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(d)

    def test_new_identity_must_keep_bound_audit_and_old_volume_gap(self):
        for attack in ('reference','old_volume','old_gap','bool_audit'):
            d=deepcopy(self.docs)
            if attack=='reference':d['crwd_identity']['input_references']['audit']['sha256']='0'*64
            elif attack=='bool_audit':d['audit']['completed']=True
            else:
                r=next(r for r in d['original_wiring']['rows'] if r['ticker']=='CRWD')
                if attack=='old_volume':r['independent_channel_detail']['liquidity_status']='PASS'
                else:r['gaps'].remove('SAVED_VOLUME_UNIT_RESTRICTION_RETAINED')
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.assemble(d)

    def test_consumed_blob_mismatch_stops_before_assemble(self):
        with patch.object(m,'guard'),patch.object(m.Path,'read_bytes',return_value=b'changed'),patch.object(m,'assemble') as assemble:
            with self.assertRaisesRegex(ValueError,'Consumed parent hash'):m.build()
            assemble.assert_not_called()


if __name__=='__main__':unittest.main()
