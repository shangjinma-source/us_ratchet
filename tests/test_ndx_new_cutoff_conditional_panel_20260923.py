"""Projection and small typed fixtures; never build the actual new panel."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from scripts import ndx_new_cutoff_conditional_panel_20260923 as m


def small_panel():
    index=pd.date_range('2026-05-18',periods=127)
    columns=['GOOG','GOOGL']
    panel=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V1',scope=m.core.SCOPE,cutoff='2026-09-21',
        returns=pd.DataFrame(0.,columns=columns,index=index[1:]),nominal_close=pd.DataFrame(10.,columns=columns,index=index),
        raw_volume=pd.DataFrame(10000000,columns=columns,index=index[-63:],dtype='int64'),
        dollar_volume=pd.DataFrame(100000000.,columns=columns,index=index[-63:]),
        universe=pd.DataFrame([['security:0001652044:02079K107','issuer:0001652044','GOOG','02079K107','Class C','platform_advertising',100000000.],
            ['security:0001652044:02079K305','issuer:0001652044','GOOGL','02079K305','Class A','platform_advertising',100000000.]],
            columns=['security_id','issuer_id','ticker','cusip','security_class','risk_chain','median_dollar_volume_usd']),**dict.fromkeys(m.core.FALSE,False))
    panel['panel_content_sha256']=m.core.panel_digest(panel)
    return panel


class PanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.docs={role:json.loads((m.BASE/path).read_bytes()) for role,(path,_) in m.BOUND.items()}

    def test_projection_only_new_numeric_and_explicit_dates_and_all101(self):
        arguments,evidence=m.project_inputs(self.docs)
        self.assertEqual(len(arguments['observed_rows']),101)
        self.assertEqual(len(arguments['coordinate_assumptions']),19)
        self.assertEqual(arguments['coordinate_assumptions']['TXN']['dated_fact']['dated_as_of'],'2022-02-10')
        self.assertEqual(arguments['coordinate_assumptions']['GOOGL']['dated_fact']['dated_as_of'],'2023-02-01')
        self.assertNotIn('PCAR',arguments['coordinate_assumptions']);self.assertNotIn('CRWD',arguments['coordinate_assumptions'])
        self.assertNotIn('CMCSA',arguments['channels'])
        self.assertEqual(arguments['channels']['MNST']['liquidity']['status'],'BLOCKED_VOLUME_UNIT_UNKNOWN')
        adbe=next(row for row in evidence if row['ticker']=='ADBE')
        self.assertTrue(adbe['dated_anchor_reference']['json_pointer'].endswith('/facts/filing_date'))
        for channel in self.docs['channels']['rows']:
            if channel['status']=='CONDITIONAL_NUMERIC_RESULT':self.assertEqual(arguments['channels'][channel['ticker']],channel['channel_input'])

    def test_codec_exact_and_duplicate_issuer_only_rejected_as_combination(self):
        panel=small_panel();encoded=m.typed_encode(panel);decoded=m.typed_decode(encoded)
        self.assertEqual(m.core.panel_digest(decoded),panel['panel_content_sha256'])
        ids=decoded['universe'].security_id.tolist()
        for sid in ids:self.assertEqual(len(m.core.selected_mapping(decoded,[sid])),1)
        with self.assertRaisesRegex(ValueError,'duplicate an issuer'):m.core.selected_mapping(decoded,ids)

    def test_codec_rejects_bool_dtype_midnight_duplicate_and_shape(self):
        for attack in ('bool','dtype','midnight','duplicate','shape'):
            encoded=m.typed_encode(small_panel())
            if attack=='bool':encoded['raw_volume']['data'][0][0]=True
            elif attack=='dtype':encoded['returns']['dtypes'][0]='object'
            elif attack=='midnight':encoded['returns']['index'][0]+='garbage'
            elif attack=='duplicate':encoded['returns']['columns'][1]='GOOG'
            else:encoded['returns']['data'][0].pop()
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.typed_decode(encoded)

    def test_issuer_order_reference_and_audit_row_attacks(self):
        for attack in ('issuer','order','reference','audit'):
            docs=deepcopy(self.docs)
            if attack=='issuer':docs['old_panel']['panel']['observed_provenance_and_missing'][1]['observed_issuer_id']='issuer:9999999999'
            elif attack=='order':docs['old_panel']['panel']['observed_provenance_and_missing'].reverse()
            elif attack=='reference':docs['wiring']['input_references']['channels']['sha256']='0'*64
            else:docs['audit']['details'][0]['status']='BLOCKED_PRICE_INPUT'
            with self.subTest(attack=attack),self.assertRaises(ValueError):m.project_inputs(docs)

    def test_old_numeric_cells_not_considered_by_projection(self):
        expected=m.project_inputs(self.docs)
        docs=deepcopy(self.docs)
        for name in ('returns','nominal_close','raw_volume','dollar_volume'):docs['old_panel']['panel'][name]={'UNUSABLE_OLD_VALUES':True}
        self.assertEqual(m.project_inputs(docs),expected)

    def test_fixed_namespace_and_source_guard(self):
        with tempfile.TemporaryDirectory() as directory,patch.object(m,'OUTPUT',Path(directory)/'panel.json'),patch.object(m,'build') as build:
            with self.assertRaises(ValueError):m.publish()
            build.assert_not_called()
        with patch.object(m.Path,'read_bytes',return_value=b'drift'):
            with self.assertRaises(ValueError):m.guard({})


if __name__=='__main__':unittest.main()
