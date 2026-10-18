"""Projection metadata and synthetic numeric tests; no actual panel audit/build."""
from copy import deepcopy
from decimal import Decimal,Context,localcontext
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd

spec=importlib.util.spec_from_file_location('panel_reader',Path(__file__).resolve().parents[1]/'scripts/ndx_new_cutoff_typed_panel_independent_readback_20260923.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def channel():
 days=pd.bdate_range('2026-03-20',periods=127).strftime('%Y-%m-%d').tolist()
 price=10.000000000000002;volume=10000001
 with localcontext(Context(prec=50)):dollar=Decimal(str(price))*volume
 c=dict(schema='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1',ticker='GOOG',calendar=days,cutoff=days[-1],
  price_rows=[dict(session=d,nominal_close=price) for d in days],
  price_returns=[dict(previous_session=a,session=b,price_return=0.0,declared_share_ratio='1') for a,b in zip(days,days[1:])],
  liquidity=dict(status='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE',rows=[dict(session=d,raw_volume=volume,dollar_volume=str(dollar)) for d in days[-63:]],median_dollar_volume_usd=str(dollar),numerical_threshold_passed=True),
  minimum_median_dollar_volume_usd=50000000,**dict.fromkeys(m.CHANNEL_FALSE,False))
 return c,days


def panel():
 c,days=channel();values=m.channel_numbers(c,days);index=pd.DatetimeIndex(days);cols=['GOOG','GOOGL']
 p=dict(returns=pd.DataFrame({t:values[0] for t in cols},index=index[1:],dtype='float64'),
  nominal_close=pd.DataFrame({t:values[1] for t in cols},index=index,dtype='float64'),
  raw_volume=pd.DataFrame({t:values[2]['volumes'] for t in cols},index=index[-63:],dtype='int64'),
  dollar_volume=pd.DataFrame({t:values[2]['dollars'] for t in cols},index=index[-63:],dtype='float64'),
  universe=pd.DataFrame([['security:0001652044:02079K107','issuer:0001652044','GOOG','02079K107','Class C','platform_advertising',values[2]['median']],
   ['security:0001652044:02079K305','issuer:0001652044','GOOGL','02079K305','Class A','platform_advertising',values[2]['median']]],columns=m.UNIVERSE),
  **dict.fromkeys(m.PANEL_FALSE,False))
 p['panel_content_sha256']=m.checksum(p);return p


class Tests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):cls.docs={k:json.loads((m.BASE/p).read_bytes()) for k,(p,h) in m.BOUND.items()}
 def test_metadata_projection_all101_and19sid18issuer(self):
  days,old,channels,a,coords,risks,side=m.projections(self.docs)
  self.assertEqual((len(days),len(old),len(coords),len(side)),(127,101,19,101))
  self.assertNotEqual(coords['GOOG']['security_id'],coords['GOOGL']['security_id'])
  self.assertEqual(coords['GOOG']['issuer_id'],coords['GOOGL']['issuer_id'])
  self.assertEqual(coords['TXN']['dated_fact']['dated_as_of'],'2022-02-10')
  self.assertNotIn('CRWD',coords);self.assertNotIn('PCAR',coords)
  self.assertEqual(channels['CRWD']['liquidity']['status'],'BLOCKED_VOLUME_UNIT_UNKNOWN')
 def test_old_numbers_not_read(self):
  docs=deepcopy(self.docs)
  for key in m.FRAMES:docs['old_panel']['panel'][key]={'unusable':True}
  self.assertEqual(m.projections(docs),m.projections(self.docs))
 def test_dollar_boundary_and_ambient_precision(self):
  c,days=channel()
  with localcontext(Context(prec=5)):a=m.channel_numbers(c,days)
  with localcontext(Context(prec=100)):b=m.channel_numbers(c,days)
  self.assertEqual(a,b)
  with localcontext(Context(prec=50)):expected=float(Decimal(str(c['price_rows'][0]['nominal_close']))*c['liquidity']['rows'][0]['raw_volume'])
  self.assertEqual(a[2]['dollars'],[expected]*63)
 def test_nonzero_return_and_blocked_volume(self):
  c,days=channel();c['price_rows'][0]['nominal_close']=c['price_rows'][1]['nominal_close']/1.1;c['price_returns'][0]['price_return']=0.1
  self.assertEqual(m.channel_numbers(c,days)[0][0],0.1)
  c['liquidity']=dict(status='BLOCKED_VOLUME_UNIT_UNKNOWN',rows=None,median_dollar_volume_usd=None,numerical_threshold_passed=None)
  self.assertEqual(m.channel_numbers(c,days)[3],'BLOCKED_VOLUME_UNIT_UNKNOWN')
  c['liquidity']['rows']=[]
  with self.assertRaises(ValueError):m.channel_numbers(c,days)
 def test_exact_codec_and_class_preservation(self):
  p=panel();e=m.encode_frames(p);d=m.decode_frames(e)
  self.assertEqual(d['universe'].issuer_id.nunique(),1)
  self.assertEqual(d['universe'].security_id.nunique(),2)
  self.assertEqual(m.checksum(d),p['panel_content_sha256'])
 def test_codec_bool_timezone_fractional_volume_and_checksum(self):
  for attack in ('bool','tz','fractional','checksum'):
   e=m.encode_frames(panel())
   if attack=='bool':e['returns']['data'][0][0]=False
   elif attack=='tz':e['nominal_close']['index'][0]+='+00:00'
   elif attack=='fractional':e['raw_volume']['data'][0][0]=10000001.5
   else:e['panel_content_sha256']='0'*64
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.decode_frames(e)
 def test_sidecar_and_source_mutations(self):
  for attack in ('issuer','risk','anchor','audit'):
   d=deepcopy(self.docs)
   if attack=='issuer':next(r for r in d['old_panel']['panel']['observed_provenance_and_missing'] if r['ticker']=='GOOG')['observed_issuer_id']='issuer:9999999999'
   elif attack=='audit':d['audit']['details'][0]['reasons']=['FORGED']
   else:
    row=next(r for r in d['wiring']['rows'] if r['ticker']=='TXN')
    if attack=='risk':row['risk_chain']='OTHER'
    else:row['complete_original_evidence'][0]['complete_original_fact']['evidence']['dated_evidence']['filing_date']='2026-09-21'
   with self.subTest(attack=attack),self.assertRaises(ValueError):m.projections(d)
 def test_hard_candidate_and_repeat_guard(self):
  self.assertEqual(len(m.CANDIDATE_SHA),64)
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/'audit.json';p.write_text('{}')
   with patch.object(m,'OUTPUT',p),patch.object(m,'build') as b:
    with self.assertRaises(ValueError):m.publish()
    b.assert_not_called()
  with patch.object(m.Path,'read_bytes',return_value=b'changed'):
   with self.assertRaises(ValueError):m.guard({})

if __name__=='__main__':unittest.main()
