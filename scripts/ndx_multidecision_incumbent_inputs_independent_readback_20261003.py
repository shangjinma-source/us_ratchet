"""Independent original-eight input projection and source binding. No engines."""
from pathlib import Path
from copy import deepcopy
from datetime import date
from fractions import Fraction
from urllib.parse import urlsplit
import hashlib,json,math,os,re,shutil,traceback,types
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/multidecision_incumbent_inputs_20261003_v1'
OUTPUT=ROOT/'data/cache/research/multidecision_incumbent_inputs_independent_readback_20261003_v1'
PRODUCER=ROOT/'scripts/ndx_multidecision_incumbent_inputs_20261003.py';PRODUCER_SHA='c6400e6bf2bce204ac472e09b7175387cb273f9832c5544d14fb8d36f0d7ec45'
CORE=ROOT/'backtest/ndx_multidecision_incumbent_inputs_research.py';CORE_SHA='c4a95ee8ecc61e9c8f803e0e1c72c3621bb587e4758b723722b279b1e8506a71'
INPUTS_SHA='9705b1ed2e42351050a5e413dcbe73fdc5d42efc16a03a79b560fe0c69f68aa4';PUBLICATION_SHA='5b8da9d3440422ec8899d5ad73abf589ea43a1869aa4aa84b6227ce480958fe9'
ENGINE=dict(path='backtest/ndx_incumbent_flow_split_control_research.py',sha256='5e963ddcf321de8b9b607dab11fe36e570050399b68125fdd02f12f671dfdeb3',function='simulate_incumbent_flow_split_control')
TICKERS=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
MODES=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'];LANES=['RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE']
FLAGS=('source_bytes_authenticated','account_simulation_performed','fit_performed','weights_normalized','weights_reoptimized','candidate_inventory_extended','cross_lane_execution_reused','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed','corporate_action_completeness_verified','future_independent_oos')
PFLAGS=('source_bytes_authenticated','account_simulation_performed','fit_performed','selection_performed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed','weights_normalized','cross_lane_execution_reused')
LINEAGE=ROOT/'backtest/ndx_history_failed_lineage_guard_20261008.py';LINEAGE_SHA='fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
BOUND={
 'original_inputs':('data/cache/research/original_eight_long_window_channels_20261003_v1/channels.json','67d433ae92acb0755a1ffdabf090e6c20706b4d1ba893637673e96a047acc372'),
 'original_publication':('data/cache/research/original_eight_long_window_channels_20261003_v1/publication.json','836622bff616370375539490c441fbb5b988d5dab8b661b202991288bcbf05e1'),
 'original_readback':('DYNAMIC_ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_20261003.json','182e901ad1554292444142c51ace220da2f1912b361d048d78b499d5aeaeb988'),
 'original_reader':('scripts/ndx_original_eight_long_window_independent_review_20261003.py','738e876b8e03cc2d2892a34b2c254c4ea8cc91e191e03acca55d15110b4bd469'),
 'candidate_inputs':('data/cache/research/multidecision_account_inputs_20261003_v1/inputs.json','c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9'),
 'candidate_publication':('data/cache/research/multidecision_account_inputs_20261003_v1/publication.json','64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940'),
 'candidate_readback':('data/cache/research/multidecision_account_inputs_independent_readback_20261003_v1/independent_readback.json','8568bbe2ea6fa33d2aa9956a72a8b11d902f353b6078044a9a832384ec0886fb'),
 'candidate_reader':('scripts/ndx_multidecision_account_inputs_independent_readback_20261003.py','85f3fd668a948bf9b3e68f1d4c013ee6def02d806f57373c41ef65698443576d')}

def require(x,m):
 if not x:raise ValueError(m)

def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()

def sha(b):return hashlib.sha256(b).hexdigest()

def reference(p,h):return dict(path=str(Path(p).resolve()),sha256=h)

