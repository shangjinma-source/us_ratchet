from copy import deepcopy
from datetime import date,timedelta
import unittest
from backtest import ndx_multidecision_account_inputs_research as m


def ref(name):return {'path':'/synthetic/'+name,'sha256':m.digest(name)}
def fixture():
    days=[];d=date(2026,9,21)
    while len(days)<253:
        if d.weekday()<5:days.append(d.isoformat())
        d-=timedelta(days=1)
    days.reverse();rows=[];audits=[]
    selected={f'SID{i:03}':dict(ticker=f'T{i:03}',issuer_id=f'I{i:03}',risk_chain=f'R{i}') for i in range(4)}
    flags=dict.fromkeys(('execution_authorized','promotion_allowed','point_in_time_verified','source_bytes_authenticated','optimization_reperformed'),False)
    outer=[]
    for di,cutoff in enumerate(m.CUTOFFS):
      for mi,mode in enumerate(m.MODES):
       for li,lane in enumerate(m.LANES):
        i=di*8+mi*4+li;coordinate=[cutoff,mode,lane]
        if mi==0:outer.append(dict(coordinate_index=i,coordinate=coordinate,status='SOURCE_BLOCKED',evidence=None));continue
        refs={k:ref(f'{i}/{k}') for k in ('request','raw_result','postcheck','readback','reader')}
        identity=dict(selected=deepcopy(selected),requested_previous_target_weights=None if di==0 else {s:.25 for s in selected})
        request=dict(schema='OUTER_LANE_CUTOFF_REFIT_REQUEST_V1',coordinate=coordinate,numerical_identity=identity,fit_matrix={'dates':[cutoff]},numerical_task_id=m.digest([cutoff,'numeric']),location_id=m.digest(coordinate),**flags)
        targets={s:{'ticker':v['ticker'],'issuer_id':v['issuer_id'],'target_weight':.25} for s,v in selected.items()}
        body=dict(schema='ndx_dynamic_cutoff_refit_research_v2',cutoff=cutoff,targets=targets)
        raw=dict(result=body,**flags)
        post=dict(request_reference=refs['request'],raw_result_reference=refs['raw_result'],outcome='REFIT_PASSED_PENDING_INDEPENDENT_READBACK',**flags)
        audit=dict(schema='OUTER_LANE_CUTOFF_REFIT_INDEPENDENT_READBACK_V1',reader_sha256=refs['reader']['sha256'],scope='SAVED_OUTER_RESULT_ARITHMETIC_AND_SOURCE_BINDING_NOT_REOPTIMIZATION',numerical_task_id=request['numerical_task_id'],location_id=request['location_id'],status='PASS',prior_eligible=True,attempt_outcome=post['outcome'],raw_result_body_sha256=m.digest(body),targets_preserved=deepcopy(targets),source_hashes={r['path']:r['sha256'] for k,r in refs.items() if k!='readback'},**flags)
        for role in ('request','raw_result','postcheck'):audit[role+'_reference']=refs[role]
        outer.append(dict(coordinate_index=i,coordinate=coordinate,status='AUDITED',evidence=dict(request=request,raw_result=raw,postcheck=post,readback=audit,references=refs)))
    for i in range(77):
        raw=ref(f'raw{i}');receipt=ref(f'receipt{i}');quotes=[dict(session=x,nominal_open_exact='100',nominal_close_exact='101') for x in days]
        channel=dict(ticker=f'T{i:03}',raw_reference=raw,receipt_reference=receipt,quote_rows=quotes,quote_rows_sha256=m.digest(quotes),returned_events={},event_policies=[],receipt_preserved=dict(raw_path=raw['path'],raw_sha256=raw['sha256'],ticker=f'T{i:03}',request_url='https://example.test/'+str(i)))
        rows.append(dict(coordinate=dict(security_id=f'SID{i:03}',ticker=f'T{i:03}',issuer_id=f'I{min(i,75):03}'),channel=channel,original_identity_assumed_window={'first':'2026-03-20','last':'2026-09-21'}))
        audits.append(dict(ticker=channel['ticker'],raw_reference=raw,receipt_reference=receipt,quote_rows_sha256=channel['quote_rows_sha256']))
    refs={k:ref(k) for k in ('channels','publication','readback','reader')}
    p=dict(schema='BULK_LONG_WINDOW_CONDITIONAL_CHANNELS_V1',rows=rows,calendar253=days,original_provenance_and_missing=[{'original':i} for i in range(101)],preserved_evidence_sidecars={str(i):{'original':i} for i in range(7)},**dict.fromkeys(('point_in_time_verified','execution_authorized','promotion_allowed','complete_corporate_actions_verified'),False))
    audit=dict(status='PASS',channels_sha256=refs['channels']['sha256'],publication_sha256=refs['publication']['sha256'],reader_sha256=refs['reader']['sha256'],per_channel=audits)
    return dict(outer_rows=outer,price_evidence=dict(document=p,readback=audit,references=refs),execution_contract=dict(schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUT_CONTRACT_V1',reference=ref('contract'),parameters=deepcopy(m.PARAMETERS),valuation_end_date=days[-1],cash_flow_role='ZERO_FLOW_BASELINE'),flows_by_lane={mode+'|'+lane:[] for mode in m.MODES for lane in m.LANES},benchmark_references={k:ref(k) for k in ('target_012922','original_8_incumbent')})


def reuse(args,index=5,origin_index=4):
    e=args['outer_rows'][index]['evidence'];origin=deepcopy(args['outer_rows'][origin_index]['evidence'])
    e['numerical_reuse_evidence']=origin;e['raw_result']=deepcopy(origin['raw_result']);e['references']['raw_result']=deepcopy(origin['references']['raw_result'])
    e['postcheck'].update(outcome='REUSED_AUDITED_NUMERICAL_RESULT',current_location_call_invoked=False,current_location_returned_call_count=0,raw_result_reference=e['references']['raw_result'],numerical_reuse_evidence_references=deepcopy(origin['references']))
    e['readback'].update(raw_result_reference=e['references']['raw_result'],attempt_outcome=e['postcheck']['outcome'])
    for r in origin['references'].values():e['readback']['source_hashes'][r['path']]=r['sha256']


class Tests(unittest.TestCase):
 def test_complete_domain_single_state_per_track_and_adjacent_targets(self):
    a=fixture();before=m.digest(a);out=m.prepare_multidecision_account_inputs(**a)
    self.assertEqual(m.digest(a),before);self.assertEqual((out['lane_count'],out['track_count'],out['coordinate_count']),(8,16,48))
    self.assertEqual(len(out['full_candidate_inventory_preserved']),77);self.assertEqual(len(out['original_provenance_and_missing']),101);self.assertEqual(len(out['preserved_evidence_sidecars']),7)
    self.assertEqual([x['execution_date'] for x in out['execution_clock_from_saved_calendar']],['2026-04-01','2026-05-01','2026-06-01','2026-07-01','2026-08-03','2026-09-01'])
    for row in out['rows'][:4]:self.assertEqual(len(row['tracks'][0]['blocking_reasons']),6)
    for row in out['rows'][4:]:
      for t in row['tracks']:
        self.assertEqual(len(t['stateful_input']['schedule']),6);self.assertEqual(t['stateful_input']['calendar'][0],'2026-03-31');self.assertFalse(t['account_simulation_performed'])
        self.assertEqual(t['stateful_input']['schedule'][0]['targets']['SID000']['target_weight'],.25)
    out['rows'][4]['tracks'][0]['own_initial_state']['cash_usd']=0
    self.assertEqual(out['rows'][4]['tracks'][1]['own_initial_state']['cash_usd'],25000)
 def test_full_reuse_origin_preserved_without_account_sharing(self):
    a=fixture();reuse(a);out=m.prepare_multidecision_account_inputs(**a)
    self.assertEqual(out['outer_coordinate_rows_preserved'][5],a['outer_rows'][5]);self.assertEqual(out['rows'][4]['original_targets_schedule'],out['rows'][5]['original_targets_schedule'])
    a['outer_rows'][5]['evidence'].pop('numerical_reuse_evidence')
    with self.assertRaises(ValueError):m.prepare_multidecision_account_inputs(**a)
 def test_risk_failure_reuse_preserves_full_chain_without_cash_fabrication(self):
    a=fixture();reuse(a)
    for index in (4,5):
      e=a['outer_rows'][index]['evidence'];e['readback'].update(status='PASS_SAVED_RISK_FAILURE',prior_eligible=False)
      e['postcheck']['outcome']='REFIT_RISK_FAILED' if index==4 else 'REUSED_AUDITED_NUMERICAL_RISK_FAILURE'
    origin=deepcopy(a['outer_rows'][4]['evidence']);a['outer_rows'][5]['evidence']['numerical_reuse_evidence']=origin
    for di in range(1,6):
      for li in (0,1):a['outer_rows'][di*8+4+li].update(evidence=None,status='NO_REFIT_INPUT_OR_ADJACENT_PRIOR')
    out=m.prepare_multidecision_account_inputs(**a)
    for row in out['rows'][4:6]:
      self.assertEqual(row['original_targets_schedule'],[])
      self.assertEqual(row['tracks'][0]['status'],'BLOCKED_ENGINE_OR_SOURCE_INPUT')
      self.assertEqual(len(row['tracks'][0]['blocking_reasons']),6)
    self.assertEqual(out['outer_coordinate_rows_preserved'][5]['evidence']['numerical_reuse_evidence'],origin)
 def test_flows_kept_nonrebalance_and_initial_close_boundary(self):
    a=fixture();a['execution_contract']['cash_flow_role']='EXPLICIT_NEW_CASH_RESEARCH';key=m.MODES[1]+'|RETURN'
    a['flows_by_lane'][key]=[dict(session='2026-03-31',amount_usd=0,currency='USD',timing='BEFORE_OPEN',source_reference=ref('flow0')),dict(session='2026-04-02',amount_usd=1000,currency='USD',timing='BEFORE_OPEN',source_reference=ref('flow1'))]
    o=m.prepare_multidecision_account_inputs(**a);t=o['rows'][4]['tracks'][0]
    self.assertEqual(t['stateful_input']['external_flows'],a['flows_by_lane'][key]);self.assertIn('FLOW_BEFORE_INITIAL_DECISION_CLOSE_REQUIRES_EXPLICIT_INITIAL_CAPITAL_CONTRACT',[x['reason'] for x in t['blocking_reasons']])
    for value in (True,-1,'1000',float('inf')):
      b=deepcopy(a);b['flows_by_lane'][key][1]['amount_usd']=value
      with self.assertRaises(ValueError):m.prepare_multidecision_account_inputs(**b)
 def test_split_and_missing_quote_preserve_slots_and_block(self):
    a=fixture();ch=a['price_evidence']['document']['rows'][0]['channel'];ch['event_policies']=[dict(session='2026-04-06',kind='ORDINARY_SPLIT',numerator=25,denominator=1)]
    j=next(j for j,r in enumerate(ch['quote_rows']) if r['session']=='2026-04-07');ch['quote_rows'][j]['nominal_open_exact']=None
    ch['quote_rows_sha256']=m.digest(ch['quote_rows']);a['price_evidence']['readback']['per_channel'][0]['quote_rows_sha256']=ch['quote_rows_sha256']
    o=m.prepare_multidecision_account_inputs(**a);t=o['rows'][4]['tracks'][0];s=t['stateful_input']
    self.assertEqual(s['corporate_actions'][0]['new_shares'],25);self.assertIsNone(s['opens']['data'][s['calendar'].index('2026-04-07')][0]);self.assertIn('MISSING_SAVED_NOMINAL_FIELD',[x['reason'] for x in t['blocking_reasons']]);self.assertEqual(t['engine_binding']['source_reference']['sha256'],m.FRACTIONAL_ENGINE['sha256'])
 def test_new_fractional_engine_explicit_arguments_allow_later_flow_and_split(self):
    a=fixture();a['execution_contract']['cash_flow_role']='EXPLICIT_NEW_CASH_RESEARCH'
    key=m.MODES[1]+'|RETURN';a['flows_by_lane'][key]=[dict(session='2026-04-02',amount_usd=1000,currency='USD',timing='BEFORE_OPEN',source_reference=ref('later'))]
    a['price_evidence']['document']['rows'][0]['channel']['event_policies']=[dict(session='2026-04-06',kind='ORDINARY_SPLIT',numerator=25,denominator=1)]
    out=m.prepare_multidecision_account_inputs(**a);frac,whole=out['rows'][4]['tracks']
    self.assertEqual(frac['status'],'ENGINE_INPUTS_PREPARED_NOT_EXECUTED');self.assertEqual(frac['blocking_reasons'],[])
    kwargs=frac['engine_binding']['keyword_arguments']
    self.assertEqual(set(kwargs),{'closes','opens','schedule','corporate_actions','external_flows','initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps','valuation_end_date'})
    self.assertEqual(kwargs['external_flows'],a['flows_by_lane'][key]);self.assertEqual(kwargs['corporate_actions'][0]['new_shares'],25)
    self.assertEqual(whole['status'],'ENGINE_INPUTS_PREPARED_NOT_EXECUTED');self.assertEqual(whole['engine_binding']['keyword_arguments']['external_flows'],a['flows_by_lane'][key])
 def test_actual_whole_flow_api_synthetic_signature_and_own_state(self):
    import pandas as pd
    from backtest.ndx_dynamic_frozen_flow_split_research import simulate_dynamic_frozen_flow_split_research
    a=fixture();a['execution_contract']['cash_flow_role']='EXPLICIT_NEW_CASH_RESEARCH'
    a['flows_by_lane'][m.MODES[1]+'|RETURN']=[dict(session='2026-04-02',amount_usd=1000,currency='USD',timing='BEFORE_OPEN',source_reference=ref('wholeflow'))]
    out=m.prepare_multidecision_account_inputs(**a);before=m.digest(out);results=[]
    for row in out['rows'][4:6]:
      kwargs=deepcopy(row['tracks'][1]['engine_binding']['keyword_arguments'])
      for key in ('opens','closes'):
        f=kwargs[key];kwargs[key]=pd.DataFrame(f['data'],index=pd.to_datetime(f['index']),columns=f['columns'])
      result=simulate_dynamic_frozen_flow_split_research(**kwargs);results.append(result)
      self.assertEqual(result['schema'],'DYNAMIC_WHOLE_LOT_USD_FLOW_SPLIT_ACCOUNT_V1')
    self.assertEqual(m.digest(out),before)
    self.assertEqual(sum(d['cash_injection_usd'] for d in results[0]['daily']),1000)
    self.assertEqual(sum(d['cash_injection_usd'] for d in results[1]['daily']),0)
 def test_prior_and_domain_false_types_rejected(self):
    for mutate in (lambda a:a['outer_rows'][12]['evidence']['request']['numerical_identity'].update(requested_previous_target_weights=None),lambda a:a['outer_rows'][0].update(coordinate_index=False),lambda a:a['outer_rows'][4]['evidence']['readback'].update(execution_authorized=0)):
      a=fixture();mutate(a)
      with self.assertRaises(ValueError):m.prepare_multidecision_account_inputs(**a)

if __name__=='__main__':unittest.main()
