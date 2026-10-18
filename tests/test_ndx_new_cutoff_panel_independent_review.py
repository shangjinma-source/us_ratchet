"""Synthetic codec and projection review only; no actual panel assembly or fit."""
from copy import deepcopy
from decimal import getcontext, localcontext, Inexact
import json
import unittest
from unittest.mock import patch
import test_ndx_new_cutoff_conditional_panel_20260923 as fixture

m=fixture.m


class IndependentPanelReview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.docs={role:json.loads((m.BASE/path).read_bytes()) for role,(path,_) in m.BOUND.items()}

    def test_new_anchor_and_all_legacy_risk_dates_are_preserved(self):
        arguments,sidecars=m.project_inputs(self.docs)
        originals={r['ticker']:r for r in self.docs['wiring']['rows']}
        for ticker in m.NEW_ANCHORS:
            sidecar=next(r for r in sidecars if r['ticker']==ticker)
            self.assertEqual(sidecar['wiring_row'],originals[ticker])
            self.assertEqual(arguments['risk_assumptions'][ticker]['source_kind'],'LEGACY_LOCAL_RISK_LABEL_NOT_NEW_ADJUDICATION')
            self.assertFalse(arguments['coordinate_assumptions'][ticker]['latest_interval_verified'])
        self.assertEqual(len(sidecars),101)

    def test_all_new_risk_observations_must_agree(self):
        docs=deepcopy(self.docs)
        row=next(r for r in docs['wiring']['rows'] if r['ticker']=='QCOM')
        row['risk_sources'][0]['all_saved_observations'][0]['risk_chain']='contradiction'
        with self.assertRaisesRegex(ValueError,'historical risk'):m.project_inputs(docs)

    def test_wire_hash_and_dated_anchor_cannot_be_swapped(self):
        for attack in ('hash','anchor','pointer'):
            docs=deepcopy(self.docs);row=next(r for r in docs['wiring']['rows'] if r['ticker']=='TXN')
            if attack=='hash':row['channel_row_sha256']='0'*64
            elif attack=='pointer':row['channel_audit_reference']['json_pointer']='/details/0'
            else:row['complete_original_evidence'][0]['complete_original_fact']['evidence']['dated_evidence']['filing_date']='2023-02-10'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.project_inputs(docs)

    def test_typed_roundtrip_rejects_numeric_string_timezone_and_range_bool(self):
        for attack in ('string','timezone','range_bool','infinite'):
            encoded=m.typed_encode(fixture.small_panel())
            if attack=='string':encoded['nominal_close']['data'][0][0]='10.0'
            elif attack=='timezone':encoded['raw_volume']['index'][0]+='+00:00'
            elif attack=='range_bool':encoded['universe']['index'][0]=False
            else:encoded['dollar_volume']['data'][0][0]=float('inf')
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.typed_decode(encoded)

    def test_context_reset_and_singleton_mapping_do_not_imply_issuer_pair_allowed(self):
        panel=fixture.small_panel();panel['conditional_security_count']=2
        panel['panel_content_sha256']=m.core.panel_digest(panel);observed=[]
        def synthetic_core(**kwargs):
            observed.append((getcontext().prec,getcontext().traps[Inexact]))
            return deepcopy(panel)
        with localcontext() as context:
            context.prec=2;context.traps[Inexact]=True
            with patch.object(m,'project_inputs',return_value=({},[])),patch.object(m.core,'assemble_conditional_panel',side_effect=synthetic_core):
                result=m.assemble({})
        self.assertEqual(observed,[(80,False)])
        decoded=m.typed_decode(result['panel'])
        with self.assertRaisesRegex(ValueError,'duplicate an issuer'):
            m.core.selected_mapping(decoded,decoded['universe']['security_id'].tolist())
        self.assertFalse(result['strict_loader_validation_passed'])


if __name__=='__main__':unittest.main()
