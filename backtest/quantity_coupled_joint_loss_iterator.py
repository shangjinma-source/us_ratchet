"""Exact budget/loss coupled iterator; one active zero reduced-cost axis only.

For fixed other coordinates, strict improvement requires
 q_z > (B-C_other-(D-L_other)/lambda)/cost_z,
while feasibility requires q_z <= (B-C_other)/cost_z.  With exact width
D/(lambda*cost_z)<1 their intersection contains at most one integer.
All other axes retain the loss-kernel necessary deviations. DFS is fixed
ascending SID/deviation. Unsupported degeneracies are rejected, never guessed.
At a prefix, maximum spend uses assigned quantities and independent maxima
of every remaining allowed axis (including the zero axis). Hence feasible
loss >= partial_loss + lambda*max(0,B-maximum_spend). Ignoring issuer and
joint-budget restrictions only increases that maximum, so pruning is safe.
100000 popped prefixes / 10000 original objective calls are hard ceilings.
No optimizer or IO; verification repeats bounded traversal, not a free check.
"""
from copy import deepcopy
from fractions import Fraction as F
import json
from backtest.quantity_small_joint_loss_enumerator import canonical,load,pattern_bound
from backtest import quantity_saved_anchor_tail_tightening as tail
from backtest import quantity_joint_anchor_loss as loss_kernel
from backtest import quantity_integer_box_certificate_prototype as core
MAX_NODES=100000
MAX_OBJECTIVES=10000
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
 count=pattern_bound(loss)
 return report,c,loss,count,core.prepare(**expected['inputs']),incumbent