def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and Path(r['path']).is_absolute() and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Absolute immutable source reference')

def merge(s,r):
 valid(r);require(r['path'] not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']

def claims(s,o):
 for p,h in o.get('source_hashes',{}).items():merge(s,dict(path=p,sha256=h))

def decode(b):
 def pairs(items):
  d={}
  for k,v in items:require(k not in d,'Duplicate JSON key');d[k]=v
  return d
 return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda x:(_ for _ in ()).throw(ValueError(x)))

def load(r,s,body=True):
 valid(r);p=Path(r['path']);require(not (p.parent/'failure.json').exists(),'Failed parent namespace');b=p.read_bytes();require(sha(b)==r['sha256'],'Consumed source SHA mismatch');merge(s,r);return decode(b) if body else b

def hashfile(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024**2),b''):h.update(b)
 return h.hexdigest()

def inventory(root,names):require({p.name for p in root.iterdir()}==set(names),'Parent or output namespace inventory drift')

def resource(n=0):
 p=OUTPUT.parent
 while not p.exists():p=p.parent
 require(shutil.disk_usage(p).free>=5*1024**3+n,'Resource reserve')

def save(name,value,emergency=False):
 b=enc(value)
 if not emergency:resource(len(b))
 p=OUTPUT/name
 with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
 require(p.read_bytes()==b,'Saved output bytes drift');return reference(p,sha(b))

ORIGINAL_FLAGS=('http_performed', 'fit_performed', 'account_simulation_performed', 'old_producer_called', 'old_audit_repeated', 'seven_reused_channels_recomputed', 'weights_normalized', 'weights_reoptimized', 'holdings_or_quotes_converted', 'identity_interval_extended', 'historical_identity_verified', 'historical_risk_verified', 'complete_corporate_actions_verified', 'provider_binding_verified', 'point_in_time_verified', 'legal_training_input_admitted', 'execution_authorized', 'promotion_allowed', 'formal_benchmark_evaluation_performed', 'full_transitive_source_closure_reverified', 'benchmark_qualified', 'fx_equivalence_verified', 'nav_publication_verified', 'future_independent_oos', 'untouched_holdout')

def exact(a,b,m):require(enc(a)==enc(b),m)
def false(o,keys):
 for k in keys:require(o[k] is False,'False authority '+k)
def lineage_members(sources):
 raw=LINEAGE.read_bytes();require(sha(raw)==LINEAGE_SHA,'Fixed diagnostic helper bytes')
 module=types.ModuleType('_fixed_history_failed_lineage');module.__file__=str(LINEAGE)
 exec(compile(raw,str(LINEAGE),'exec'),module.__dict__)
 return module.diagnostic_members(sources)

def guard(s,parents):
 require(hashfile(SOURCE)==LOADED,'Reader drift')
 diagnostic=lineage_members(s)
 for p,h in s.items():require((p in diagnostic or not (Path(p).parent/'failure.json').exists()) and hashfile(p)==h,'Source drift/failure')
 for p,names in parents.items():inventory(Path(p),names)
