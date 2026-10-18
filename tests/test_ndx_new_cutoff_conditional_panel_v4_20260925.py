"""V2 metadata validation and synthetic typed increment tests; no actual build."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd
from scripts import ndx_new_cutoff_conditional_panel_v4_20260925 as m


def parent():
 index=pd.bdate_range('2026-03-20',periods=127);cols=['GOOG','GOOGL']
 p=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V3',scope=m.core.SCOPE,
 returns=pd.DataFrame(0.,index=index[1:],columns=cols),nominal_close=pd.DataFrame(10.,index=index,columns=cols),
 raw_volume=pd.DataFrame(10000000,index=index[-63:],columns=cols,dtype='int64'),dollar_volume=pd.DataFrame(100000000.,index=index[-63:],columns=cols),
 universe=pd.DataFrame([dict(security_id='security:0001652044:02079K107',issuer_id='issuer:0001652044',ticker='GOOG',cusip='02079K107',security_class='Class C',risk_chain='platform_advertising',median_dollar_volume_usd=100000000.),
 dict(security_id='security:0001652044:02079K305',issuer_id='issuer:0001652044',ticker='GOOGL',cusip='02079K305',security_class='Class A',risk_chain='platform_advertising',median_dollar_volume_usd=100000000.)]),**dict.fromkeys(m.core.FALSE,False))
 p['panel_content_sha256']=m.core.panel_digest(p);return p


def numbers():return ([0.]*126,[20.]*127,dict(volumes=[10000000]*63,dollars=[200000000.]*63,median=200000000.),None)
def coordinate():return dict(security_id='security:0001075531:09857L108',issuer_id='issuer:0001075531',ticker='BKNG',cusip='09857L108',security_class='Common Stock par value $0.008 per share')


class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.docs={k:m.codec.loads((m.BASE/p).read_bytes()) for k,(p,h) in m.BOUND.items()}
 def test_actual_reference_projection_only(self):
  days=m.validate_sources(self.docs);self.assertEqual((len(days),days[0],days[-1]),(127,'2026-03-20','2026-09-21'))
 def test_mocked_increment_once_preserves_three_sidecars(self):
  with patch.object(m.core,'channel_values',return_value=numbers()) as calculate:
   result=m.assemble(self.docs)
  self.assertEqual(calculate.call_count,1)
  self.assertEqual(calculate.call_args.args[2],'BKNG')
  self.assertEqual((result['actual_panel_security_count'],result['actual_panel_issuer_count']),(22,21))
  self.assertEqual(result['source_coordinate_candidate_count'],23)
  for key in ('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection'):
   self.assertEqual(result[key],self.docs['parent_panel'][key])
  increment=result['v4_incremental_evidence_and_projection'][0]
  self.assertEqual(increment['dated_anchor_value'],'2026-03-02')
  self.assertFalse(increment['early_window_local_evidence_available'])
  self.assertTrue(all(v['exact'] for v in result['original21_frame_exact_proof'].values()))
 def test_only_append_preserves_original_sid_and_numeric_cells(self):
  p=parent();saved=m.canonical(m.codec.typed_encode(p));after,proof=m.append_bkng(p,numbers(),coordinate(),'travel_hospitality')
  self.assertEqual(m.canonical(m.codec.typed_encode(p)),saved)
  self.assertEqual(after['returns'].columns.tolist(),['BKNG','GOOG','GOOGL'])
  self.assertEqual(after['universe'].iloc[0].ticker,'BKNG')
  self.assertTrue(all(v['exact'] for v in proof.values()))
  self.assertNotIn('CRWD',after['returns'].columns)
 def test_old_cell_or_sid_corruption_rejected(self):
  for attack in ('price','sid'):
   p=parent();after,_=m.append_bkng(p,numbers(),coordinate(),'travel_hospitality')
   if attack=='price':after['nominal_close'].loc[after['nominal_close'].index[0],'GOOG']=11.
   else:after['universe'].loc[1,'security_class']='Class A'
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.original_frame_proof(p,after)
 def test_blocked_increment_not_forced_in(self):
  v=list(numbers());v[2]=None;v[3]='BLOCKED_VOLUME_UNIT_UNKNOWN'
  with self.assertRaises(ValueError):m.append_bkng(parent(),v,coordinate(),'travel_hospitality')
 def test_v2_mapping_explicit_schema_and_issuer_constraint(self):
  p,_=m.append_bkng(parent(),numbers(),coordinate(),'travel_hospitality');p['schema']='LATEST_CONDITIONAL_TYPED_PANEL_V4';p['panel_content_sha256']=m.core.panel_digest(p)
  sid=p['universe'].security_id.tolist()
  self.assertEqual(len(m.selected_mapping_v4(p,[sid[0],sid[1]])),2)
  with self.assertRaises(ValueError):m.selected_mapping_v4(p,sid[1:])
  with self.assertRaises(ValueError):m.core.selected_mapping(p,[sid[0]])
  p['schema']='LATEST_CONDITIONAL_TYPED_PANEL_V3';p['panel_content_sha256']=m.core.panel_digest(p)
  with self.assertRaises(ValueError):m.selected_mapping_v4(p,[sid[0]])
 def test_parent19_sidecar_and_crwd_boundary_attacks(self):
  for attack in ('old19','early','volume','audit'):
   docs=deepcopy(self.docs)
   if attack=='old19':next(r for r in docs['wiring']['rows'] if r['ticker']=='GOOG')['risk_chain']='OTHER'
   elif attack=='audit':docs['parent_readback']['candidate_reference']['sha256']='0'*64
   else:
    ext=next(r for r in docs['wiring']['extended_provenance'] if r['ticker']=='CRWD')
    if attack=='early':ext['early_window_evidence_available']=True
    else:ext['complete_increment_evidence']['volume_status']='PASS'
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.validate_sources(docs)
 def test_namespace_and_loaded_guard(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(m,'OUTPUT',Path(tmp)/'panel.json'),patch.object(m,'build') as build:
   with self.assertRaises(ValueError):m.publish()
   build.assert_not_called()
  with patch.object(m.Path,'read_bytes',return_value=b'drift'):
   with self.assertRaises(ValueError):m.guard({})
 def test_bkng_late_review_and_original_null_cannot_upgrade(self):
  for key,value in [('early_window_review_availability_verified',True),('saved_review_selection_date','2026-03-01')]:
   docs=deepcopy(self.docs);docs['wiring']['v4_extended_provenance'][0][key]=value
   with self.subTest(key=key),self.assertRaises(ValueError):m.validate_sources(docs)

if __name__=='__main__':unittest.main()