def strict_interval(*,spendable,other_spend,loss_budget,other_loss,dual_lambda,unit_cost,lo,hi):
 """Exact open lower endpoint and closed upper endpoint; no float rounding."""
 lower=(spendable-other_spend-(loss_budget-other_loss)/dual_lambda)/unit_cost
 upper=(spendable-other_spend)/unit_cost
 first=max(lo,lower.numerator//lower.denominator+1)
 last=min(hi,upper.numerator//upper.denominator)
 return dict(strict_lower=str(lower),closed_upper=str(upper),first=first,last=last)

def prefix_bound(*,problem,all_axes,branch_axes,prefix,zero_axis,box,dual_lambda):
 """Independent coordinate maxima safely relax every remaining combination."""
 maximum={a['sid']:max(a['preferred'],a['preferred']+a['direction']*a['max_deviation']) for a in all_axes}
 maximum[zero_axis]=box[zero_axis][1]
 for axis,deviation in zip(branch_axes,prefix):maximum[axis['sid']]=axis['preferred']+axis['direction']*deviation
 spend=sum((problem['cost'][s]*q for s,q in maximum.items()),F(0))
 partial=sum((F(branch_axes[i]['penalty'])*d for i,d in enumerate(prefix)),F(0))
 surplus=max(F(0),problem['spendable']-spend)
 return dict(maximum_possible_spend=str(spend),minimum_budget_loss=str(dual_lambda*surplus),partial_coordinate_loss=str(partial),total_loss_lower=str(partial+dual_lambda*surplus))

def build(*,objective_budget=MAX_OBJECTIVES,node_budget=MAX_NODES,**sources):
 core.require(type(objective_budget)is int and 0<=objective_budget<=MAX_OBJECTIVES and type(node_budget)is int and 0<=node_budget<=MAX_NODES,'HARD_BUDGET_REQUIRED')
 report,parent,loss,count,p,incumbent=_context(**sources)
 lam=F(loss['binding']['dual_lambda']);gap=F(loss['strict_loss_budget']);box=parent['remaining_box']
 core.require(lam>0,'POSITIVE_LAMBDA_REQUIRED')
 zero=[s for s in p['ids'] if box[s][0]<box[s][1] and F(loss['reduced_coefficients'][s])==0]
 core.require(len(zero)==1,'EXACTLY_ONE_ACTIVE_ZERO_AXIS_REQUIRED')
 z=zero[0];width=gap/(lam*p['cost'][z])
 core.require(0<width<1,'STRICT_INTERVAL_WIDTH_BELOW_ONE_REQUIRED')
 axes=[a for a in count['axes'] if a['sid']!=z and a['max_deviation']>0]
 stack=[[]];ledger=[];points=[];evaluations=0;lower=F(parent['lower_product']);best=lower;selected=deepcopy(incumbent)
 while stack and len(ledger)<node_budget and evaluations<objective_budget:
  prefix=stack.pop();partial=sum((F(axes[i]['penalty'])*d for i,d in enumerate(prefix)),F(0))
  proof=prefix_bound(problem=p,all_axes=count['axes'],branch_axes=axes,prefix=prefix,zero_axis=z,box=box,dual_lambda=lam)
  record=dict(prefix=prefix,partial_coordinate_loss=str(partial),prefix_loss_bound=proof)
  if F(proof['total_loss_lower'])>=gap:record['terminal']='CLOSED_BY_PREFIX_BUDGET_AND_COORDINATE_LOSS'
  elif len(prefix)<len(axes):
   a=axes[len(prefix)];record.update(terminal='SPLIT_ALL_ALLOWED_DEVIATIONS',sid=a['sid'],maximum=a['max_deviation'])
   for d in range(a['max_deviation'],-1,-1):stack.append(prefix+[d])
  else:
   q={a['sid']:a['preferred'] for a in count['axes']}
   for a,d in zip(axes,prefix):q[a['sid']]+=a['direction']*d
   spend=sum((p['cost'][s]*n for s,n in q.items() if s!=z),F(0))
   interval=strict_interval(spendable=p['spendable'],other_spend=spend,loss_budget=gap,other_loss=partial,dual_lambda=lam,unit_cost=p['cost'][z],lo=box[z][0],hi=box[z][1])
   record['zero_axis_interval']=interval
   core.require(interval['last']-interval['first']<1,'INTERVAL_NOT_SINGLETON')
   if interval['first']>interval['last']:record['terminal']='CLOSED_BY_COUPLED_BUDGET_LOSS'
   else:
    q[z]=interval['first'];positive={s:n for s,n in q.items() if n};issuers=[p['metadata'][s]['issuer_id'] for s in positive]
    spent=spend+p['cost'][z]*q[z];residual=p['cash']-spent
    feasible=len(set(issuers))==len(issuers) and residual>=0 and (not positive or residual>=p['buffer'])
    point=dict(quantities=positive,feasible=feasible,fee_inclusive_spend=str(spent),product=None)
    if feasible:
     value=core.objective(p,positive)[0];evaluations+=1;point['product']=str(value)
     if value>best:best=value;selected=positive
    points.append(point);record.update(terminal='CHECKED_INTEGER_POINT',point_index=len(points)-1)
  ledger.append(record)
 return dict(schema='COUPLED_JOINT_LOSS_ITERATOR_V1',scope='ONE_BOUND_DOMAIN_VALUE_ONLY_OTHER_DOMAINS_REMAIN',binding=dict(parent_report_sha256=sources['expected_parent_report_sha256'],target_id=sources['target_id'],tail_sha256=sources['expected_tail_sha256'],loss_sha256=sources['expected_loss_sha256'],loss_binding_sha256=sources['expected_loss_binding_sha256']),parent_closed_rows=deepcopy(report['inherited_closed_rows']),parent_fixing_rows=deepcopy(report['inherited_fixing_rows']),other_domains=deepcopy([r for r in report['new_rows'] if r['id']!=sources['target_id']]),original_box=deepcopy(box),necessary_count_evidence=count,zero_axis=z,strict_interval_width=str(width),axes=axes,rule='ASCENDING_SID_ASCENDING_DEVIATION_DFS_WITH_EXACT_ZERO_AXIS_INTERVAL',ledger=ledger,points=points,unsearched_frontier=stack,frontier_semantics='Each prefix retains all allowed suffix deviations and the full original zero-axis interval until processed.',objective_budget=objective_budget,node_budget=node_budget,visited_nodes=len(ledger),checked_points=len(points),objective_evaluations=evaluations,selected_candidate=selected,original_lower_product=str(lower),candidate_product=str(best),domain_complete=not stack,status='TARGET_DOMAIN_COMPLETE_OTHER_DOMAINS_UNRESOLVED' if not stack else 'BUDGET_STOPPED_UNRESOLVED',global_objective_value_optimal=False,tie_break_optimality_established=False,integer_source_lower_modified=False,solver_calls=0,economic_runs=0)

def verify(certificate,**sources):
 expected=build(objective_budget=certificate['objective_budget'],node_budget=certificate['node_budget'],**sources)
 core.require(canonical(expected)==canonical(certificate),'COUPLED_CERTIFICATE_CHANGED')
 return dict(status='VERIFIED_COUPLED_BOUND_DOMAIN',domain_complete=expected['domain_complete'],global_objective_value_optimal=False)
