"""Independent projection from saved audited channels; no raw decoding or fitter."""
from pathlib import Path
from fractions import Fraction
import hashlib
import json
import math

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research/dated_training_panel_20261003_v1'
SHA='895f31e30647e1422bcd2feab3025f8e9103c745f9d176549d59a069a30b9d96'
PUB='2b64693fd54c1358429ca9df8ac5c9b685b988d5dab8b661b202991288bcbf05e1'
# Explicit immutable publication digest supplied by the publishing root.
PUB='2b64693fd54c1358429ca9df8ac5c9b685882d419a275a7b4384e878c5c1a2a5'
def check(v,m):
 if not v:raise ValueError(m)
def sha(b):return hashlib.sha256(b).hexdigest()
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b,m):check(enc(a)==enc(b),m)
def read(p,h):
 b=Path(p).read_bytes();check(sha(b)==h,'SHA '+str(p));return b
def verify():
 d=json.loads(read(BASE/'panel.json',SHA));pub=json.loads(read(BASE/'publication.json',PUB));started=json.loads((BASE/'started.json').read_bytes());p=d['panel'];refs=d['input_references'];docs={};sources={}
 check({x.name for x in BASE.iterdir()}=={'started.json','panel.json','publication.json'},'Successful namespace')
 for role,r in refs.items():
  b=read(r['path'],r['sha256']);sources[r['path']]=r['sha256']
  if role!='channels_reader':docs[role]=json.loads(b)
 for file,h in [('backtest/ndx_dated_training_panel_research.py','67c2c2a950d56bc3238f77479b08909077613bca8a6809963470302eba9f616b'),('scripts/ndx_dated_training_panel_20261003.py','816eb11922d69264400b0c63c7a5c0adf917b3bd9c302290c50c38bc1765b361')]:read(ROOT/file,h);sources[str(ROOT/file)]=h
 check(len(sources)==7,'7 direct sources');exact(d['source_hashes'],sources,'Sources');exact(pub['source_hashes'],sources,'Publication sources');exact(started['source_hashes'],sources,'Started sources')
 exact(pub['panel_reference'],dict(path=str(BASE/'panel.json'),sha256=SHA),'Publication payload');exact(d['runtime'],pub['runtime'],'Runtime preserved');exact(d['runtime'],started['runtime'],'Started runtime')
 check(pub['status']=='PUBLISHED_TRAINING_PAYLOAD_NOT_FITTED' and started['retry_allowed'] is False,'No fit/retry')
 source=docs['channels'];audit=docs['channels_readback'];parent=docs['parent_panel']
 check(audit['status']=='PASS' and audit['channels_sha256']==refs['channels']['sha256'] and audit['publication_sha256']==refs['channels_publication']['sha256'] and audit['reader_sha256']==refs['channels_reader']['sha256'],'Prior audit reference only')
 exact(docs['channels_publication']['channels_reference'],refs['channels'],'Channel publication');exact(docs['channels_publication']['source_hashes'],source['source_hashes'],'Parent sources');exact(d['parent_source_hashes_preserved'],source['source_hashes'],'Parent source map preservation')
 calendar=source['calendar253'];check(len(calendar)==253 and calendar[0]=='2025-09-18' and calendar[126]=='2026-03-20' and calendar[127]=='2026-03-23' and calendar[-1]=='2026-09-21','Training/evaluation boundaries')
 coords=[r['coordinate'] for r in source['rows']];u=parent['panel']['universe'];exact(coords,[dict(zip(u['columns'],row)) for row in u['data']],'Original coordinates including late MDV')
 check(len(coords)==77 and len({r['issuer_id'] for r in coords})==76,'77/76 distinct classes')
 values={};selected={};evidence=[];evaluation=[]
 for i,row in enumerate(source['rows']):
  c=row['coordinate'];ch=row['channel'];sid=c['security_id'];ticker=c['ticker'];train=ch['training_returns'];ev=ch['evaluation_returns'];check(len(train)==126 and len(ev)==126,'Partitions')
  check(sha(enc(train))==ch['training_returns_sha256'] and sha(enc(ev))==ch['evaluation_returns_sha256'],'Saved partition digests')
  vals=[];proof=[]
  for j,item in enumerate(train):
   check(item['session']==calendar[j+1] and item['previous_session']==calendar[j] and item['dividends_included'] is False,'Training predecessor')
   r=Fraction(item['split_only_return_exact']);v=float(r);check(str(r)==item['split_only_return_exact'] and math.isfinite(v) and v>-1 and type(item['split_only_return_float']) is float and v==item['split_only_return_float'],'Exact float projection')
   vals.append(v);proof.append(dict(session=item['session'],source_reference=dict(refs['channels'],json_pointer=f'/rows/{i}/channel/training_returns/{j}'),exact_return=str(r),float_hex=v.hex()))
  values[ticker]=vals;selected[sid]={k:c[k] for k in ('ticker','issuer_id','risk_chain')};evidence.append(dict(security_id=sid,ticker=ticker,rows=proof))
  check([x['session'] for x in ev]==calendar[127:],'Evaluation dates')
  evaluation.append(dict(security_id=sid,ticker=ticker,reference=dict(refs['channels'],json_pointer=f'/rows/{i}/channel/evaluation_returns'),saved_payload_sha256=sha(enc(ev)),previous_close_date=calendar[126],return_end_dates=calendar[127:]))
 tickers=sorted(values);frame=dict(type='DataFrame',index_type='DatetimeIndex',index=[x+'T00:00:00' for x in calendar[1:127]],columns=tickers,dtypes=['float64']*77,data=[[values[t][i] for t in tickers] for i in range(126)])
 payload=dict(cutoff=calendar[126],returns=frame,selected_by_security={s:selected[s] for s in sorted(selected)})
 exact(p['fit_payload'],payload,'Entire fit payload exact, no evaluation or MDV fields');exact(p['numeric_conversion_evidence'],evidence,'9702 hex and source pointers');exact(p['evaluation_references'],evaluation,'Evaluation references only')
 check(p['training_frame_sha256']==sha(enc(frame)) and p['fit_payload_sha256']==sha(enc(payload)) and p['evaluation_dates_sha256']==sha(enc(calendar[127:])),'Payload checksums')
 check(p['content_sha256']==sha(enc({k:v for k,v in p.items() if k!='content_sha256'})),'Content hash')
 for key,expected in [('original_coordinate_evidence',coords),('original_provenance_and_missing',source['original_provenance_and_missing']),('preserved_evidence_sidecars',source['preserved_evidence_sidecars']),('preserved_sidecar_references',source['preserved_sidecar_references']),('original_identity_assumed_window',source['original_identity_assumed_window']),('evaluation_prior_fit_overlap_evidence',source['evaluation_prior_fit_overlap_evidence'])]:exact(p[key],expected,'Preserved '+key)
 check(len(p['original_provenance_and_missing'])==101 and len(p['preserved_evidence_sidecars'])==7,'101 and7 scope')
 exact(p['input_references'],dict(channels=refs['channels'],independent_readback=refs['channels_readback'],parent_panel=refs['parent_panel']),'Panel refs')
 for item in (d,p,pub,started):
  for k in ('point_in_time_verified','legal_training_input_admitted','execution_authorized','fit_performed'):check(item[k] is False,'No authority '+k)
 for k in ('evaluation_values_in_fit_payload','old_task_weights_reused','liquidity_qualification_at_training_cutoff_verified'):check(p[k] is False,'Training isolation '+k)
 check(p['new_numerical_task_identity_required'] is True and p['old_results_are_not_dated_refit_results'] is True and p['historical_retrospective_only'] is True,'New task and retrospective limits')
 check(p['excluded_from_training_selection_fields']==['median_dollar_volume_usd'],'No future liquidity selection')
 for file,h in sources.items():read(file,h)
 return dict(schema='DATED_TRAINING_PANEL_INDEPENDENT_READBACK_V1',status='PASS',panel_sha256=SHA,publication_sha256=PUB,reader_sha256=sha(Path(__file__).read_bytes()),direct_source_count=7,security_count=77,issuer_count=76,training_return_rows=126,training_numeric_cells=9702,observed_security_count=101,preserved_sidecar_count=7,first_training_return=calendar[1],training_cutoff=calendar[126],evaluation_numeric_fields_in_fit_payload=0,fit_payload_sha256=sha(enc(payload)),fit_performed=False,raw_redecoded=False,old_audit_repeated=False,point_in_time_verified=False,legal_training_input_admitted=False,liquidity_qualification_at_training_cutoff_verified=False)
if __name__=='__main__':
 r=verify()
 with (ROOT/'DYNAMIC_DATED_TRAINING_PANEL_INDEPENDENT_READBACK_20261003.json').open('x',encoding='utf-8') as f:json.dump(r,f,indent=2);f.write('\n')
 print(json.dumps(r,indent=2))
