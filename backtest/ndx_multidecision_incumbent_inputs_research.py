"""Saved nominal original-eight controls aligned to all candidate coordinates.
No raw decoding, score returns, account execution, normalization or deduplication.
"""
from copy import deepcopy
from datetime import date
from fractions import Fraction
from urllib.parse import urlsplit
import hashlib,json,math,re
TICKERS=['NVDA','TXN','ASML','CDNS','TSM','MU','MSFT','GOOG']
CUTOFFS=['2026-03-31','2026-04-30','2026-05-29','2026-06-30','2026-07-31','2026-08-31']
PFLAGS=('source_bytes_authenticated','account_simulation_performed','fit_performed','selection_performed','execution_authorized','promotion_allowed','point_in_time_verified','formal_benchmark_passed','automatic_retry_allowed')
ORIGINAL_FLAGS=('http_performed', 'fit_performed', 'account_simulation_performed', 'old_producer_called', 'old_audit_repeated', 'seven_reused_channels_recomputed', 'weights_normalized', 'weights_reoptimized', 'holdings_or_quotes_converted', 'identity_interval_extended', 'historical_identity_verified', 'historical_risk_verified', 'complete_corporate_actions_verified', 'provider_binding_verified', 'point_in_time_verified', 'legal_training_input_admitted', 'execution_authorized', 'promotion_allowed', 'formal_benchmark_evaluation_performed', 'full_transitive_source_closure_reverified', 'benchmark_qualified', 'fx_equivalence_verified', 'nav_publication_verified', 'future_independent_oos', 'untouched_holdout')
MODES=['STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'];LANES=['RETURN','BAD_TAIL','DRAWDOWN','TARGET_ENVELOPE']
ENGINE=dict(path='backtest/ndx_incumbent_flow_split_control_research.py',sha256='5e963ddcf321de8b9b607dab11fe36e570050399b68125fdd02f12f671dfdeb3',function='simulate_incumbent_flow_split_control')
FLAGS=dict.fromkeys(('source_bytes_authenticated','account_simulation_performed','fit_performed','weights_normalized','weights_reoptimized','candidate_inventory_extended','cross_lane_execution_reused','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed','corporate_action_completeness_verified','future_independent_oos'),False)

def require(x,m):
 if not x:raise ValueError(m)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def digest(v):return hashlib.sha256(enc(v)).hexdigest()
def exact(a,b,m):require(enc(a)==enc(b),m)
def ref(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and r['path'] and type(r['sha256'])is str and re.fullmatch('[a-f0-9]{64}',r['sha256']),'Explicit source reference')
def dates(v):
 require(type(v)is list and v and v==sorted(set(v)),'Whole observed calendar')
 for d in v:require(type(d)is str and date.fromisoformat(d).isoformat()==d and date.fromisoformat(d).weekday()<5,'Canonical observed session')

