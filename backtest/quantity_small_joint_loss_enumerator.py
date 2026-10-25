"""Bounded complete search of one externally bound small loss-filtered domain.

The full target remains in the parent report; other domains are copied as
unresolved references. Only this domain is enumerated. Loss-filtered points
are a provable superset of strict improvers, not a selected stock shortlist.
Hard admission <=10000 necessary patterns; <=200000 branch nodes per call.
No solver, price fetch, economic replay, original-certificate mutation or IO.
"""
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
import json
from backtest import quantity_saved_anchor_tail_tightening as tail
from backtest import quantity_joint_anchor_loss as loss_kernel
from backtest import quantity_integer_box_certificate_prototype as core
MAX_POINTS=10000
MAX_NODES=200000

def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def load(raw,h):
 core.require(type(raw)is bytes and sha256(raw).hexdigest()==h,'RAW_HASH_CHANGED');return json.loads(raw)

def pattern_bound(loss):
 """Exact necessary-count upper; coefficient polynomial, no point enumeration."""
 box=loss['binding']['box'];gap=F(loss['strict_loss_budget']);free=1;weighted=[];axes=[]
 for sid in sorted(box):
  lo,hi=box[sid];width=hi-lo;penalty=abs(F(loss['reduced_coefficients'][sid]))
  if penalty==0:allowed=width;free*=width+1
  else:
   ratio=gap/penalty;allowed=max(0,min(width,(ratio.numerator+ratio.denominator-1)//ratio.denominator-1))
   if allowed:weighted.append((penalty,allowed))
  axes.append(dict(sid=sid,max_deviation=allowed,penalty=str(penalty),preferred=loss['preferred_endpoints'][sid],direction=-1 if F(loss['reduced_coefficients'][sid])>=0 else 1))
 if gap<=0:return dict(count_upper=0,max_positive_coordinates=0,axes=axes)
 running=F(0);k=0
 for penalty,_ in sorted(weighted):
  if running+penalty>=gap:break
  running+=penalty;k+=1
 poly=[1]
 for _,choices in weighted:
  updated=[0]*(len(poly)+1)
  for i,value in enumerate(poly):updated[i]+=value;updated[i+1]+=value*choices
  poly=updated
 return dict(count_upper=free*sum(poly[:k+1]),max_positive_coordinates=k,axes=axes)

def _context(*,parent_report_raw,expected_parent_report_sha256,target_id,tail_raw,expected_tail_sha256,tail_sources,loss_raw,expected_loss_sha256,expected_loss_binding_sha256):
 report=load(parent_report_raw,expected_parent_report_sha256);c=load(tail_raw,expected_tail_sha256);tail.verify(c,**tail_sources)
 matches=[r for r in report['new_rows'] if r['id']==target_id]
 core.require(len(matches)==1 and matches[0]['certificate_sha256']==expected_tail_sha256,'TARGET_REPORT_CHANGED')
 core.require(report['lower_product']==c['lower_product'],'PARENT_LOWER_CHANGED')
 loss=load(loss_raw,expected_loss_sha256);loss_kernel.verify(loss,expected_binding_sha256=expected_loss_binding_sha256)
 source=json.loads(tail_sources['fixing_sources']['anchor_raw']);incumbent=tail_sources['fixing_sources']['incumbent']
 expected=dict(inputs=source['binding']['inputs'],box=c['remaining_box'],anchor_quantities=source['repaired_quantities'],incumbent=incumbent,dual_lambda=loss['binding']['dual_lambda'])
 core.require(canonical(expected)==canonical(loss['binding']),'LOSS_TARGET_CHANGED')
 core.require(canonical(report['integer_selected_unchanged'])==canonical(incumbent),'INCUMBENT_CHANGED')
 count=pattern_bound(loss);core.require(count['count_upper']<=MAX_POINTS,'DOMAIN_TOO_LARGE_FOR_THIS_ENUMERATOR')
 return report,c,loss,count,core.prepare(**expected['inputs']),incumbent

def build(*,point_budget=MAX_POINTS,node_budget=MAX_NODES,**sources):
 core.require(type(point_budget)is int and 0<=point_budget<=MAX_POINTS and type(node_budget)is int and 0<=node_budget<=MAX_NODES,'HARD_BUDGET_REQUIRED')
 report,parent,loss,count,p,incumbent=_context(**sources)
 axes=[a for a in count['axes'] if a['max_deviation']>0];gap=F(loss['strict_loss_budget']);lower=F(parent['lower_product'])
 stack=[[]] if count['count_upper'] else [];ledger=[];points=[];best=lower;selected=deepcopy(incumbent);evaluations=0
 while stack and len(ledger)<node_budget:
  prefix=stack[-1];depth=len(prefix);partial=sum((F(axes[i]['penalty'])*d for i,d in enumerate(prefix)),F(0))
  if depth==len(axes) and partial<gap and len(points)>=point_budget:break
  stack.pop();record=dict(prefix=prefix,partial_coordinate_loss=str(partial))
  if partial>=gap:record['terminal']='CLOSED_BY_EXACT_JOINT_LOSS'
  elif depth<len(axes):
   axis=axes[depth];record.update(terminal='SPLIT_ALL_ALLOWED_DEVIATIONS',sid=axis['sid'],maximum=axis['max_deviation'])
   for value in range(axis['max_deviation'],-1,-1):stack.append(prefix+[value])
  else:
   q={a['sid']:a['preferred'] for a in count['axes']}
   for axis,d in zip(axes,prefix):q[axis['sid']]+=axis['direction']*d
   positive={s:n for s,n in q.items() if n};issuer_ids=[p['metadata'][s]['issuer_id'] for s in positive]
   spent=sum((p['cost'][s]*n for s,n in positive.items()),F(0));residual=p['cash']-spent
   feasible=len(set(issuer_ids))==len(issuer_ids) and residual>=0 and (not positive or residual>=p['buffer'])
   point=dict(quantities=positive,issuer_unique=len(set(issuer_ids))==len(issuer_ids),fee_inclusive_spend=str(spent),residual_cash=str(residual),feasible=feasible,product=None)
   if feasible:
    value=core.objective(p,positive)[0];evaluations+=1;point['product']=str(value)
    if value>best:best=value;selected=positive
   points.append(point);record.update(terminal='CHECKED_INTEGER_POINT',point_index=len(points)-1)
  ledger.append(record)
 core.require(len(points)<=count['count_upper'],'COUNT_UPPER_VIOLATED')
 complete=not stack
 return dict(schema='SMALL_JOINT_LOSS_DOMAIN_ENUMERATION_V1',scope='ONE_BOUND_DOMAIN_VALUE_ONLY_OTHER_DOMAINS_REMAIN',binding=dict(parent_report_sha256=sources['expected_parent_report_sha256'],target_id=sources['target_id'],tail_sha256=sources['expected_tail_sha256'],loss_sha256=sources['expected_loss_sha256'],loss_binding_sha256=sources['expected_loss_binding_sha256']),
  parent_closed_rows=deepcopy(report['inherited_closed_rows']),parent_fixing_rows=deepcopy(report['inherited_fixing_rows']),other_domains=deepcopy([r for r in report['new_rows'] if r['id']!=sources['target_id']]),
  original_box=deepcopy(parent['remaining_box']),necessary_count_evidence=count,rule='ASCENDING_SID_ASCENDING_INTEGER_DEVIATION_DFS',ledger=ledger,points=points,unsearched_frontier=stack,
  point_budget=point_budget,node_budget=node_budget,visited_nodes=len(ledger),checked_points=len(points),objective_evaluations=evaluations,selected_candidate=selected,original_lower_product=str(lower),candidate_product=str(best),
  domain_complete=complete,status='TARGET_DOMAIN_COMPLETE_OTHER_DOMAINS_UNRESOLVED' if complete else 'BUDGET_STOPPED_UNRESOLVED',global_objective_value_optimal=False,tie_break_optimality_established=False,integer_source_lower_modified=False,solver_calls=0,economic_runs=0)

def verify(certificate,**sources):
 expected=build(point_budget=certificate['point_budget'],node_budget=certificate['node_budget'],**sources)
 core.require(canonical(certificate)==canonical(expected),'ENUMERATION_CERTIFICATE_CHANGED')
 return dict(status='VERIFIED_SMALL_BOUND_DOMAIN_ENUMERATION',domain_complete=expected['domain_complete'],global_objective_value_optimal=False)
