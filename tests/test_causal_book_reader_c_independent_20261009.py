"""New independent synthetic saved-path cases; no real book/source IO."""
from pathlib import Path
from copy import deepcopy
from datetime import date,timedelta
from fractions import Fraction as F
from unittest.mock import patch
import ast,hashlib,importlib.util,json,math,sys,unittest
ROOT=Path(__file__).resolve().parents[1]
def load(p,name):
 sp=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
PATH=ROOT/'backtest/ndx_causal_book_independent_reconstruction_v1.py'
assert hashlib.sha256(PATH.read_bytes()).hexdigest()=='2bb14a3e0318182f9f6f105a5039d3cb0b56be608167faaf20a09ca2131e4eab'
r=load(PATH,'c_reader');f=load(ROOT/'tests/test_ndx_causal_book_v2_c_independent_20261009.py','c_own_fixture');p=f.m
OBS={}
def build(n=4,count=5,nontrivial=True,stop=None,cash='100'):
 s,c,st=f.fixture(cash=cash,flows=(20,0,30,5) if nontrivial else ())
 days=[(date(2026,10,5)+timedelta(days=i)).isoformat() for i in range(max(n,1)+1)]
 s['calendar']=[dict(session=d,open_at_utc=d+'T13:30:00Z',close_at_utc=d+'T20:00:00Z') for d in days]
 quantities=dict.fromkeys('ABCDE',1) if count==5 else {f'S{i}':1 for i in range(count)}
 initial=dict(session=days[0],close_at_utc=days[0]+'T20:00:00Z',holdings_by_sid=quantities,cash_usd=cash);marks=dict.fromkeys(quantities,'10')
 if stop=='bootstrap':c['numeric_coverage']['prices']='MISSING'
 boot=p.bootstrap_research_book(scenario=s,initial_state=initial,initial_marks=marks,source_context=c);st=boot['next_state'];frames=[];actions=[];saved=[];timeline=[]
 for i in range(n if st is not None else 0):
  op,cl=(('12','11'),('9','10'),('11','8'),('10','13'))[i] if nontrivial else ('10','10');fr=f.frame(s,c,st,op,cl);ac=f.action(s,st,fr)
  if stop=='pending':ac=dict(schema='EXPLICIT_RESEARCH_ACTION_V1',status='PENDING_ACTION_POLICY',reason='NO_POLICY',decision_session=st['session'],execution_session=fr['session'])
  if stop=='critical':fr['source_context']['numeric_coverage']['corporate_events']='MISSING'
  result=f.run(s,c,st,fr,ac);frames.append(fr);actions.append(ac);saved.append(result)
  if result['next_state'] is None:break
  timeline.append(dict(sequence=i+1,session=fr['session'],previous_close_session=st['session'],previous_state_sha256=st['content_sha256'],state_sha256=result['next_state']['content_sha256'],book_lineage_id=s['book_lineage_id'],scenario_content_sha256=f.H(s),session_twr=result['valuation_row']['session_twr'],status='COMPUTED'));st=result['next_state']
 pairs=[(1,2),(1,3),(1,4),(1,5),(2,3),(2,4),(2,5),(3,4),(3,5),(4,5),(1,2),(2,4),(1,5)] if n==4 else [(1,len(days))]*13
 windows=[dict(window_id='c'+str(i),fit_end=days[a-1],evaluation_start=days[a],evaluation_end_inclusive=days[b-1]) for i,(a,b) in enumerate(pairs)]
 mapping=dict(schema='ROLLING_BOOK_WINDOW_VIEW_MAPPING_V1',book_lineage_id=s['book_lineage_id'],scenario_content_sha256=f.H(s),calendar=days,terminal_boundary=dict(kind='AFTER_LAST_SAVED_MARK',ordinal=len(days)))
 views=p.map_rolling_windows_to_book_views(window_coordinates=windows,book_timeline=timeline,mapping_contract=mapping)
 return dict(scenario=s,initial_state=initial,initial_marks=marks,initial_source_context=c,frames=frames,explicit_actions=actions,saved_bootstrap=boot,saved_transitions=saved,window_coordinates=windows,mapping_contract=mapping,saved_views=views)