def prepare_incumbent_account_inputs(*,candidate_evidence,original_eight_evidence):
 sources={}
 def add(r):ref(r);require(r['path'] not in sources or sources[r['path']]==r['sha256'],'Source conflict');sources[r['path']]=r['sha256']
 for env in (candidate_evidence,original_eight_evidence):
  require(set(env)=={'document','publication','readback','references'} and set(env['references'])=={'inputs','publication','readback','reader'},'Two complete saved source envelopes')
  for r in env['references'].values():add(r)
 ce=candidate_evidence;cr=ce['references'];doc=ce['document'];ca=ce['readback'];pub=ce['publication'];require(doc['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_DOCUMENT_V1','Candidate saved inputs');candidate=doc['inputs']
 require(candidate['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_V1' and ca['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_INDEPENDENT_READBACK_V1' and ca['status']=='PASS' and ca['reader_sha256']==cr['reader']['sha256'],'Specific candidate independent input audit')
 for obj in (doc,pub):
  for k in PFLAGS:require(obj[k] is False,'Candidate receipt authority '+k)
 require(pub['schema']=='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS_PUBLICATION_V1' and pub['status']=='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS','Candidate publication role')
 require(ca['scope']=='SAVED_FULL48_TO_16_STATEFUL_INPUT_PROJECTION_NOT_ACCOUNT_EXECUTION','Independent candidate scope')
 for k in ('producer_called','account_engine_called','fit_called','point_in_time_verified','formal_benchmark_passed','execution_authorized','promotion_allowed'):require(ca[k] is False,'Candidate audit authority')
 for k,v in dict(coordinate_count=48,lane_count=8,track_count=16,security_count=77,issuer_count=76,provenance_count=101,sidecar_count=7).items():require(type(ca['inspection'][k])is int and ca['inspection'][k]==v,'Complete candidate audit denominator')
 exact(ca['inputs_reference'],cr['inputs'],'Audited candidate inputs');exact(ca['publication_reference'],cr['publication'],'Audited candidate publication');exact(pub['inputs_reference'],cr['inputs'],'Candidate publication link')
 require(len(candidate['rows'])==8 and [candidate[k] for k in ('coordinate_count','lane_count','track_count')]==[48,8,16],'All candidate coordinates')
 for k in ('point_in_time_verified','execution_authorized','promotion_allowed','account_simulation_performed'):require(candidate[k] is False,'No candidate execution authority')
 require(candidate['content_sha256']==digest({k:v for k,v in candidate.items() if k!='content_sha256'}),'Saved candidate digest')
 oe=original_eight_evidence;o=oe['document'];oa=oe['readback'];orr=oe['references']
 require(o['schema']=='ORIGINAL_EIGHT_LONG_WINDOW_CONDITIONAL_CHANNELS_V1' and len(o['rows'])==8 and oa['schema']=='ORIGINAL_EIGHT_LONG_WINDOW_INDEPENDENT_READBACK_V1' and oa['status']=='PASS' and oa['channels_sha256']==orr['inputs']['sha256'] and oa['publication_sha256']==orr['publication']['sha256'] and oa['reader_sha256']==orr['reader']['sha256'],'Original nominal channels audit')
 for obj in (o,oe['publication']):
  for k in ORIGINAL_FLAGS:require(obj[k] is False,'Original source restriction '+k)
 require(oe['publication']['status']=='PUBLISHED_CONDITIONAL_NUMBERS_PENDING_NEW_TSM_READBACK','Original publication status')
 for k in ('reused_channels_recomputed','untouched_holdout','point_in_time_verified','benchmark_qualified','fit_performed','account_simulation_performed'):require(oa[k] is False,'Original limited audit restriction')
 for k,v in dict(original_provenance_count=101,preserved_sidecar_count=7,price_rows=253,open_close_values=506,returns=252,training_returns=126,evaluation_returns=126).items():require(type(oa[k])is int and oa[k]==v,'Original audit dimensions')
 require(oa['new_raw_ticker']=='TSM','Original distinct TSM audit');exact(oa['reused_tickers'],[t for t in TICKERS if t!='TSM'],'Seven reused source roles')
 require(oe['publication']['schema']=='ORIGINAL_EIGHT_LONG_WINDOW_CHANNELS_PUBLICATION_V1','Original publication role');exact(oe['publication']['channels_reference'],orr['inputs'],'Original publication relation')
 for k in ('weights_normalized','weights_reoptimized','holdings_or_quotes_converted','point_in_time_verified','execution_authorized','promotion_allowed','complete_corporate_actions_verified'):require(o[k] is False,'Original conditional limits')
 require(len(o['original_candidate_provenance'])==101 and len(o['preserved_candidate_evidence_sidecars'])==7,'Full original candidate evidence kept distinct')
 securities=o['original_control_preserved']['securities'];exact([s['ticker'] for s in securities],TICKERS,'Original8 definition order');exact(o['original_control_order'],TICKERS,'Original order');exact(o['original_control_preserved']['complete_original_definition']['securities'],securities,'Preserved original definition')
 require(len({s['security_id'] for s in securities})==len({s['issuer_id'] for s in securities})==8,'Eight original identities')
 weights=[s['target_weight'] for s in securities];require(all(type(w)in(int,float) and math.isfinite(w) and w>0 for w in weights) and math.isfinite(sum(weights)) and abs(sum(weights)-1)<=1e-12,'Original weights unchanged, no normalization')
 cal=o['calendar253'];dates(cal);require(len(cal)==253,'Full original nominal calendar')
 clock=candidate['execution_clock_from_saved_calendar'];require(len(clock)==6,'Six original decisions')
 exact([c['decision_date'] for c in clock],CUTOFFS,'Original six cutoff order')
 for c in clock:require(c['decision_date'] in cal[:-1] and c['execution_date']==cal[cal.index(c['decision_date'])+1],'Observed next Open clock')
 first=clock[0]['decision_date'];end=candidate['execution_contract_preserved']['valuation_end_date'];calendar=[d for d in cal if first<=d<=end];require(end in cal,'Complete covered end')
 params=candidate['execution_contract_preserved']['parameters'];require(params['initial_cash_usd']==25000 and params['minimum_cash_buffer_usd']==100 and params['transaction_cost_bps']==10,'Shared initial capital and fee contract')
 columns=['CONTROL_SID_COLUMN_'+str(i).zfill(4) for i in range(8)];mapping={s['security_id']:columns[i] for i,s in enumerate(securities)};targets={s['security_id']:dict(ticker=mapping[s['security_id']],issuer_id=s['issuer_id'],target_weight=s['target_weight']) for s in securities};chains={s['security_id']:s['risk_chain'] for s in securities};qmap={};sourceslots=[];conversion=[];actions=[];gaps=[]
 for i,(security,row) in enumerate(zip(securities,o['rows'])):
  exact(row['original_control_security'],security,'Original row identity');ch=row['channel'];require(ch['ticker']==security['ticker'],'Original channel ticker');sid=security['security_id'];meta=row['complete_benchmark_metadata'];exact(meta['complete_original_control_security'],security,'Full control evidence');require(meta['shares_or_prices_converted'] is False,'No ADR conversion')
  if security['ticker']=='TSM':require(row['mode']=='ONE_NEW_TSM_RAW_RECONSTRUCTION' and meta['control_only_overlay'] is True and row['complete_parent_row'] is None,'TSM separate control-only nominal source')
  else:require(row['mode']=='EXACT_SEALED_CHANNEL_REUSE_NO_ARITHMETIC','Seven exact saved nominal channels')
  for k in ('raw_reference','receipt_reference'):exact(ch[k],meta[k],'Raw receipt role');add(ch[k])
  sourceslots.append(dict(security_id=sid,original_row_preserved=deepcopy(row),source_reference=dict(orr['inputs'],json_pointer=f'/rows/{i}'),candidate_universe_member_claimed=False if security['ticker']=='TSM' else None))
  if ch['status']!='CONDITIONAL_NUMERIC_RESULT':gaps.append(dict(security_id=sid,reason='BLOCKED_ORIGINAL_NOMINAL_CHANNEL',original_reasons=deepcopy(ch['reasons'])));qmap[sid]={};continue
  require(ch['quote_rows_sha256']==digest(ch['quote_rows']),'Original quote checksum');exact(ch['calendar'],cal,'Shared253 original calendar');q={v['session']:(j,v) for j,v in enumerate(ch['quote_rows'])};require(len(q)==len(ch['quote_rows']),'Unique quote dates');qmap[sid]={}
  for d in calendar:
   if d not in q:gaps.append(dict(security_id=sid,session=d,reason='MISSING_ORIGINAL_NOMINAL_QUOTE'));continue
   qi,v=q[d];pair=[]
   for field in ('nominal_open_exact','nominal_close_exact'):
    if v.get(field) is None:gaps.append(dict(security_id=sid,session=d,field=field,reason='MISSING_ORIGINAL_NOMINAL_FIELD'));pair.append(None);continue
    raw=v[field];require(type(raw)is str,'Exact original nominal text');f=Fraction(raw);value=float(f);require(f>0 and math.isfinite(value) and value>0,'Positive finite nominal');pair.append(value);conversion.append(dict(security_id=sid,session=d,field=field,exact=raw,binary64_hex=value.hex(),json_pointer=f'/rows/{i}/channel/quote_rows/{qi}/{field}'))
   qmap[sid][d]=pair
  for ev in ch['event_policies']:
   if first<=ev['session']<=end:
    require(ev['kind']=='ORDINARY_SPLIT' and type(ev['numerator'])is int and type(ev['denominator'])is int and ev['numerator']>0 and ev['denominator']>0 and ev['numerator']!=ev['denominator'] and ev['session'] in calendar,'Explicit observed split');require(not any(a['security_id']==sid and a['session']==ev['session'] for a in actions),'No duplicate split')
    receipt=ch['receipt_preserved'];url=receipt['request_url'];u=urlsplit(url);require(type(url)is str and not any(c.isspace() for c in url) and u.scheme=='https' and u.hostname and not u.username and not u.password,'Actual public receipt URL');exact([receipt['raw_path'],receipt['raw_sha256'],receipt['ticker']],[ch['raw_reference']['path'],ch['raw_reference']['sha256'],security['ticker']],'Split receipt binding');actions.append(dict(security_id=sid,session=ev['session'],new_shares=ev['numerator'],old_shares=ev['denominator'],source_url=receipt['request_url'],evidence_sha256=ch['raw_reference']['sha256']))
 opens=dict(index=calendar,columns=columns,data=[[qmap[s['security_id']].get(d,[None,None])[0] for s in securities] for d in calendar]);closes=dict(index=calendar,columns=columns,data=[[qmap[s['security_id']].get(d,[None,None])[1] for s in securities] for d in calendar]);schedule=[dict(c,targets=deepcopy(targets)) for c in clock];risk={c['decision_date']:deepcopy(chains) for c in clock};rows=[]
 for li,lane in enumerate(candidate['rows']):
  mode,name=MODES[li//4],LANES[li%4];exact(lane['coordinate_indexes'],[li+8*d for d in range(6)],'Full lane coordinate linkage');exact([lane['fx_mode'],lane['lane']],[mode,name],'Original lane order');require(len(lane['tracks'])==2,'Two candidate track roles');tracks=[]
  for ti,track in enumerate(lane['tracks']):
   kind=['CONTINUOUS','WHOLE_LOT'][ti];require(track['track']==kind,'Original track order');state=track['stateful_input'];exact(state['calendar'],calendar,'Same complete candidate/control calendar');exact(state['parameters'],params,'Same original monetary and risk parameters')
   flows=deepcopy(state['external_flows']);require(flows==lane['tracks'][0]['stateful_input']['external_flows'],'Same lane flow across tracks');seen=set()
   for flow in flows:
    require(set(flow)=={'session','amount_usd','currency','timing','source_reference'} and flow['session'] in calendar and flow['currency']=='USD' and flow['timing']=='BEFORE_OPEN','Explicit same USD flow');require(type(flow['amount_usd'])in(int,float) and math.isfinite(flow['amount_usd']) and flow['amount_usd']>=0,'Finite injection');add(flow['source_reference']);key=(flow['session'],flow['source_reference']['path'],flow['source_reference']['sha256']);require(key not in seen,'Duplicate receipt');seen.add(key)
   blocked=deepcopy(gaps)
   if any(f['session']==calendar[0] for f in flows):blocked.append(dict(reason='FLOW_BEFORE_INITIAL_DECISION_CLOSE_REQUIRES_EXPLICIT_INITIAL_CAPITAL_CONTRACT'))
   if kind=='CONTINUOUS' and any(a['session']==calendar[0] for a in actions):blocked.append(dict(reason='SPLIT_AT_INITIAL_CLOSE_OUTSIDE_FRACTIONAL_OPEN_ACTION_INTERVAL'))
   kwargs=dict(track=kind,closes=deepcopy(closes),opens=deepcopy(opens),schedule=deepcopy(schedule),risk_chains_by_decision=deepcopy(risk),corporate_actions=deepcopy(actions),external_flows=flows,valuation_end_date=end,**deepcopy(params))
   tracks.append(dict(track=kind,status='BLOCKED_ORIGINAL_CONTROL_INPUT' if blocked else 'CONTROL_INPUTS_PREPARED_NOT_EXECUTED',blocking_reasons=blocked,candidate_status_preserved=track['status'],candidate_blocking_reasons_preserved=deepcopy(track['blocking_reasons']),candidate_input_reference=dict(cr['inputs'],json_pointer=f'/inputs/rows/{li}/tracks/{ti}'),engine_binding=dict(source_reference={k:ENGINE[k] for k in ('path','sha256')},function=ENGINE['function'],keyword_arguments=kwargs,dataframe_restoration_required=['closes','opens']),own_initial_state=dict(cash_usd=25000,shares={}),execution_reused=False,**FLAGS))
  rows.append(dict(fx_mode=mode,lane=name,coordinate_indexes=deepcopy(lane['coordinate_indexes']),tracks=tracks,original_target_weights_preserved=deepcopy(weights),risk_is_order_gate=False,**FLAGS))
 add({k:ENGINE[k] for k in ('path','sha256')})
 result=dict(schema='MULTIDECISION_ORIGINAL_EIGHT_CONTROL_INPUTS_V1',coordinate_count=48,lane_count=8,track_count=16,rows=rows,source_slots=sourceslots,exact_quote_conversion_evidence=conversion,original_control_preserved=deepcopy(o['original_control_preserved']),original_candidate_provenance=deepcopy(o['original_candidate_provenance']),preserved_candidate_evidence_sidecars=deepcopy(o['preserved_candidate_evidence_sidecars']),candidate_evidence_references=deepcopy(cr),original_eight_evidence_references=deepcopy(orr),source_hashes=sources,nav_role='EXTERNAL_NAV_REFERENCE_NOT_A_SUBSCRIPTION_ACCOUNT',control_deduplication_performed=False,**FLAGS);result['content_sha256']=digest(result);return result
