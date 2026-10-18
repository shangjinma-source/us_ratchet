"""Independent saved-JSON bulk typed panel verification; no producer/codec imports."""
import json,hashlib,math
from decimal import Decimal,Context,localcontext
from pathlib import Path
from copy import deepcopy
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'data/cache/research/bulk_conditional_panel_20261003_v1'
PANEL='f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71';PUB='895b1d0f71fb3f4b1175845c3390f3d286c672519fa4aa2c0a13bb930f6a2a9d'
FRAMES=('returns','nominal_close','raw_volume','dollar_volume','universe')
def check(v,m):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b):return canonical(a)==canonical(b)
def raw(r):
 b=Path(r['path']).read_bytes();check(sha(b)==r['sha256'],'SHA '+r['path']);return b
def read(r):return json.loads(raw(r))
def rows(frame):return [dict(zip(frame['columns'],r)) for r in frame['data']]
def col(frame,t):return [r[frame['columns'].index(t)] for r in frame['data']]
def payload(frame,kind='index_type'):
 return {'columns':frame['columns'],'index':[s.replace('T',' ') if isinstance(s,str) else str(s) for s in frame['index']],kind:frame['index_kind'],'dtypes':frame['dtypes'],'data':frame['data']}
def typed(frame,name):
 check(set(frame)=={'type','index_kind','index','columns','dtypes','data'} and frame['type']=='dataframe','typed schema')
 check(len(set(frame['columns']))==len(frame['columns'])==len(frame['dtypes']) and len(frame['data'])==len(frame['index']),'typed shape')
 if name=='universe':check(frame['index_kind']=='RangeIndex' and frame['index']==list(range(len(frame['data']))) and frame['dtypes']==['object']*6+['float64'],'universe dtype')
 else:
  check(frame['index_kind']=='DatetimeIndex' and frame['index']==sorted(set(frame['index'])) and all(s.endswith('T00:00:00') for s in frame['index']),'exact midnight date index')
  dtype='int64' if name=='raw_volume' else 'float64';check(frame['dtypes']==[dtype]*len(frame['columns']),'numeric dtypes')
  for r in frame['data']:
   check(len(r)==len(frame['columns']),'row shape')
   check(all(type(v) is int and 0<v<2**63 for v in r) if name=='raw_volume' else all(type(v) is float and math.isfinite(v) and v>(-1 if name=='returns' else 0) for v in r),'finite typed cells')
def flags(d):
 for k in ('formal_input_ready','legal_training_input_admitted','point_in_time_verified','promotion_allowed','execution_authorized','strict_loader_validation_passed','fit_performed','enumeration_performed','raw_oracle_called','old_panel_assemble_called','old_numeric_values_recomputed','http_performed','full_transitive_source_closure_reverified','issuer_observation_currently_certified','winner_selected','source_assertions_authenticated'):
  if k in d:check(d[k] is False,'authority '+k)
