"""Single-session conditional ALXN liquidation; not May or July certification."""
from copy import deepcopy
SID='research:security:alxn';START='2021-05-28';END='2021-06-01';MONTH_END='2021-06-30'
PATH='tmp/alxn_june_short_exit_review_20261105/timeline_and_candidate.json'
SHA='fee021cdcb9e98f7ce9c465098033905f33aeb538cdc95bdc566daca3e52218b'
def apply_gate(gate,*,window,arguments,selected,active,until):
 result=deepcopy(gate)
 if window!='2021_2023' or arguments['decision_date']!=START or active!=END or until!=MONTH_END:return result
 if result.get('decision_date')!=START or result.get('through')!=MONTH_END or result.get('exposure_end_by_security',{}).get(SID)!=END:return result
 if arguments['account_state']['shares'].get(SID)!=24 or selected['target_quantities'].get(SID,0)!=0:return result
 if SID not in result.get('missing_action_streams',[]):return result
 result['missing_action_streams']=[s for s in result['missing_action_streams'] if s!=SID]
 result['conditional_assumptions']=[dict(security_id=SID,start_exclusive=START,end_inclusive=END,kind='ASSUMED_NO_UNOBSERVED_ACTION_BEFORE_FULL_JUNE1_EXIT',required_opening_shares=24,required_target=0,required_after_session_shares=0,evidence_path=PATH,evidence_sha256=SHA,absence_proven=False,production_admission=False)]
 result['original_gate_rejection_preserved']=deepcopy(gate);result['admitted']=not result['missing_action_streams'] and not result.get('unmapped_events');result['evidence_scope']='CONDITIONAL_SINGLE_SESSION_EXIT_NOT_PROVEN_ACTION_ABSENCE';return result

def assert_exit(rows):
 for row in rows:
  if END<=row['date']<=MONTH_END and row['shares'].get(SID,0)!=0:raise ValueError('ALXN_JUNE1_EXIT_NOT_COMPLETE_OR_JUNE_REAPPEARED')
