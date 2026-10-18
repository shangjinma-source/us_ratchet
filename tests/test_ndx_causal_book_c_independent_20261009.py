"""Independent tiny synthetic oracles; no actual book/source/economic execution."""
from pathlib import Path
from copy import deepcopy
from fractions import Fraction as F
from unittest.mock import patch
import ast,hashlib,importlib.util,json,math,unittest
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'backtest/ndx_causal_research_book_mechanics_v1.py'
assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()=='d03bf29dea094bbe59480667cc395e8120f8ba1bd4642cf993d155715ca53f60'
sp=importlib.util.spec_from_file_location('c_mechanics_subject',SOURCE);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
OBS={}
def H(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def ref(k):return dict(path='c-synthetic/'+k,sha256=H(k),json_pointer='')
def sign(v):v['content_sha256']=H({k:x for k,x in v.items() if k!='content_sha256'})
def fixture(cash='1000',flows=(),quantities=None):
 cal=[dict(session=f'2026-10-{d:02d}',open_at_utc=f'2026-10-{d:02d}T13:30:00Z',close_at_utc=f'2026-10-{d:02d}T20:00:00Z') for d in range(5,10)]
 schedule=[dict(event_id=f'flow{i}',session=cal[i]['session'],amount_usd=str(amount),available_at_utc=cal[i-1]['close_at_utc']) for i,amount in enumerate(flows,1) if amount]
 scenario=dict(schema='CAUSAL_RESEARCH_SCENARIO_V1',scenario_id='C_ORACLE',currency='USD',quantity_domain='WHOLE_SHARES',book_lineage_id='C_BOOK',bootstrap_policy='EXPLICIT_POSITIVE_PRIOR_CLOSE_RESEARCH',cashflow_schedule=schedule,calendar=cal,lane_coordinate=dict(lane='SYNTHETIC_EXPLICIT',fx_mode='USD',lineage_kind='EXPLICIT_ONE_BOOK'),risk_policy_reference=ref('risk'),action_policy_reference=ref('policy'),source_requirements=['prices','identity_risk','corporate_events','calendar','cashflow'])
 context=dict(input_scope='SYNTHETIC_EXPLICIT',numeric_coverage={k:'DECLARED_COMPLETE' for k in scenario['source_requirements']},source_references_by_role={k:ref(k) for k in ('open_prices','close_prices','decision_prices','identity_risk','corporate_events','calendar')},full_inventory_reference=ref('full77-not-authenticated'),eligibility_blockers=['SOURCE_NOT_AUTHENTICATED'],authority=dict(m.FLAGS))
 initial=dict(session=cal[0]['session'],close_at_utc=cal[0]['close_at_utc'],holdings_by_sid=quantities or dict.fromkeys('ABCDE',1),cash_usd=cash)
 state=m.bootstrap_research_book(scenario=scenario,initial_state=initial,initial_marks={k:'10' for k in initial['holdings_by_sid']},source_context=context)['next_state']
 return scenario,context,state
def frame(scenario,context,state,op='10',cl='10',events=()):
 i=state['sequence']+1;c=scenario['calendar'][i];sids=state['holdings_by_sid']
 return dict(schema='CAUSAL_RESEARCH_FRAME_V1',session=c['session'],previous_state_sha256=state['content_sha256'],identity_risk_by_sid={s:dict(issuer_id='I'+s,risk_chain='R'+s) for s in sids},open_prices_usd=dict.fromkeys(sids,op),close_prices_usd=dict.fromkeys(sids,cl),cashflow_events=[deepcopy(x) for x in scenario['cashflow_schedule'] if x['session']==c['session']],corporate_events=list(events),source_context=deepcopy(context),session_open_at_utc=c['open_at_utc'],session_close_at_utc=c['close_at_utc'])
def action(scenario,state,f,status='EXPLICIT_NO_TRADE',aid=None):
 baseline=dict(schema='FROZEN_PRE_EVENT_ACTION_BASELINE_V1',phase='PRIOR_CLOSE_BEFORE_FRAME_EVENTS_AND_FLOW',previous_state_sha256=state['content_sha256'],holdings_by_sid=deepcopy(state['holdings_by_sid']),cash_usd=state['cash_usd'],planned_cashflow_event_ids=sorted(x['event_id'] for x in f['cashflow_events']))
 a=dict(schema='EXPLICIT_RESEARCH_ACTION_V1',status=status,action_id=aid or 'a'+str(state['sequence']+1),decision_session=state['session'],decision_at_utc=state['close_at_utc'],execution_session=f['session'],information_cutoff_utc=state['close_at_utc'],decision_state_sha256=state['content_sha256'],fill_baseline_sha256=H(baseline),frozen_baseline=baseline,policy_reference=scenario['action_policy_reference'],source_references={k:dict(reference=scenario['action_policy_reference'] if k=='policy' else f['source_context']['source_references_by_role'][k],available_at_utc=state['close_at_utc'],stage='DECISION_KNOWN_ONLY') for k in ('decision_prices','identity_risk','policy')})
 if status=='EXPLICIT_BUY':a['buy_shares']=dict.fromkeys(state['holdings_by_sid'],1)
 else:a['reason']='C_DECLARED_NO_TRADE'
 return a
def run(s,c,st,f,a):return m.advance_research_book(scenario=s,previous_state=st,frame=f,explicit_action=a)
def fr(v):return F(int(v['numerator']),int(v['denominator']))

class Independent(unittest.TestCase):
 def test_01_original_oracle_flow_split_and_fatal_pending(self):
  s,c,st=fixture(flows=(100,0,0,50));f=frame(s,c,st);a=action(s,st,f,'EXPLICIT_BUY');args=deepcopy((s,st,f,a));r=run(s,c,st,f,a)
  self.assertEqual((s,st,f,a),args);row=r['valuation_row'];self.assertEqual((row['cash_after_usd'],row['close_equity_usd'],row['fees_usd']),('1049.95','1149.95','0.05'));self.assertEqual(fr(row['session_twr']),-F(1,23000))
  self.assertEqual(r['content_sha256'],H({k:v for k,v in r.items() if k!='content_sha256'}));self.assertTrue(all(v is False for v in r['authority'].values()))
  st=r['next_state'];f=frame(s,c,st);f['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='splitA',session=f['session'],security_id='A',new_shares=2,old_shares=1)];f['open_prices_usd']['A']=f['close_prices_usd']['A']='5';a=action(s,st,f,'EXPLICIT_BUY');r=run(s,c,st,f,a)
  self.assertEqual(r['action_disposition'],'REJECTED_STALE_CORPORATE_ACTION');self.assertEqual(r['next_state']['holdings_by_sid']['A'],4);self.assertEqual(r['valuation_row']['fees_usd'],'0');self.assertEqual(fr(r['valuation_row']['session_twr']),0)
  for val in (0,True):
   bad=deepcopy(f);bad['source_context']['authority']['point_in_time_verified']=val
   with self.assertRaises(ValueError):run(s,c,st,bad,a)
  bad=deepcopy(a);bad['fill_baseline_sha256']='0'*64
  with self.assertRaises(ValueError):run(s,c,st,f,bad)
  missing=deepcopy(f);missing['source_context']['numeric_coverage']['corporate_events']='MISSING'
  self.assertIsNone(run(s,c,st,missing,a)['next_state'])
  pending=dict(schema='EXPLICIT_RESEARCH_ACTION_V1',status='PENDING_ACTION_POLICY',reason='UNREGISTERED',decision_session=st['session'],execution_session=f['session'])
  self.assertEqual(run(s,c,st,f,pending)['consumed_event_ids'],[])
  unsupported=deepcopy(f);unsupported['corporate_events']=[dict(schema='UNSUPPORTED_CORPORATE_EVENT_V1',event_id='divA',session=f['session'],security_id='A',kind='DIVIDEND')]
  self.assertIn('UNSUPPORTED_CORPORATE_EVENT',run(s,c,st,unsupported,a)['blockers'])
  r['next_state']['holdings_by_sid'].clear();self.assertEqual((s,st,f,a), (args[0],st,f,a))

 def test_02_nontrivial_four_frames_and_all13_views_no_io(self):
  oracle=json.loads((ROOT/'tmp/causal_book_nontrivial_view_oracle_c_20261009_v1/ORACLE.json').read_bytes())
  s,c,st=fixture(cash='100',flows=(20,0,30,5));timeline=[];states=[deepcopy(st)]
  # Fixed imports completed; business calls must perform no filesystem IO.
  with patch('builtins.open',side_effect=AssertionError('BusinessIO')),patch.object(Path,'read_bytes',side_effect=AssertionError('BusinessIO')):
   for i,expected in enumerate(oracle['frames']):
    op=('12','9','11','10')[i];cl=('11','10','8','13')[i];f=frame(s,c,st,op,cl);a=action(s,st,f);r=run(s,c,st,f,a);row=r['valuation_row']
    for field,source in (('previous_close_equity_usd','previous_close_equity'),('pre_flow_open_equity_usd','pre_flow_open_equity'),('post_flow_pre_fee_open_equity_usd','post_flow_equity'),('close_equity_usd','close_equity')):self.assertEqual(F(row[field]),fr(expected[source]))
    self.assertEqual(fr(row['overnight_return'])+1,fr(expected['overnight_factor']));self.assertEqual(fr(row['session_twr'])+1,fr(expected['session_factor']))
    timeline.append(dict(sequence=i+1,session=f['session'],previous_close_session=st['session'],previous_state_sha256=st['content_sha256'],state_sha256=r['next_state']['content_sha256'],book_lineage_id=s['book_lineage_id'],scenario_content_sha256=H(s),session_twr=row['session_twr'],status='COMPUTED'));st=r['next_state'];states.append(deepcopy(st))
   cal=[x['session'] for x in s['calendar']];mapping=dict(schema='ROLLING_BOOK_WINDOW_VIEW_MAPPING_V1',book_lineage_id=s['book_lineage_id'],scenario_content_sha256=H(s),calendar=cal,terminal_boundary=dict(kind='AFTER_LAST_SAVED_MARK',ordinal=5))
   windows=[dict(window_id='w'+str(v['window_ordinal']),fit_end='2026-10-02',evaluation_start=cal[v['interval'][0]],evaluation_end_inclusive=cal[v['interval'][1]-1]) for v in oracle['views']]
   views=m.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=timeline,mapping_contract=mapping)
   for saved,want in zip(views['rows'],oracle['views']):
    self.assertEqual(saved['view_twr'],want['correct_twr']);self.assertEqual([x['sequence'] for x in saved['frame_references']],want['included_frame_indices']);self.assertEqual(saved['anchor_state_sha256'],states[want['anchor_mark_index']]['content_sha256'])
   self.assertEqual(len(views['rows']),13)
   badmap=deepcopy(mapping);badmap['terminal_boundary']=None;blocked=m.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=timeline,mapping_contract=badmap);self.assertEqual(len(blocked['rows']),13);self.assertTrue(any('BLOCKED_ENDPOINT' in x['blockers'] for x in blocked['rows']))
   bad=deepcopy(timeline);bad[1]['previous_state_sha256']='0'*64
   with self.assertRaisesRegex(ValueError,'Adjacent hash'):m.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=bad,mapping_contract=mapping)
   bad=deepcopy(timeline);bad[0]['book_lineage_id']='other'
   with self.assertRaisesRegex(ValueError,'mixed'):m.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=bad,mapping_contract=mapping)
  OBS['nontrivial_oracle']='4 actual synthetic transitions/full13 views matched independent Fraction oracle;7 subtraction counterexamples,all13 overnight/end errors numerically observable; no IO.'

 def test_03_original_fixed_risk_formula_and_crosssession_causal(self):
  raw=(ROOT/'backtest/ndx_dynamic_whole_lot_repair_path.py').read_bytes();self.assertEqual(hashlib.sha256(raw).hexdigest(),'e614be1a2fe461e483e17413af03153f9a2fe99c31e0412b5daa8954c53d3f34')
  node=next(n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef) and n.name=='_risk_snapshot');node.returns=None
  for arg in node.args.args+node.args.kwonlyargs:arg.annotation=None
  ns=dict(math=math,NdxDynamicWholeLotRepairPathError=ValueError);exec(compile(ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[])),'fixed_original_risk','exec'),ns)
  identity={k:dict(issuer_id='I'+k,risk_chain='R'+k) for k in 'ABCDE'}
  for marks in (dict.fromkeys('ABCDE',10.0),dict(A=10000.0,B=1.0,C=1.0,D=1.0,E=1.0),dict(A=45.00000001,B=20.0,C=15.0,D=10.0,E=10.0)):
   original=ns['_risk_snapshot'](dict.fromkeys('ABCDE',1),marks,{k:'R'+k for k in 'ABCDE'},max_single_weight=.45,min_single_weight=.05,top_weight_cap=.8,minimum_effective_n_ratio=.7,risk_chain_top1_cap=.55)
   actual=m.risk_snapshot(dict.fromkeys('ABCDE',1),{k:F(str(v)) for k,v in marks.items()},identity);self.assertEqual(actual['checks'],original['checks']);self.assertEqual(actual['metrics']['effective_n'],repr(original['effective_n']))
  s,c,st=fixture();f=frame(s,c,st);a=action(s,st,f,'EXPLICIT_BUY',aid='same');r=run(s,c,st,f,a);st=r['next_state'];f=frame(s,c,st);a=action(s,st,f,aid='same')
  with self.assertRaisesRegex(ValueError,'Duplicate action'):run(s,c,st,f,a)
  a=action(s,st,f);a['source_references']['decision_prices']['available_at_utc']=f['session_open_at_utc']
  with self.assertRaisesRegex(ValueError,'future'):run(s,c,st,f,a)

 def test_04_resigned_genesis_cannot_preconsume_history(self):
  outcomes=[]
  for key,value in (('applied_event_ids',['ghost_event']),('applied_action_ids',['ghost_action']),('cumulative_twr',dict(numerator='1',denominator='2'))):
   s,c,st=fixture();st[key]=value;sign(st);f=frame(s,c,st);a=action(s,st,f)
   try:r=run(s,c,st,f,a);outcomes.append(dict(field=key,accepted=True,status=r['status']))
   except ValueError as exc:outcomes.append(dict(field=key,accepted=False,message=str(exc)))
  OBS['coordinated_genesis_attack']=outcomes
  self.assertTrue(all(not x['accepted'] for x in outcomes),'Impossible re-signed genesis consumed IDs/nonzero cumulative history accepted')

 def test_05_stale_split_ignores_unexecuted_buy_quantity_cap(self):
  s,c,st=fixture(quantities=dict(A=5*10**11,B=1,C=1,D=1,E=1));f=frame(s,c,st);f['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='split',session=f['session'],security_id='A',new_shares=2,old_shares=1)];f['open_prices_usd']['A']=f['close_prices_usd']['A']='5';a=action(s,st,f,'EXPLICIT_BUY');a['buy_shares']={'A':1}
  try:r=run(s,c,st,f,a);OBS['stale_cap_attack']=dict(status=r['action_disposition'],nextA=r['next_state']['holdings_by_sid']['A']);self.assertEqual(r['action_disposition'],'REJECTED_STALE_CORPORATE_ACTION');self.assertEqual(r['next_state']['holdings_by_sid']['A'],10**12)
  except ValueError as exc:OBS['stale_cap_attack']=dict(rejected_error=str(exc));self.fail('Complete supported stale action should zero buys, but rejected for hypothetical ignored buys: '+str(exc))