def verify():
 pref={'path':str(D/'panel.json'),'sha256':PANEL};out=read(pref);pub=read({'path':str(D/'publication.json'),'sha256':PUB});started=json.loads((D/'started.json').read_bytes());refs=out['input_references']
 check(pub['panel_reference']==pref and pub['status']=='PUBLISHED_CONDITIONAL_PANEL_ONLY','publication')
 check(out['source_hashes']==pub['source_hashes']==started['source_hashes'],'source maps')
 for path,h in out['source_hashes'].items():raw({'path':path,'sha256':h})
 check(set(out['source_hashes'])=={r['path'] for r in refs.values()}|{str(ROOT/'scripts/ndx_bulk_conditional_panel_20261003.py'),str(ROOT/'scripts/ndx_new_cutoff_conditional_panel_20260923.py'),str(ROOT/'backtest/ndx_latest_conditional_panel_research.py'),'D:\\python\\Lib\\site-packages\\pandas\\__init__.py'},'complete direct source paths')
 docs={k:read(r) for k,r in refs.items()};w=docs['wiring'];parent=docs['parent_panel'];old=parent['panel'];p=out['panel'];days=docs['channels']['calendar']
 check(docs['wiring_publication']['wiring_reference']==refs['wiring'] and docs['wiring_publication']['source_hashes']==w['source_hashes'],'wiring receipt')
 check(len(w['historical_denominators_preserved'])==15 and len(w['rows'])==101,'history reference15 and101')
 check(docs['parent_readback']['candidate_reference']==refs['parent_panel'] and docs['parent_readback']['status']=='PASSED' and docs['channel_audit']['candidate_reference']==refs['channels'],'saved audit bindings')
 for f in FRAMES:typed(p[f],f)
 digest_payload={k:payload(v) if k in FRAMES else v for k,v in p.items() if k!='panel_content_sha256'}
 check(sha(canonical(digest_payload))==p['panel_content_sha256'],'independent mutation checksum')
 uni=rows(p['universe']);olduni=rows(old['universe']);by={r['ticker']:r for r in uni}
 check(len(uni)==len({r['security_id'] for r in uni})==77 and len({r['issuer_id'] for r in uni})==76,'actual77/76')
 check(by['GOOG']['security_id']!=by['GOOGL']['security_id'] and by['GOOG']['issuer_id']==by['GOOGL']['issuer_id'],'two class SID')
 check('CRWD' not in by and out['raw_volume_blocked_candidates']==['CRWD'],'CRWD blocked')
 check(len(olduni)==24 and all(by[r['ticker']]==r for r in olduni),'old universe24 exact')
 for name in FRAMES:
  left=old[name];right=deepcopy(p[name])
  if name=='universe':right['data']=[[by[r['ticker']][key] for key in right['columns']] for r in olduni];right['index']=list(range(24))
  else:
   right['columns']=left['columns'];right['dtypes']=[p[name]['dtypes'][p[name]['columns'].index(t)] for t in left['columns']];right['data']=[[r[p[name]['columns'].index(t)] for t in left['columns']] for r in p[name]['data']]
  check(exact(left,right),'old frame '+name)
  proof=out['original24_frame_exact_proof'][name];expected=sha(canonical(payload(left,'index_kind')))
  check(proof=={'original_sha256':expected,'projected_sha256':expected,'exact':True},'frame proof')
 sidecars=('original_evidence_and_projection','incremental_evidence_and_projection','v3_incremental_evidence_and_projection','v4_incremental_evidence_and_projection','v5_incremental_evidence_and_projection','v6_incremental_evidence_and_projection')
 for key in sidecars:check(exact(out[key],parent[key]),'sidecar '+key)
 increments=out['bulk_incremental_evidence_and_projection'];check(len(increments)==53,'new53')
 names=[r['ticker'] for r in increments];check(names==[r['ticker'] for r in w['bulk_extended_provenance']]==out['incremental_numeric_channels_projected'],'increment fullorder')
 gapby={r['ticker']:r for r in p['observed_provenance_and_missing']};oldgap={r['ticker']:r for r in old['observed_provenance_and_missing']};channels={r['ticker']:r for r in docs['channels']['rows']};wrows={r['ticker']:r for r in w['rows']};extensions={r['ticker']:r for r in w['bulk_extended_provenance']}
 check(len(gapby)==len(p['observed_provenance_and_missing'])==101 and [r['ticker'] for r in p['observed_provenance_and_missing']]==[r['ticker'] for r in old['observed_provenance_and_missing']],'101gap order')
 for t in gapby:
  if t not in names:check(exact(gapby[t],oldgap[t]),'old48gap')
 other=[r for r in old['observed_provenance_and_missing'] if r['ticker'] not in names]
 check(out['original48_gap_exact'] is True and out['original48_gap_exact_sha256']==sha(canonical(other)),'48gap proof')
 dollar_cells=0
 for inc in increments:
  t=inc['ticker'];wr=wrows[t];g=gapby[t];c=channels[t]['channel_input']
  check(exact(inc['complete_wiring_row'],wr) and exact(inc['complete_extended_provenance'],extensions[t]) and exact(inc['original_gap'],oldgap[t]) and exact(inc['new_gap'],g),'full incremental evidence')
  check(inc['numerical_column_added'] is True and inc['early_window_review_availability_verified'] is False,'added conditional')
  expected=deepcopy(oldgap[t]);expected.update(coordinate_assumption=dict(wr['coordinate'],scope=p['scope'],dated_fact=None,dated_evidence_role='BULK_CROSS_DOCUMENT_CONDITIONAL_LINK_NOT_JOINT_DATED_PROOF',latest_interval_verified=False,provider_binding_verified=False,assumed_window=wr['new_assumption']['window'],source_references=[refs['wiring']]),risk_assumption=dict(scope=p['scope'],risk_chain=wr['risk_chain'],latest_interval_verified=False,continued_historical_label_is_explicit_assumption=True,source_kind='BULK_SAVED_CONDITIONAL_SEC_EVIDENCE_LINK',source_references=[refs['wiring']]),included_in_conditional_panel=True,blocking_reasons=[])
  check(exact(g,expected),'entire newgap')
  close=[r['nominal_close'] for r in c['price_rows']];returns=[r['price_return'] for r in c['price_returns']];vol=[r['raw_volume'] for r in c['liquidity']['rows']]
  check(col(p['returns'],t)==returns and col(p['nominal_close'],t)==close and col(p['raw_volume'],t)==vol,'3savedcolumns exact')
  check(p['returns']['index']==[d+'T00:00:00' for d in days[1:]] and p['nominal_close']['index']==[d+'T00:00:00' for d in days] and p['raw_volume']['index']==p['dollar_volume']['index']==[d+'T00:00:00' for d in days[-63:]],'frame calendars')
  check(c['liquidity']['status']=='CONDITIONAL_RAW_VOLUME_TIMES_NOMINAL_CLOSE' and c['liquidity']['numerical_threshold_passed'] is True and c['minimum_median_dollar_volume_usd']==50000000,'original gate')
  with localcontext(Context(prec=50)):
   dollars=[Decimal(str(price))*volume for price,volume in zip(close[-63:],vol)];median=sorted(dollars)[31]
  check(col(p['dollar_volume'],t)==[float(z) for z in dollars] and by[t]['median_dollar_volume_usd']==float(median) and median>=50000000,'typed dollars/median')
  check(by[t]==dict(wr['coordinate'],risk_chain=wr['risk_chain'],median_dollar_volume_usd=float(median)),'new universe exact');dollar_cells+=len(dollars)
 check(not out['new_numeric_blocks'] and out['source_coordinate_candidate_count']==78 and out['actual_panel_security_count']==p['conditional_security_count']==77 and out['actual_panel_issuer_count']==p['conditional_issuer_count']==76,'candidate vs actual')
 for value in (out,p,pub):flags(value)
 check({z.name for z in D.iterdir()}=={'started.json','panel.json','publication.json'},'namespace')
 return {'status':'PASS','direct_sources':len(out['source_hashes']),'original_columns_exact':24,'old_frames_exact':5,'old_sidecars_exact':6,'all_gap_rows':101,'unchanged_gap_rows':48,'new_columns':53,'saved_numeric_cells_reused':53*(126+127+63),'typed_dollar_volume_cells':dollar_cells,'new_medians':53,'actual_sid':77,'actual_issuer':76,'historical_coordinates_preserved_by_wiring_reference':15,'panel_sha256':PANEL,'publication_sha256':PUB}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