def inspect_inputs(*,saved,candidate,original,candidate_refs,original_refs):
 """Exact projection checks use nominal rationals, never adjusted scoring returns."""
 c=candidate['document']['inputs'];o=original['document'];ca=candidate['readback'];oa=original['readback'];pub=candidate['publication'];op=original['publication']
 require(saved['schema']=='MULTIDECISION_ORIGINAL_EIGHT_CONTROL_INPUTS_V1','Saved input schema');false(saved,FLAGS);require(saved['content_sha256']==sha(enc({k:v for k,v in saved.items() if k!='content_sha256'})),'Input digest')
 require(candidate['document']['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1','Candidate document role');false(c,('point_in_time_verified','execution_authorized','promotion_allowed','account_simulation_performed'));exact([c[k] for k in ('coordinate_count','lane_count','track_count')],[48,8,16],'Complete candidate input domain')
 require(c['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1' and len(c['rows'])==8 and len(saved['rows'])==8,'Eight complete lanes');exact([saved[k] for k in ('coordinate_count','lane_count','track_count')],[48,8,16],'Exact domains')
 require(c['content_sha256']==sha(enc({k:v for k,v in c.items() if k!='content_sha256'})),'Candidate saved content')
 for item in (candidate['document'],pub):false(item,PFLAGS[:9])
 require(pub['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1' and pub['status']=='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS','Candidate publication role');exact(pub['inputs_reference'],candidate_refs['inputs'],'Candidate publication link')
 require(ca['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1' and ca['status']=='PASS' and ca['reader_sha256']==candidate_refs['reader']['sha256'] and ca['scope']=='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION','Candidate audit scope');exact(ca['inputs_reference'],candidate_refs['inputs'],'Candidate audit input');exact(ca['publication_reference'],candidate_refs['publication'],'Candidate audit pub')
 for k,v in dict(coordinate_count=48,lane_count=8,track_count=16,security_count=77,issuer_count=76,provenance_count=101,sidecar_count=7).items():require(type(ca['inspection'][k])is int and ca['inspection'][k]==v,'Candidate inspected domain')
 false(ca,('producer_called','account_engine_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed'))
 require(o['schema']=='ORIGINAL_EIGHT_LONG_WINDOW_CONDITIONAL_CHANNELS_V1' and op['schema']=='ORIGINAL_EIGHT_LONG_WINDOW_CHANNELS_PUBLICATION_V1' and op['status']=='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_TSM_READBACK','Original source roles')
 for obj in (o,op):false(obj,ORIGINAL_FLAGS)
 exact(op['channels_reference'],original_refs['inputs'],'Original publication');require(oa['schema']=='ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_V1' and oa['status']=='PASS' and oa['channels_sha256']==original_refs['inputs']['sha256'] and oa['publication_sha256']==original_refs['publication']['sha256'] and oa['reader_sha256']==original_refs['reader']['sha256'],'Original audit links')
 false(oa,('reused_channels_recomputed','untouched_holdout','point_in_time_verified','benchmark_qualified','fit_performed','account_simulation_performed'))
 for k,v in dict(original_provenance_count=101,preserved_sidecar_count=7,price_rows=253,open_close_values=506,returns=252,training_returns=126,evaluation_returns=126).items():require(type(oa[k])is int and oa[k]==v,'Original independent dimensions')
 require(oa['new_raw_ticker']=='TSM','TSM role');exact(oa['reused_tickers'],[t for t in TICKERS if t!='TSM'],'Original seven roles')
 exact(o['original_control_order'],TICKERS,'Original disclosed order')
 sec=o['original_control_preserved']['securities'];require(len(sec)==len(o['rows'])==8 and len({s['security_id'] for s in sec})==len({s['issuer_id'] for s in sec})==8,'Original eight identities');exact([s['ticker'] for s in sec],TICKERS,'Exact original order');exact(o['original_control_preserved']['complete_original_definition']['securities'],sec,'Original definition')
 weights=[s['target_weight'] for s in sec];require(all(type(v)in(int,float) and math.isfinite(v) and v>0 for v in weights) and math.isfinite(sum(weights)) and abs(sum(weights)-1)<=1e-12,'No normalization, positive original weights')
 exact(saved['original_control_preserved'],o['original_control_preserved'],'Full original definition');exact(saved['original_candidate_provenance'],o['original_candidate_provenance'],'101 original evidence');exact(saved['preserved_candidate_evidence_sidecars'],o['preserved_candidate_evidence_sidecars'],'Seven original sidecars');require(len(saved['original_candidate_provenance'])==101 and len(saved['preserved_candidate_evidence_sidecars'])==7,'Full provenance domain')
 exact(saved['candidate_evidence_references'],candidate_refs,'Candidate roles');exact(saved['original_eight_evidence_references'],original_refs,'Original roles');require(saved['nav_role']=='EXTERNAL_NAV_REFERENCE_NOT_A_SUBSCRIPTION_ACCOUNT' and saved['control_deduplication_performed'] is False,'No implicit accounts or reuse')
 cal=o['calendar253'];require(len(cal)==253 and cal==sorted(set(cal)),'Original calendar')
 for d in cal:require(type(d)is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5,'Canonical source day')
 clock=c['execution_clock_from_saved_calendar'];exact([r['decision_date'] for r in clock],CUTOFFS,'Six decisions')
 for r in clock:require(r['decision_date'] in cal[:-1] and r['execution_date']==cal[cal.index(r['decision_date'])+1],'Next original observed session')
 end=c['execution_contract_preserved']['valuation_end_date'];require(end in cal,'Covered end');days=[d for d in cal if CUTOFFS[0]<=d<=end];params=c['execution_contract_preserved']['parameters'];require(params['initial_cash_usd']==25000 and params['minimum_cash_buffer_usd']==100 and params['transaction_cost_bps']==10,'Original execution parameters')
 expected_sources={}
 def add(r):
  require(type(r)is dict and set(r)=={'path','sha256'},'Declared role reference');require(r['path'] not in expected_sources or expected_sources[r['path']]==r['sha256'],'Conflicting source role');expected_sources[r['path']]=r['sha256']
 for rs in (candidate_refs,original_refs):
  for r in rs.values():add(r)
 columns=['CONTROL_SID_COLUMN_'+str(i).zfill(4) for i in range(8)];mapping={s['security_id']:columns[i] for i,s in enumerate(sec)};targets={s['security_id']:dict(ticker=mapping[s['security_id']],issuer_id=s['issuer_id'],target_weight=s['target_weight']) for s in sec};chains={s['security_id']:s['risk_chain'] for s in sec};quotes={};conversions=[];actions=[];gaps=[];slots=[]
 for i,(s,row) in enumerate(zip(sec,o['rows'])):
  sid=s['security_id'];exact(row['original_control_security'],s,'Original identity');ch=row['channel'];meta=row['complete_benchmark_metadata'];exact(meta['complete_original_control_security'],s,'Original role metadata');require(meta['shares_or_prices_converted'] is False and ch['ticker']==s['ticker'],'No conversion/alias')
  if s['ticker']=='TSM':require(row['mode']=='ONE_NEW_TSM_RAW_RECONSTRUCTION' and meta['control_only_overlay'] is True and row['complete_parent_row'] is None,'TSM control-only independent source')
  else:require(row['mode']=='EXACT_SEALED_CHANNEL_REUSE_NO_ARITHMETIC','Seven reused sources')
  for key in ('raw_reference','receipt_reference'):exact(ch[key],meta[key],'Nominal raw receipt');add(ch[key])
  slots.append(dict(security_id=sid,original_row_preserved=row,source_reference=dict(original_refs['inputs'],json_pointer=f'/rows/{i}'),candidate_universe_member_claimed=False if s['ticker']=='TSM' else None));quotes[sid]={}
  if ch['status']!='CONDITIONAL_NUMERIC_RESULT':gaps.append(dict(security_id=sid,reason='BLOCKED_ORIGINAL_NOMINAL_CHANNEL',original_reasons=ch['reasons']));continue
  require(ch['quote_rows_sha256']==sha(enc(ch['quote_rows'])),'Original nominal rows digest');exact(ch['calendar'],cal,'253 calendar');by={r['session']:(j,r) for j,r in enumerate(ch['quote_rows'])};require(len(by)==len(ch['quote_rows']),'Unique nominal sessions')
  for day in days:
   if day not in by:gaps.append(dict(security_id=sid,session=day,reason='MISSING_ORIGINAL_NOMINAL_QUOTE'));continue
   j,r=by[day];pair=[]
   for field in ('nominal_open_exact','nominal_close_exact'):
    raw=r.get(field)
    if raw is None:gaps.append(dict(security_id=sid,session=day,field=field,reason='MISSING_ORIGINAL_NOMINAL_FIELD'));pair.append(None);continue
    require(type(raw)is str,'Original rational text');fraction=Fraction(raw);value=float(fraction);require(fraction>0 and math.isfinite(value) and value>0,'Finite positive nominal');pair.append(value);conversions.append(dict(security_id=sid,session=day,field=field,exact=raw,binary64_hex=value.hex(),json_pointer=f'/rows/{i}/channel/quote_rows/{j}/{field}'))
   quotes[sid][day]=pair
  for event in ch['event_policies']:
   if CUTOFFS[0]<=event['session']<=end:
    require(event['kind']=='ORDINARY_SPLIT' and type(event['numerator'])is int and type(event['denominator'])is int and event['numerator']>0 and event['denominator']>0 and event['numerator']!=event['denominator'] and event['session'] in days,'Explicit in-calendar split');require(not any(a['security_id']==sid and a['session']==event['session'] for a in actions),'Unique split')
    receipt=ch['receipt_preserved'];exact([receipt['raw_path'],receipt['raw_sha256'],receipt['ticker']],[ch['raw_reference']['path'],ch['raw_reference']['sha256'],s['ticker']],'Saved event receipt');url=receipt['request_url'];u=urlsplit(url);require(u.scheme=='https' and u.hostname and not u.username and not u.password and not any(x.isspace() for x in url),'Original public locator');actions.append(dict(security_id=sid,session=event['session'],new_shares=event['numerator'],old_shares=event['denominator'],source_url=url,evidence_sha256=ch['raw_reference']['sha256']))
 exact(saved['source_slots'],slots,'Full source identity/actions/gaps evidence');exact(saved['exact_quote_conversion_evidence'],conversions,'Exact nominal to binary64 mapping')
 opens=dict(index=days,columns=columns,data=[[quotes[s['security_id']].get(d,[None,None])[0] for s in sec] for d in days]);closes=dict(index=days,columns=columns,data=[[quotes[s['security_id']].get(d,[None,None])[1] for s in sec] for d in days]);schedule=[dict(r,targets=targets) for r in clock];risk={r['decision_date']:chains for r in clock}
 for li,(actual,lane) in enumerate(zip(saved['rows'],c['rows'])):
  false(actual,FLAGS);exact([actual['fx_mode'],actual['lane']],[MODES[li//4],LANES[li%4]],'Original lane position');exact([lane['fx_mode'],lane['lane']],[actual['fx_mode'],actual['lane']],'Candidate matched lane');expected_indices=[li+d*8 for d in range(6)];exact(actual['coordinate_indexes'],expected_indices,'Full48 mapping');exact(lane['coordinate_indexes'],expected_indices,'Candidate48 mapping');exact(actual['original_target_weights_preserved'],weights,'Original weights unmodified');require(actual['risk_is_order_gate'] is False and len(actual['tracks'])==len(lane['tracks'])==2,'Two control tracks no risk gating')
  for ti,(tr,ct) in enumerate(zip(actual['tracks'],lane['tracks'])):
   false(tr,FLAGS);kind=['CONTINUOUS','WHOLE_LOT'][ti];require(tr['track']==ct['track']==kind,'Track matching');state=ct['stateful_input'];exact(state['calendar'],days,'Same entire calendar');exact(state['parameters'],params,'Same parameters');flow=state['external_flows'];exact(flow,lane['tracks'][0]['stateful_input']['external_flows'],'Same lane flow both tracks');seen=set()
   for f in flow:
    require(set(f)=={'session','amount_usd','currency','timing','source_reference'} and f['session'] in days and f['currency']=='USD' and f['timing']=='BEFORE_OPEN' and type(f['amount_usd'])in(int,float) and math.isfinite(f['amount_usd']) and f['amount_usd']>=0,'Original explicit USD flow');key=(f['session'],f['source_reference']['path'],f['source_reference']['sha256']);require(key not in seen,'Duplicate flow');seen.add(key);add(f['source_reference'])
   blocked=deepcopy(gaps)
   if any(f['session']==days[0] for f in flow):blocked.append(dict(reason='FLOW_BEFORE_INITIAL_DECISION_CLOSE_REQUIRES_EXPLICIT_INITIAL_CAPITAL_CONTRACT'))
   if kind=='CONTINUOUS' and any(a['session']==days[0] for a in actions):blocked.append(dict(reason='SPLIT_AT_INITIAL_CLOSE_OUTSIDE_FRACTIONAL_OPEN_ACTION_INTERVAL'))
   exact(tr['blocking_reasons'],blocked,'Original missing values remain blocked');require(tr['status']==('BLOCKED_ORIGINAL_CONTROL_INPUT' if blocked else 'CONTROL_INPUTS_PREPARED_NOT_EXECUTED'),'Control readiness');exact(tr['candidate_status_preserved'],ct['status'],'No candidate cash invention');exact(tr['candidate_blocking_reasons_preserved'],ct['blocking_reasons'],'Candidate missing chain');exact(tr['candidate_input_reference'],dict(candidate_refs['inputs'],json_pointer=f'/inputs/rows/{li}/tracks/{ti}'),'Mapped candidate pointer')
   kwargs=dict(track=kind,closes=closes,opens=opens,schedule=schedule,risk_chains_by_decision=risk,corporate_actions=actions,external_flows=flow,valuation_end_date=end,**params);exact(tr['engine_binding'],dict(source_reference={k:ENGINE[k] for k in ('path','sha256')},function=ENGINE['function'],keyword_arguments=kwargs,dataframe_restoration_required=['closes','opens']),'Complete control signature and own full-path input');exact(tr['own_initial_state'],dict(cash_usd=25000,shares={}),'Own initial state');require(tr['execution_reused'] is False,'No unregistered deduplication')
 add({k:ENGINE[k] for k in ('path','sha256')});exact(saved['source_hashes'],expected_sources,'Complete pure source roles')
 return dict(status='PASS',coordinate_count=48,lane_count=8,track_count=16,control_security_count=8,nominal_conversion_count=len(conversions),original_provenance_count=101,preserved_sidecar_count=7,producer_called=False,control_engine_called=False,candidate_engine_called=False,source_bytes_authenticated=False)

def load_inputs():
 require(all(type(h)is str and re.fullmatch('[a-f0-9]{64}',h) for h in [INPUTS_SHA,PUBLICATION_SHA,PRODUCER_SHA,CORE_SHA]+[h for p,h in BOUND.values()]),'Future bindings pending before IO')
 sources={str(SOURCE):LOADED};expected={str(PRODUCER):PRODUCER_SHA,str(LINEAGE):LINEAGE_SHA};load(reference(PRODUCER,PRODUCER_SHA),sources,False);load(reference(CORE,CORE_SHA),expected,False);docs={};refs={k:reference(ROOT/p,h) for k,(p,h) in BOUND.items()};parents={}
 for k,r in refs.items():
  value=load(r,expected,not k.endswith('_reader'))
  if type(value)is dict:docs[k]=value;claims(expected,value)
 for prefix,filename in [('original','channels.json'),('candidate','inputs.json')]:
  directory=Path(refs[prefix+'_inputs']['path']).parent;parents[str(directory)]=['started.json',filename,'publication.json'];inventory(directory,parents[str(directory)]);p=directory/'started.json';b=p.read_bytes();merge(expected,reference(p,sha(b)))
  exact(docs[prefix+'_inputs']['source_hashes'],docs[prefix+'_publication']['source_hashes'],'Upstream published source claims')
 for row in docs['original_inputs']['rows']:
  for role in ('raw_reference','receipt_reference'):load(row['channel'][role],expected,False)
 load(reference(ROOT/ENGINE['path'],ENGINE['sha256']),expected,False)
 ir=reference(PARENT/'inputs.json',INPUTS_SHA);pr=reference(PARENT/'publication.json',PUBLICATION_SHA);doc=load(ir,sources);pub=load(pr,sources);sr=pub['started_reference'];require(Path(sr['path'])==PARENT/'started.json','Fixed producer started');started=load(sr,sources)
 require(doc['schema']=='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_DOCUMENT_V1' and doc['independent_readback_status']=='PENDING' and doc['parent_started_dispatch_authority_verified'] is False,'Original input document scope');require(pub['schema']=='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_PUBLICATION_V1' and pub['status']=='PUBLISHED_CONTROL_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS','Original input publication role');require(started['schema']=='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_STARTED_V1','Original input started role');exact(pub['inputs_reference'],ir,'Externally pinned input bytes')
 for obj in (doc,pub,started):false(obj,PFLAGS);exact(obj['source_hashes'],expected,'Independent complete producer closure');exact(obj['input_references'],refs,'Eight fixed source roles')
 for p,h in expected.items():merge(sources,dict(path=p,sha256=h))
 parents[str(PARENT)]=['started.json','inputs.json','publication.json'];guard(sources,parents)
 def envelope(prefix):return dict(document=docs[prefix+'_inputs'],publication=docs[prefix+'_publication'],readback=docs[prefix+'_readback'])
 args=dict(saved=doc['inputs'],candidate=envelope('candidate'),original=envelope('original'),candidate_refs={r:refs['candidate_'+r] for r in ('inputs','publication','readback','reader')},original_refs={r:refs['original_'+r] for r in ('inputs','publication','readback','reader')})
 return dict(args=args,sources=sources,parent_inventories=parents,inputs_reference=ir,publication_reference=pr)

def readback(*,execute=False):
 require(execute is True,'Explicit independent readback');c=load_inputs();require(not OUTPUT.exists(),'Create only no retry');resource();OUTPUT.mkdir(parents=True);written=[]
 try:
  written.append(save('started.json',dict(schema='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_READBACK_STARTED_V1',inputs_reference=c['inputs_reference'],publication_reference=c['publication_reference'],source_hashes=c['sources'])))
  result=inspect_inputs(**c['args']);guard(c['sources'],c['parent_inventories'])
  report=dict(schema='MULTIDECISION_ORIGINAL_EIGHT_INPUTS_INDEPENDENT_READBACK_V1',status='PASS',inputs_reference=c['inputs_reference'],publication_reference=c['publication_reference'],reader_sha256=LOADED,source_hashes=c['sources'],inspection=result,scope='SAVED_NOMINAL_ORIGINAL_EIGHT_16_CONTROL_INPUT_PROJECTIONS_NOT_ACCOUNTS',producer_called=False,control_engine_called=False,candidate_engine_called=False,fit_called=False,point_in_time_verified=False,formal_benchmark_passed=False,execution_authorized=False,promotion_allowed=False,parent_started_dispatch_authority_verified=False)
  rr=save('independent_readback.json',report);written.append(rr);guard(c['sources'],c['parent_inventories']);inventory(OUTPUT,['started.json','independent_readback.json'])
  for r in written:require(hashfile(r['path'])==r['sha256'],'Final reader output drift')
  return rr
 except BaseException as e:
  if not (OUTPUT/'failure.json').exists():save('failure.json',dict(status='FAILED_NO_RETRY',saved_references=written,error=dict(type=type(e).__name__,message=str(e),traceback=traceback.format_exc()),producer_called=False,account_simulation_performed=False),True)
  raise

if __name__=='__main__':
 import argparse
 p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