def inspect_no_producer(args):
 with patch.object(p,'bootstrap_research_book',side_effect=AssertionError('ProducerCall')),patch.object(p,'advance_research_book',side_effect=AssertionError('ProducerCall')),patch.object(p,'risk_snapshot',side_effect=AssertionError('ProducerCall')),patch.object(p,'map_rolling_windows_to_book_views',side_effect=AssertionError('ProducerCall')),patch('builtins.open',side_effect=AssertionError('SourceIO')),patch.object(Path,'read_bytes',side_effect=AssertionError('SourceIO')):
  return r.inspect_saved_book(**args)
def resign(v):v['content_sha256']=f.H({k:x for k,x in v.items() if k!='content_sha256'})
class Independent(unittest.TestCase):
 def test_01_fourframe_all13_no_producer_and_independent_money_risk(self):
  args=build();oracle=json.loads((ROOT/'tmp/causal_book_nontrivial_view_oracle_c_20261009_v1/ORACLE.json').read_bytes());original=deepcopy(args);report=inspect_no_producer(args);self.assertEqual(args,original)
  for saved,want in zip(report['transitions'],oracle['frames']):
   row=saved['valuation_row'];self.assertEqual(F(row['close_equity_usd']),f.fr(want['close_equity']));self.assertEqual(f.fr(row['session_twr'])+1,f.fr(want['session_factor']));risk=saved['risk_observations']['actual_close'];self.assertEqual(risk['checks'],dict(MAX_SINGLE_WEIGHT=True,MIN_SINGLE_WEIGHT=True,SECURITY_TOP3_WEIGHT=True,MINIMUM_EFFECTIVE_N=True,RISK_CHAIN_TOP1_WEIGHT=True));self.assertEqual(F(risk['metrics']['effective_n']),5)
  for got,want in zip(report['views']['rows'],oracle['views']):self.assertEqual(got['view_twr'],want['correct_twr']);self.assertEqual([x['sequence'] for x in got['frame_references']],want['included_frame_indices'])
  self.assertTrue(all(v is False for v in report['authority'].values()));report['transitions'].clear();self.assertEqual(args,original)
  tree=ast.parse(PATH.read_bytes());imports=[n for n in ast.walk(tree) if isinstance(n,(ast.Import,ast.ImportFrom))];self.assertTrue(all(not (isinstance(n,ast.ImportFrom) and (n.module or '').startswith('backtest')) for n in imports))
 def test_02_coordinated_saved_tampering_whole_result(self):
  baseline=build();inspect_no_producer(baseline)
  mutations=[lambda t:t['valuation_row'].__setitem__('cash_after_usd','999'),lambda t:t['valuation_row'].__setitem__('fees_usd','1'),lambda t:t['valuation_row']['holdings_after'].__setitem__('A',2),lambda t:t['valuation_row'].__setitem__('session_twr',dict(numerator='1',denominator='3')),lambda t:t['next_state']['applied_action_ids'].append('ghost'),lambda t:t['risk_observations']['actual_close']['checks'].__setitem__('MAX_SINGLE_WEIGHT',False),lambda t:t['next_state']['authority'].__setitem__('future_oos',0)]
  for mutate in mutations:
   args=deepcopy(baseline);t=args['saved_transitions'][0];mutate(t);resign(t['next_state']);resign(t)
   # Also re-sign all descendant saved states/results and view digest. No digest-only pass.
   for later in args['saved_transitions'][1:]:resign(later['next_state']);resign(later)
   resign(args['saved_views'])
   with self.assertRaisesRegex(ValueError,'Complete transition'):inspect_no_producer(args)
  args=deepcopy(baseline);args['saved_views']['rows'][0]['stop_index']=3;resign(args['saved_views'])
  with self.assertRaisesRegex(ValueError,'thirteen-view'):inspect_no_producer(args)
  args=deepcopy(baseline);args['frames'][1]['previous_state_sha256']='0'*64
  with self.assertRaisesRegex(ValueError,'lineage'):inspect_no_producer(args)
  OBS['tamper_cases']=9
 def test_03_blocked_pending_bootstrap_empty_and_no_later_advance(self):
  for stop in ('pending','critical','bootstrap'):
   args=build(stop=stop);report=inspect_no_producer(args);self.assertEqual(report['numeric_status'],'BLOCKED');self.assertTrue(all(x['view_twr'] is None for x in report['views']['rows']))
   if args['saved_transitions']:
    bad=deepcopy(args);bad['frames']*=2;bad['explicit_actions']*=2;bad['saved_transitions']*=2
    with self.assertRaisesRegex(ValueError,'Uncommitted'):inspect_no_producer(bad)
  args=build(n=0,nontrivial=False);self.assertEqual(inspect_no_producer(args)['transition_count'],0)
 def test_04_maxsplit_stale_and_derived_open_not_capped(self):
  # Construct new one-frame paths via our own prior fixture; source money bounds apply to source prices/state, not derived Open values.
  def one(quantities,op,cl,split=False):
   args=build(n=1,nontrivial=False,cash='1000');args['initial_state']['holdings_by_sid']=quantities;args['initial_marks']=dict.fromkeys(quantities,'10');boot=p.bootstrap_research_book(scenario=args['scenario'],initial_state=args['initial_state'],initial_marks=args['initial_marks'],source_context=args['initial_source_context']);args['saved_bootstrap']=boot;st=boot['next_state'];fr=f.frame(args['scenario'],args['initial_source_context'],st,op,cl)
   if split:fr['corporate_events']=[dict(schema='INTEGER_SPLIT_EVENT_V1',event_id='split',session=fr['session'],security_id='A',new_shares=2,old_shares=1)];fr['open_prices_usd']['A']=fr['close_prices_usd']['A']='5'
   ac=f.action(args['scenario'],st,fr,'EXPLICIT_BUY' if split else 'EXPLICIT_NO_TRADE');result=f.run(args['scenario'],args['initial_source_context'],st,fr,ac);args['frames']=[fr];args['explicit_actions']=[ac];args['saved_transitions']=[result];timeline=[dict(sequence=1,session=fr['session'],previous_close_session=st['session'],previous_state_sha256=st['content_sha256'],state_sha256=result['next_state']['content_sha256'],book_lineage_id=args['scenario']['book_lineage_id'],scenario_content_sha256=f.H(args['scenario']),session_twr=result['valuation_row']['session_twr'],status='COMPUTED')];args['saved_views']=p.map_rolling_windows_to_book_views(window_coordinates=args['window_coordinates'],book_timeline=timeline,mapping_contract=args['mapping_contract']);return args
  args=one(dict(A=5*10**11,B=1,C=1,D=1,E=1),'10','10',True);out=inspect_no_producer(args)['transitions'][0];self.assertEqual(out['next_state']['holdings_by_sid']['A'],10**12);self.assertEqual(out['action_disposition'],'REJECTED_STALE_CORPORATE_ACTION');self.assertIsNone(out['risk_observations']['prospective_open']['all_passed'])
  args=one(dict.fromkeys('ABCDE',10**12),'1'+'0'*39,'1');out=inspect_no_producer(args)['transitions'][0];self.assertGreater(len(out['valuation_row']['pre_flow_open_equity_usd']),40);self.assertIsNotNone(out['next_state'])
 def test_05_per_document_limits_do_not_truncate_history(self):
  args=build(n=40,count=128,nontrivial=False,cash='1000')
  def nodes(x):return 1+sum(nodes(v) for v in x.values()) if isinstance(x,dict) else 1+sum(nodes(v) for v in x) if isinstance(x,list) else 1
  count=sum(nodes(x) for values in (args['frames'],args['explicit_actions'],args['saved_transitions']) for x in values);self.assertGreater(count,200000)
  report=inspect_no_producer(args);self.assertEqual(report['transition_count'],40);self.assertEqual(report['committed_transition_count'],40);self.assertEqual(report['window_count'],13);OBS['perdocument_scope']=dict(frames=40,SIDs=128,aggregate_nodes=count,scope='Each document valid; no 512-frame capacity claim')
