import unittest
from copy import deepcopy
from test_ndx_multidecision_account_inputs_research import fixture as candidate_fixture,ref
from backtest import ndx_multidecision_account_inputs_research as c
from backtest import ndx_multidecision_incumbent_inputs_research as m


def fixture():
 a=candidate_fixture();ci=c.prepare_multidecision_account_inputs(**a);refs={k:ref('candidate/'+k) for k in ('inputs','publication','readback','reader')};ce=dict(document=dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1',inputs=ci),publication=dict(inputs_reference=refs['inputs']),readback=dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=refs['reader']['sha256'],inputs_reference=refs['inputs'],publication_reference=refs['publication']),references=refs)
 securities=[];rows=[]
 for i,t in enumerate(m.TICKERS):
  sec=dict(security_id='CONTROL:'+t,ticker=t,issuer_id='ISS:'+t,risk_chain='CHAIN:'+t,target_weight=.125);securities.append(sec);ch=deepcopy(a['price_evidence']['document']['rows'][i]['channel']);ch.update(ticker=t,status='CONDITIONAL_NUMERIC_RESULT',calendar=a['price_evidence']['document']['calendar253']);ch['receipt_preserved']['ticker']=t
  meta=dict(complete_original_control_security=deepcopy(sec),shares_or_prices_converted=False,control_only_overlay=t=='TSM',raw_reference=ch['raw_reference'],receipt_reference=ch['receipt_reference'])
  rows.append(dict(original_control_security=deepcopy(sec),channel=ch,complete_benchmark_metadata=meta,complete_parent_row=None if t=='TSM' else {'preserved':True},mode='ONE_NEW_TSM_RAW_RECONSTRUCTION' if t=='TSM' else 'EXACT_SEALED_CHANNEL_REUSE_NO_ARITHMETIC'))
 o=dict(schema='ORIGINAL_EIGHT_LONG_WINDOW_CONDITIONAL_CHANNELS_V1',rows=rows,original_control_order=m.TICKERS,original_control_preserved=dict(securities=securities,complete_original_definition=dict(securities=deepcopy(securities))),calendar253=a['price_evidence']['document']['calendar253'],original_candidate_provenance=[{'i':i} for i in range(101)],preserved_candidate_evidence_sidecars={str(i):{} for i in range(7)},**dict.fromkeys(('weights_normalized','weights_reoptimized','holdings_or_quotes_converted','point_in_time_verified','execution_authorized','promotion_allowed','complete_corporate_actions_verified'),False))
 refs={k:ref('original/'+k) for k in ('inputs','publication','readback','reader')};oe=dict(document=o,publication=dict(schema='ORIGINAL_EIGHT_LONG_WINDOW_CHANNELS_PUBLICATION_V1',channels_reference=refs['inputs']),readback=dict(schema='ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_V1',status='PASS',channels_sha256=refs['inputs']['sha256'],publication_sha256=refs['publication']['sha256'],reader_sha256=refs['reader']['sha256']),references=refs)
 for obj in (ce['document'],ce['publication']):obj.update(dict.fromkeys(m.PFLAGS,False))
 ce['publication'].update(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1',status='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS')
 ce['readback'].update(scope='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION',inspection=dict(coordinate_count=48,lane_count=8,track_count=16,security_count=77,issuer_count=76,provenance_count=101,sidecar_count=7),**dict.fromkeys(('producer_called','account_engine_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed'),False))
 for obj in (o,oe['publication']):obj.update(dict.fromkeys(m.ORIGINAL_FLAGS,False))
 oe['publication']['status']='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_TSM_READBACK'
 oe['readback'].update(new_raw_ticker='TSM',reused_tickers=[t for t in m.TICKERS if t!='TSM'],original_provenance_count=101,preserved_sidecar_count=7,price_rows=253,open_close_values=506,returns=252,training_returns=126,evaluation_returns=126,**dict.fromkeys(('reused_channels_recomputed','untouched_holdout','point_in_time_verified','benchmark_qualified','fit_performed','account_simulation_performed'),False))
 return dict(candidate_evidence=ce,original_eight_evidence=oe)

class Tests(unittest.TestCase):
 def test_all_controls_mapping_tsm_and_original_weights(self):
  a=fixture();before=m.digest(a);r=m.prepare_incumbent_account_inputs(**a);self.assertEqual(m.digest(a),before);self.assertEqual((r['lane_count'],r['track_count'],r['coordinate_count']),(8,16,48));self.assertFalse(r['source_slots'][4]['candidate_universe_member_claimed'])
  for lane in r['rows']:
   for tr in lane['tracks']:
    self.assertEqual(tr['status'],'CONTROL_INPUTS_PREPARED_NOT_EXECUTED');kw=tr['engine_binding']['keyword_arguments'];self.assertEqual(len(kw['schedule']),6);self.assertEqual(len(kw['opens']['columns']),8);self.assertEqual(kw['schedule'][0]['targets']['CONTROL:TSM']['target_weight'],.125)
  self.assertEqual(r['rows'][0]['tracks'][0]['candidate_status_preserved'],'BLOCKED_ENGINE_OR_SOURCE_INPUT')
 def test_missing_control_price_blocks_without_dropping_column(self):
  a=fixture();ch=a['original_eight_evidence']['document']['rows'][4]['channel'];ch['quote_rows'].pop(-1);ch['quote_rows_sha256']=m.digest(ch['quote_rows']);r=m.prepare_incumbent_account_inputs(**a)
  t=r['rows'][-1]['tracks'][1];self.assertEqual(t['status'],'BLOCKED_ORIGINAL_CONTROL_INPUT');self.assertEqual(len(t['engine_binding']['keyword_arguments']['opens']['columns']),8);self.assertIsNone(t['engine_binding']['keyword_arguments']['opens']['data'][-1][4])
 def test_same_flow_no_dedup_and_no_input_mutation(self):
  a=fixture();ci=a['candidate_evidence']['document']['inputs'];flow=dict(session='2026-04-01',amount_usd=123.,currency='USD',timing='BEFORE_OPEN',source_reference=ref('flow'))
  for tr in ci['rows'][4]['tracks']:tr['stateful_input']['external_flows']=[deepcopy(flow)]
  ci['content_sha256']=m.digest({k:v for k,v in ci.items() if k!='content_sha256'});r=m.prepare_incumbent_account_inputs(**a)
  self.assertEqual(r['rows'][4]['tracks'][0]['engine_binding']['keyword_arguments']['external_flows'],[flow]);self.assertEqual(r['rows'][5]['tracks'][0]['engine_binding']['keyword_arguments']['external_flows'],[]);self.assertFalse(r['control_deduplication_performed'])
 def test_tsm_scoring_or_wrong_identity_rejected(self):
  for mode in ('role','schema','weight'):
   a=fixture();o=a['original_eight_evidence']['document']
   if mode=='role':o['rows'][4]['mode']='EXACT_SEALED_CHANNEL_REUSE_NO_ARITHMETIC'
   elif mode=='schema':o['schema']='ORIGINAL_EIGHT_SCORING_INPUTS_V1'
   else:o['rows'][4]['original_control_security']['target_weight']=.5
   with self.assertRaises(ValueError):m.prepare_incumbent_account_inputs(**a)

if __name__=='__main__':unittest.main()
