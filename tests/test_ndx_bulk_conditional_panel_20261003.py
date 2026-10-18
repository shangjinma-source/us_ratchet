from copy import deepcopy
from pathlib import Path
import sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ndx_bulk_conditional_panel_20261003 as m

def channel(ticker,days):
 return dict(schema='CONDITIONAL_PROVIDER_CHANNEL_INPUT_V1',ticker=ticker,calendar=days,cutoff=days[-1],price_rows=[dict(session=d,nominal_close=100.0) for d in days],price_returns=[dict(previous_session=days[i],session=days[i+1],price_return=.01) for i in range(126)],liquidity=dict(status='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE',numerical_threshold_passed=True,rows=[dict(session=d,raw_volume=1000000,dollar_volume='100000000') for d in days[-63:]],median_dollar_volume_usd='100000000'),minimum_median_dollar_volume_usd=50000000,**dict.fromkeys(m.core.CHANNEL_FALSE,False))

def fixture():
 days=[d.strftime('%Y-%m-%d') for d in m.pd.bdate_range('2026-03-20',periods=126)]+['2026-09-21']
 names=['O'+str(i) for i in range(24)]+['N'+str(i) for i in range(53)]+['CRWD']+['M'+str(i) for i in range(23)]
 coords={t:dict(ticker=t,security_id='sid:'+t,issuer_id='issuer:'+('O0' if t=='O1' else t),cusip=t,security_class='Common') for t in names}
 channels=[];details=[];oldrows=[]
 for i,t in enumerate(names):
  c=dict(ticker=t,status='CONDITIONAL_NUMERIC_RESULT',channel_input=channel(t,days));channels.append(c);details.append(dict(ticker=t))
  if t=='CRWD':c['channel_input']['liquidity'].update(status='BLOCKED_VOLUME_UNIT_UNKNOWN',rows=None,median_dollar_volume_usd=None,numerical_threshold_passed=None)
  oldrows.append(dict(ticker=t,coordinate=coords[t] if t.startswith('O') else None,risk_chain='r' if t.startswith('O') else None,channel_reference=m.ref('channels','/rows/'+str(i)),channel_audit_reference=m.ref('channel_audit','/details/'+str(i)),channel_row_sha256=m.sha(m.encode(c)),independent_channel_detail=details[-1]))
 oldw=dict(calendar=days,rows=oldrows,promotion_allowed=False,**dict.fromkeys(('extended_provenance','v3_extended_provenance','v4_extended_provenance','v5_extended_provenance','v6_extended_provenance'),[]))
 w=deepcopy(oldw);w['source_hashes']={};w.update(schema='BULK_CONDITIONAL_IDENTITY_RISK_WIRING_V1',candidate_security_count=78,candidate_issuer_count=77,fit_column_count=None,input_references={'parent':m.ref('parent_wiring')},bulk_extended_provenance=[dict(ticker=t,original_null_row=deepcopy(oldrows[names.index(t)])) for t in names[24:77]])
 for r in w['rows'][24:77]:r.update(coordinate=coords[r['ticker']],risk_chain='r',new_assumption={'window':{'first':days[0],'last':days[-1]}})
 ix=m.pd.DatetimeIndex(days);tickers=names[:24];uni=m.pd.DataFrame([dict(coords[t],risk_chain='r',median_dollar_volume_usd=100000000.) for t in tickers],columns=['security_id','issuer_id','ticker','cusip','security_class','risk_chain','median_dollar_volume_usd']).sort_values('security_id').reset_index(drop=True)
 panel=dict(schema='LATEST_CONDITIONAL_TYPED_PANEL_V6',scope=m.core.SCOPE,returns=m.pd.DataFrame(.01,index=ix[1:],columns=tickers),nominal_close=m.pd.DataFrame(100.,index=ix,columns=tickers),raw_volume=m.pd.DataFrame(1000000,index=ix[-63:],columns=tickers,dtype='int64'),dollar_volume=m.pd.DataFrame(100000000.,index=ix[-63:],columns=tickers),universe=uni,observed_provenance_and_missing=[dict(ticker=t,observed_issuer_id=coords[t]['issuer_id'],included_in_conditional_panel=t in tickers,blocking_reasons=[] if t in tickers else ['NO_IDENTITY']) for t in names],**dict.fromkeys(m.core.FALSE,False))
 panel['panel_content_sha256']=m.core.panel_digest(panel)
 parent=dict(schema='NEW_CUTOFF_CONDITIONAL_TYPED_PANEL_DOCUMENT_V6',panel=m.codec.typed_encode(panel),input_references={k:m.ref(k) for k in ('channels','channel_audit')},promotion_allowed=False,numeric_projection_policy='parent',issuer_observation_basis='saved',**{k:[] for k in m.SIDECARS});parent['input_references']['wiring']=m.ref('parent_wiring')
 return dict(wiring=w,wiring_publication=dict(schema='BULK_CONDITIONAL_WIRING_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_METADATA_ONLY',wiring_reference=m.ref('wiring'),source_hashes={},promotion_allowed=False),parent_wiring=oldw,parent_panel=parent,parent_readback=dict(schema='NEW_CUTOFF_TYPED_PANEL_INCREMENT_INDEPENDENT_READBACK_V6',status='PASSED',candidate_reference=m.ref('parent_panel'),panel_content_sha256=panel['panel_content_sha256'],full_original101_and_incremental_sidecars_compared=True,promotion_allowed=False),channels=dict(calendar=days,rows=channels,promotion_allowed=False),channel_audit=dict(candidate_reference=m.ref('channels'),status='PASSED',completed=101,details=details,promotion_allowed=False))

