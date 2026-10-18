"""Saved parent plus synthetic declaration; no actual build or publish."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_new_cutoff_identity_risk_wiring_v4_20260925 as m


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw=Path(m.ref('parent_wiring')['path']).read_bytes()
        assert m.sha(raw)==m.ref('parent_wiring')['sha256']
        cls.parent=m.loads(raw)

    def docs(self):
        decision=dict(decision_id='current:BKNG',risk_chain='travel_hospitality',status='accepted',confidence='high')
        review=dict(**decision,selection_date='2026-07-13',security_ids=['security:0001075531:current_ticker:BKNG'],
            issuer_id='issuer:0001075531',allow_fallback=False,accession_number='0001075531-26-000009',raw_sha256='a'*64)
        declaration=dict(schema='BKNG_CONDITIONAL_DATED_IDENTITY_RISK_V1',**deepcopy(m.COORDINATE),coordinate=deepcopy(m.COORDINATE),
            risk_chain='travel_hospitality',research_only=True,conditional_risk_chain_assigned=True,assumed_window=deepcopy(m.WINDOW),
            new_window_assumption='Synthetic retrospective assumption',saved_review_selection_postdates_window_start=True,saved_review_selection_date='2026-07-13',annual_fetched_at='2026-07-15T06:38:46+00:00',memo_received_at='2026-09-11T21:04:19.470604+00:00',
            saved_seed_decision=decision,saved_review_decision=review,
            registry_event=dict(ticker='BKNG',cusip='09857L108',security_class='COMMON',publication_date='2026-03-02',received_at_utc='2026-09-11T21:04:19.470604+00:00'),
            annual_manifest=dict(cik='0001075531',accession_number='0001075531-26-000009',fetched_at='2026-07-15T06:38:46+00:00',content_sha256='a'*64,research_only=True))
        for key in ('point_in_time_verified','legal_training_input_admitted','promotion_allowed','execution_authorized','early_window_review_availability_verified','early_window_local_evidence_available','direct_single_document_cusip_cik_proof','identity_interval_verified','risk_interval_verified','provider_binding_verified','complete_corporate_actions_verified','option_contract_terms_used_as_equity_identity'):
            declaration[key]=False
        return dict(parent_wiring=deepcopy(self.parent),bkng_declaration=declaration)

    def test_only_bkng_and_all_sidecars_exact(self):
        docs=self.docs();result=m.assemble(docs);old=docs['parent_wiring']
        self.assertEqual(m.canonical([r for r in result['rows'] if r['ticker']!='BKNG']),m.canonical([r for r in old['rows'] if r['ticker']!='BKNG']))
        for key in m.SIDECARS:self.assertEqual(result[key],old[key])
        self.assertEqual(result['v4_extended_provenance'][0]['complete_increment_evidence'],docs['bkng_declaration'])
        original=next(r for r in old['rows'] if r['ticker']=='BKNG')
        self.assertEqual(result['v4_extended_provenance'][0]['original_row'],original)
        new=next(r for r in result['rows'] if r['ticker']=='BKNG')
        for key in ('channel_reference','channel_audit_reference','channel_row_sha256','independent_channel_detail','complete_original_evidence','original_windows'):
            self.assertEqual(new[key],original[key])
        self.assertEqual((result['candidate_security_count'],result['candidate_issuer_count'],result['bounded_source_missing_count']),(23,22,78))
        self.assertIsNone(result['fit_column_count']);self.assertFalse(result['typed_panel_rebuilt'])
        self.assertEqual(docs['parent_wiring'],self.parent)

    def test_coordinate_class_window_risk_and_authority_attacks(self):
        for key,value in [('security_class','Bond'),('risk_chain','automotive'),('assumed_window',{}),
                          ('point_in_time_verified',True),('early_window_review_availability_verified',True),('early_window_local_evidence_available',True)]:
            docs=self.docs();docs['bkng_declaration'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.assemble(docs)

    def test_cannot_backdate_review_or_replace_original_current_ticker(self):
        for key,value in [('selection_date','2026-02-18'),('security_ids',[m.COORDINATE['security_id']]),('raw_sha256','b'*64)]:
            docs=self.docs();docs['bkng_declaration']['saved_review_decision'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.assemble(docs)
        docs=self.docs();docs['bkng_declaration']['memo_received_at']='2026-03-02'
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_crwd_block_and_full_denominator_required(self):
        docs=self.docs();next(r for r in docs['parent_wiring']['rows'] if r['ticker']=='CRWD')['independent_channel_detail']['liquidity_status']='READY'
        with self.assertRaises(ValueError):m.assemble(docs)
        docs=self.docs();docs['parent_wiring']['rows'].pop()
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_unassembled_original_state_required(self):
        docs=self.docs();next(r for r in docs['parent_wiring']['rows'] if r['ticker']=='BKNG')['risk_chain']='travel_hospitality'
        with self.assertRaises(ValueError):m.assemble(docs)

    def test_pending_anchor_and_existing_namespace_fail_before_build(self):
        bound=deepcopy(m.BOUND);bound['bkng_declaration']=(bound['bkng_declaration'][0],None)
        with patch.object(m,'BOUND',bound),patch.object(m,'assemble') as assemble:
            with self.assertRaises(ValueError):m.build()
            assemble.assert_not_called()
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'wiring.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()

    def test_duplicate_keys_and_source_drift(self):
        with self.assertRaises(ValueError):m.loads(b'{"x":0,"x":1}')
        with patch.object(m,'LOADED_SHA','f'*64):
            with self.assertRaises(ValueError):m.guard({})


if __name__=='__main__':unittest.main()
