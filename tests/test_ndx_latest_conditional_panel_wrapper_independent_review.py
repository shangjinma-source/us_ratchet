import copy
import json
import unittest
from unittest.mock import patch
import pandas as pd
from scripts import ndx_latest_conditional_panel_20260919 as reader
from test_ndx_latest_conditional_panel_research import fixture


class WrapperIndependentTests(unittest.TestCase):
    def test_typed_roundtrip_remains_usable_by_selected_mapping(self):
        panel=reader.core.assemble_conditional_panel(**fixture())
        decoded=reader.typed_decode(reader.typed_encode(panel))
        sid=decoded['universe'].iloc[0]['security_id']
        self.assertEqual(reader.core.selected_mapping(decoded,[sid]),reader.core.selected_mapping(panel,[sid]))

    def test_actual_coordinate_builder_matches_frozen_pure_contract(self):
        calendar=['2026-03-18','2026-09-17']
        doc=json.loads((reader.BASE/reader.ANCHORS['four'][0]).read_bytes())
        fact=next(r for r in doc['rows'] if r['ticker']=='GOOG')
        value=reader.coordinate_from_fact('GOOG',fact,'four',calendar)
        observed={'ticker':'GOOG','issuer_id':'issuer:'+fact['issuer_cik']}
        actual=reader.core.coordinate(value,observed,calendar)
        self.assertEqual(actual['security_id'],fact['security_id'])

    def test_actual_nine_coordinates_through_frozen_assemble(self):
        docs={k:json.loads((reader.BASE/reader.ANCHORS[k][0]).read_bytes()) for k in ('four','seven','two','observed','fifteen')}
        calendar=docs['observed']['observed_reference_calendar'][-127:]
        observed=[dict(ticker=r['ticker'],issuer_id=r['conditional_issuer_id']) for r in docs['observed']['rows']]
        prototype=fixture()['channels']['T0'];channels={};audits={};coordinates={};risks={}
        for ticker in sorted(reader.TICKERS):
            value=copy.deepcopy(prototype);value.update(ticker=ticker,calendar=calendar,cutoff=calendar[-1])
            for row,day in zip(value['price_rows'],calendar):row['session']=day
            for row,a,b in zip(value['price_returns'],calendar,calendar[1:]):row.update(session=b,previous_session=a)
            for row,day in zip(value['liquidity']['rows'],calendar[-63:]):row['session']=day
            channels[ticker]=value
            audits[ticker]=dict(channel_sha256=reader.core.canonical_sha(value),passed=True,source_references=[reader.reference('audit')])
            key='two' if ticker in ('NFLX','PANW') else 'four' if ticker in ('AMAT','AVGO','CDNS','GOOG') else 'seven'
            fact=next(r for r in docs[key]['rows'] if r['ticker']==ticker)
            coordinates[ticker]=reader.coordinate_from_fact(ticker,fact,key,calendar)
            proposal=next(r for r in docs['fifteen']['rows'] if r['ticker']==ticker)
            risks[ticker]=dict(scope=reader.core.SCOPE,latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,
                historical_labels=[proposal['risk_chain_candidate']],risk_chain=proposal['risk_chain_candidate'],source_kind=proposal['risk_source_kind'],source_references=[reader.reference('fifteen')])
        panel=reader.core.assemble_conditional_panel(observed_rows=observed,calendar=calendar,cutoff=calendar[-1],channels=channels,channel_audits=audits,coordinate_assumptions=coordinates,risk_assumptions=risks)
        self.assertEqual(panel['conditional_security_count'],9)
        self.assertEqual(reader.typed_decode(reader.typed_encode(panel))['panel_content_sha256'],panel['panel_content_sha256'])

    def test_typed_relabel_and_numeric_coercion_rejected(self):
        panel=reader.core.assemble_conditional_panel(**fixture());encoded=reader.typed_encode(panel)
        for mutate in ('bool','date','precision'):
            bad=copy.deepcopy(encoded)
            if mutate=='bool':bad['returns']['data'][0][0]=False
            elif mutate=='date':bad['returns']['index'][0]=bad['returns']['index'][0][:10]
            else:bad['returns']['dtypes'][0]='float32';bad['returns']['data'][0][0]=0.123456789
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):reader.typed_decode(bad)

    def test_verify_rejects_hard_source_resigning_before_rebuild(self):
        value=dict(schema='SOURCE_BOUND_LATEST_NINE_CONDITIONAL_PANEL_V1',historical_expected_source_hashes=dict(reader.LOADED,**{str(reader.BASE/p):h for p,h in reader.ANCHORS.values()}))
        for key in ('target_cardinality_fixed','source_point_in_time_verified','legal_training_input_admitted','historical_six_input_training_ready','fit_performed','execution_authorized','winner_selected','promotion_allowed'):value[key]=False
        value['historical_expected_source_hashes'][reader.reference('audit')['path']]='0'*64
        with patch.object(reader,'build',side_effect=AssertionError('Must reject before rebuild')):
            with self.assertRaises(ValueError):reader.verify(value)


if __name__=='__main__':unittest.main()
