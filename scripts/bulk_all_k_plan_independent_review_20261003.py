"""Independent exact all-k lazy-plan readback, no planner imports."""
import json,hashlib,math
from fractions import Fraction as F
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'data/cache/research/bulk_all_k_plan_20261003_v1'
SHA='77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671';PUB='c5988351adb898c00626c2473b9e8e363fca3975651522263b07c80bed3b6691'
def check(v,m):
 if not v:raise ValueError(m)
def digest(v):return hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def read(r):
 b=Path(r['path']).read_bytes();check(hashlib.sha256(b).hexdigest()==r['sha256'],'source '+r['path']);return json.loads(b)
def rat(d):return F(int(d['numerator']),int(d['denominator']))
def verify():
 ref={'path':str(D/'plan.json'),'sha256':SHA};o=read(ref);p=o['plan'];pub=read({'path':str(D/'publication.json'),'sha256':PUB});start=json.loads((D/'started.json').read_bytes())
 check(pub['plan_reference']==ref and pub['source_hashes']==start['source_hashes']==o['source_hashes'] and pub['status']=='PLANNED_NOT_ENUMERATED','receipt/source maps')
 for path,h in o['source_hashes'].items():check(hashlib.sha256(Path(path).read_bytes()).hexdigest()==h,'source SHA')
 refs=o['input_references'];panel=read(refs['panel']);old=read(refs['old_plan'])['plan'];receipt=read(refs['publication']);check(receipt['panel_reference']==refs['panel'] and receipt['source_hashes']==panel['source_hashes'],'panel receipt')
 check(p['context']['panel_reference']==refs['panel'] and p['context']['panel_audit_reference']==refs['audit'],'panel/audit refs')
 check(p['context']['parameters']==old['context']['parameters'] and p['fitter_source_hashes']==old['fitter_source_hashes'] and len(p['fitter_source_hashes'])==25,'original contract')
 check(p['context']['previous_target_weights'] is None and p['context']['weight_specs']==old['context']['weight_specs'] and len(p['context']['weight_specs'])==3,'3spec None noalias')
 check(p['context']['fitter_source_fingerprint']==digest(p['fitter_source_hashes']) and p['plan_id']==digest(p['context']),'context digests')
 check(p['content_sha256']==digest({k:v for k,v in p.items() if k!='content_sha256'}),'content hash')
 universe=panel['panel']['universe'];rows=[dict(zip(universe['columns'],r)) for r in universe['data']];groups={}
 for r in rows:groups.setdefault(r['issuer_id'],[]).append(r['security_id'])
 expected=[{'issuer_id':i,'security_ids':sorted(ss)} for i,ss in sorted(groups.items())]
 check(expected==p['canonical_groups'] and len(rows)==77 and len(groups)==76 and sorted(map(len,groups.values()))==[1]*75+[2],'fullgroup77/76')
 check(p['context']['group_fingerprint']==digest({'order_version':p['context']['order_version'],'groups':[(g['issuer_id'],g['security_ids']) for g in expected]}),'groupfingerprint')
 check(o['complete_observed_provenance_and_missing']==panel['panel']['observed_provenance_and_missing'] and len(o['complete_observed_provenance_and_missing'])==101,'101provenance')
 sidecars={k:dict(refs['panel'],json_pointer='/'+k) for k in panel if 'evidence_and_projection' in k};check(len(sidecars)==7 and sidecars==o['preserved_evidence_sidecar_references'],'7sidecarrefs')
 planned=excluded=shards=certs=0;retained=[];lastpages=[]
 check(len(p['cardinalities'])==76 and p['context']['shard_size']==1000,'76cards')
 for k,card in enumerate(p['cardinalities'],1):
  total=(math.comb(75,k) if k<=75 else 0)+2*math.comb(75,k-1);eps=F(1,10**9);pad=F(k+1,10**12)
  comparisons=[('MAX_SINGLE_CAPACITY_BELOW_MINIMUM_SIMPLEX_MASS',k*(F(45,100)+eps)+pad,'<',1-eps-pad),('MIN_SINGLE_REQUIRED_MASS_ABOVE_MAXIMUM_SIMPLEX_MASS',k*(F(5,100)-eps)-pad,'>',1+eps+pad),('TRUE_TOP3_UNIVERSAL_LOWER_BOUND_ABOVE_ACCEPTED_CAP',F(min(3,k),k)*(1-eps-pad),'>',F(8,10)+eps+pad)]
  proof=[x for x in comparisons if (x[1]<x[3] if x[2]=='<' else x[1]>x[3])]
  check(card['k']==k and type(card['combination_count']) is int and card['combination_count']==total,'count k'+str(k));check(len(proof)==len(card['necessary_bound_certificates']),'certificate set')
  for c,(reason,left,op,right) in zip(card['necessary_bound_certificates'],proof):check((c['reason'],rat(c['left']),c['comparison'],rat(c['right']),rat(c['strict_gap']))==(reason,left,op,right,abs(left-right)),'exact necessary certificate')
  certs+=len(proof);n=0 if proof else total;ns=(n+999)//1000
  check(card['planned_combination_count']==n and card['planned_canonical_task_count']==3*n and card['planned_shard_count']==ns and card['first_global_shard_ordinal']==shards and card['first_global_planned_combination_ordinal']==planned and card['interval_rule']=={'start':0,'stop':n,'shard_size':1000},'interval offsets')
  if proof:excluded+=total
  else:retained.append(k);lastpages.append({'k':k,'last_start':(ns-1)*1000,'last_stop':n,'last_tasks':3*(n-(ns-1)*1000)})
  planned+=n;shards+=ns
 check(p['all_k_combination_count']==3*2**75-1==planned+excluded and p['planned_combination_count']==planned and p['necessary_bound_excluded_combination_count']==excluded and p['planned_shard_count']==shards,'total closure')
 check(type(p['completed_canonical_task_count']) is int and p['completed_canonical_task_count']==0 and p['remaining_canonical_task_count']==p['planned_canonical_task_count']==3*planned and o['old_completed_tasks_deducted']==0,'no504prematurededuct')
 check('shards' not in p and p['shard_descriptors_materialized'] is False and p['risk_feasibility_proven'] is False and p['shard_page_limit']==1000,'lazyonly')
 for d in (o,p,pub):
  for key in ('combination_enumeration_performed','task_inputs_materialized','fit_performed','old_fit_results_reused','old_plan_build_called','panel_audit_repeated','execution_authorized','point_in_time_verified','promotion_allowed','legal_training_input_admitted','full_transitive_source_closure_reverified','complete_ndx_eligible_pool_verified','continuous_weight_space_exhausted','winner_selected','dual_benchmark_evaluation_performed','oos_evaluation_performed'):check(d[key] is False,'authority '+key)
 check({x.name for x in D.iterdir()}=={'started.json','plan.json','publication.json'},'namespace')
 return {'status':'PASS','source_count':len(o['source_hashes']),'cards':76,'certificate_count':certs,'retained_k':retained,'all_combinations':planned+excluded,'planned_combinations':planned,'planned_tasks':3*planned,'logical_shards':shards,'completed':0,'last_pages':lastpages,'plan_sha256':SHA,'publication_sha256':PUB}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
