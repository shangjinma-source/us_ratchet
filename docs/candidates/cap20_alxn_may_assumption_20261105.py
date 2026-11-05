"""Root-authorized bounded research assumption, explicitly NOT factual certification."""
from copy import deepcopy
SID='research:security:alxn'
START='2021-04-30'
END='2021-05-28'
PATH='tmp/alxn_cap20_may_review_20261105/evidence_candidate.json'
SHA='9e2cf34f22d34409fb369cf162f1d29458d6cfd7ce9ff8d99e9746760312b76d'
def apply_gate(gate,*,window,arguments,until):
 result=deepcopy(gate)
 if window!='2021_2023' or arguments['decision_date']!=START or until!=END:return result
 if result.get('decision_date')!=START or result.get('through')!=END:return result
 if SID not in result.get('missing_action_streams',[]):return result
 if result.get('exposure_end_by_security',{}).get(SID)!=END:return result
 result['missing_action_streams']=[s for s in result['missing_action_streams'] if s!=SID]
 result['conditional_assumptions']=[dict(security_id=SID,start_exclusive=START,end_inclusive=END,kind='ASSUMED_NO_UNOBSERVED_ACTION_FOR_RESEARCH_ONLY',evidence_path=PATH,evidence_sha256=SHA,absence_proven=False,production_admission=False)]
 result['original_gate_rejection_preserved']=deepcopy(gate)
 result['admitted']=not result['missing_action_streams'] and not result.get('unmapped_events')
 result['evidence_scope']='CONDITIONAL_ASSUMPTION_NOT_CONFIRMED_ACTION_ABSENCE_NOT_PRODUCTION'
 return result