class Tests(unittest.TestCase):
 def test_full_synthetic53_parent_exact_no_old_calculator(self):
  d=fixture()
  with patch.object(m.core,'channel_values',side_effect=AssertionError('old calculator')):v=m.assemble(d)
  self.assertEqual((v['actual_panel_security_count'],v['actual_panel_issuer_count']),(77,76));self.assertEqual(len(v['bulk_incremental_evidence_and_projection']),53);self.assertTrue(all(x['exact'] for x in v['original24_frame_exact_proof'].values()))
  for k in m.SIDECARS:self.assertEqual(v[k],d['parent_panel'][k])
 def test_gates_not_forced(self):
  for kind in ['price','volume','threshold']:
   d=fixture();r=d['channels']['rows'][24]
   if kind=='price':r.update(status='BLOCKED_PRICE_INPUT',channel_input=None)
   elif kind=='volume':r['channel_input']['liquidity']['status']='BLOCKED_VOLUME_UNIT_UNKNOWN'
   else:r['channel_input']['liquidity']['numerical_threshold_passed']=False
   for role in ['wiring','parent_wiring']:d[role]['rows'][24]['channel_row_sha256']=m.sha(m.encode(r))
   v=m.assemble(d);self.assertEqual(v['actual_panel_security_count'],76);self.assertIn('N0',v['new_numeric_blocks']);self.assertFalse(v['bulk_incremental_evidence_and_projection'][0]['numerical_column_added']);self.assertIn('coordinate_assumption',v['bulk_incremental_evidence_and_projection'][0]['new_gap']);self.assertEqual(v['bulk_incremental_evidence_and_projection'][0]['new_gap']['blocking_reasons'],[v['new_numeric_blocks']['N0']])
 def test_saved_float_not_original_decimal_dollars(self):
  d=fixture();c=channel('T',d['channels']['calendar']);c['price_rows'][-1]['nominal_close']=100.12345678901234;c['liquidity']['rows'][-1]['dollar_volume']='garbage not consumed'
  values,reason=m.saved_channel_projection(c,c['calendar']);self.assertIsNone(reason);self.assertEqual(values[2]['dollars'][-1],float(m.Decimal(str(100.12345678901234))*1000000));self.assertEqual(values[0],[.01]*126)
 def test_types_dates_oldcells(self):
  c=channel('T',fixture()['channels']['calendar']);c['liquidity']['rows'][0]['raw_volume']=True
  with self.assertRaises(ValueError):m.saved_channel_projection(c,c['calendar'])
  d=fixture();before=m.codec.typed_decode(d['parent_panel']['panel']);after=deepcopy(before);after['returns'].iloc[0,0]=.2
  with self.assertRaises(ValueError):m.original_frame_proof(before,after)
 def test_mapping_class_conflict(self):
  v=m.assemble(fixture());p=m.codec.typed_decode(v['panel']);self.assertEqual(len(m.selected_mapping_bulk(p,['sid:N0'])),1)
  with self.assertRaises(ValueError):m.selected_mapping_bulk(p,['sid:O0','sid:O1'])
 def test_attempt_failure_is_durable_no_retry(self):
  with tempfile.TemporaryDirectory() as t,patch.object(m,'OUTPUT',Path(t)/'new'/'panel.json'),patch.object(m,'read_inputs',return_value=({},{})),patch.object(m,'guard'),patch.object(m,'assemble',side_effect=ValueError('conversion failed')) as call:
   with self.assertRaises(ValueError):m.publish()
   self.assertEqual({p.name for p in m.OUTPUT.parent.iterdir()},{'started.json','failure.json'})
   with self.assertRaises(ValueError):m.publish()
   self.assertEqual(call.call_count,1)
 def test_pending_and_namespace(self):
  with patch.dict(m.BOUND,{'wiring':('pending',None)}),patch.object(m,'assemble') as call:
   with self.assertRaises(ValueError):m.build()
   call.assert_not_called()
  with tempfile.TemporaryDirectory() as t,patch.object(m,'OUTPUT',Path(t)/'panel.json'),patch.object(m,'build') as call:
   with self.assertRaises(ValueError):m.publish()
   call.assert_not_called()
if __name__=='__main__':unittest.main()
