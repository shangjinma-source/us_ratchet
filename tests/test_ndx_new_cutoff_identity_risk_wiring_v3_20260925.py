"""Saved-parent and synthetic declaration transforms only; no publishing."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_identity_risk_wiring_v3_20260925 as m


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.parent=m.loads(Path(m.ref('parent_wiring')['path']).read_bytes())

    def docs(self):
        old=deepcopy(self.parent);row=next(r for r in old['rows'] if r['ticker']=='CPRT')
        declaration=dict(schema='CPRT_SAVED_RISK_CONDITIONAL_ADJUDICATION_V1',**row['coordinate'],risk_chain='automotive',conditional_risk_chain_assigned=True,research_only=True,
            assumed_window=dict(first='2026-03-20',last='2026-09-21'),new_window_assumption='Synthetic explicit assumption',
            original_identity_fact=deepcopy(row['complete_original_evidence'][0]['complete_original_fact']),original_business_fact=dict(assigned_risk_chain=None,risk_chain_assigned=False,boundary_status='UNRESOLVED_EXISTING_ALTERNATIVES',candidate_risk_chains=['internet_ecommerce','automotive','industrial']),
            saved_seed_decision={},saved_review_decision=dict(selection_date='2026-07-13'),saved_review_selection_postdates_window_start=True,early_window_review_availability_verified=False,
            point_in_time_verified=False,legal_training_input_admitted=False,promotion_allowed=False,execution_authorized=False)
        return dict(parent_wiring=old,cprt_declaration=declaration)

    def test_only_cprt_changed_all_old_sidecars_exact(self):
        docs=self.docs();result=m.assemble(docs);old=docs['parent_wiring']
        self.assertEqual([r for r in result['rows'] if r['ticker']!='CPRT'],[r for r in old['rows'] if r['ticker']!='CPRT'])
        self.assertEqual(result['extended_provenance'],old['extended_provenance'])
        row=next(r for r in result['rows'] if r['ticker']=='CPRT')
        self.assertIsNone(row['complete_original_evidence'][0]['complete_original_fact']['risk_chain'])
        self.assertEqual((result['candidate_security_count'],result['candidate_issuer_count']),(22,21))
        self.assertIsNone(result['fit_column_count']);self.assertFalse(result['typed_panel_rebuilt'])
        self.assertEqual(result['conditional_candidates_with_saved_volume_unit_block'],old['conditional_candidates_with_saved_volume_unit_block'])

    def test_declaration_coordinate_authority_window_attacks(self):
        for key,value in [('security_id','wrong'),('risk_chain','other'),('point_in_time_verified',True),('assumed_window',{})]:
            docs=self.docs();docs['cprt_declaration'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.assemble(docs)

    def test_original_null_and_fact_tamper_rejected(self):
        docs=self.docs();docs['cprt_declaration']['original_identity_fact']['risk_chain']='automotive'
        with self.assertRaises(ValueError):m.assemble(docs)
        docs=self.docs();docs['cprt_declaration']['original_business_fact']['assigned_risk_chain']='automotive'
        with self.assertRaises(ValueError):m.assemble(docs)
        docs=self.docs();docs['cprt_declaration']['early_window_review_availability_verified']=True
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_pending_anchor_and_existing_namespace(self):
        bound=deepcopy(m.BOUND);bound['cprt_declaration']=(bound['cprt_declaration'][0],None)
        with patch.object(m,'BOUND',bound),patch.object(m,'assemble') as assemble:
            with self.assertRaises(ValueError):m.build()
            assemble.assert_not_called()
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'wiring.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()


if __name__=='__main__':unittest.main()
