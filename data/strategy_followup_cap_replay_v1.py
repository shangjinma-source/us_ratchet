"""Pure cap/exit replay check. Archive authorization remains the caller's job."""
from copy import deepcopy
from fractions import Fraction
from core.strategy_account_ledger import require
from core.monthly_peak_exit import advance_monthly_exit
from core.monthly_risk_sizing import capped_monthly_quantities
from data.monthly_peak_exit_history import monthly_exit_observations


def review_projection(proof,inputs,*,account_id,target_id):
    require(proof['policy_id']=='MONTHLY_CAP50_EXIT20','FOLLOWUP_CAP_POLICY')
    projection=proof['projection'];view=projection['monthly_cap_view'];saved=projection['state']
    require(projection['policy_id']==view['policy']=='MONTHLY_CAP50_EXIT20','FOLLOWUP_CAP_POLICY')
    require(view['base_target_id']==target_id==inputs['base_target']['origin_reference'],
            'FOLLOWUP_CAP_TARGET')
    require(saved['account_id']==account_id,'FOLLOWUP_CAP_ACCOUNT')
    equity=Fraction(view['strategy_equity']);original=view['original_quantities'];prices=view['decision_prices']
    require(equity>0 and set(original)==set(prices),'FOLLOWUP_CAP_SIZING')
    require(all(type(q)is int and q>=0 for q in original.values()),'FOLLOWUP_CAP_QUANTITIES')
    weights={sid:str(q*Fraction(prices[sid])/equity) for sid,q in original.items()}
    recalculated=capped_monthly_quantities(equity=str(equity),weights=weights,decision_prices=prices)
    require(all(view[key]==value for key,value in recalculated.items()),'FOLLOWUP_CAP_SIZING_CHANGED')
    normalized=deepcopy(inputs)
    normalized['base_target']['monthly_decision_date']=saved['decision_date']
    baseline={sid:view['target_quantities'].get(sid,0) for sid in normalized['histories']}
    require(set(view['target_quantities'])<=set(baseline),'FOLLOWUP_CAP_HISTORY_MISSING')
    normalized['base_target']['quantities']=baseline
    dates=[day for day in normalized['session_dates']
           if saved['decision_date']<=day<=normalized['signal_date']]
    for history in normalized['histories'].values():
        by_date={row['date']:row for row in history['closes']}
        require(len(by_date)==len(history['closes']) and set(dates)<=set(by_date),
                'FOLLOWUP_CAP_COMPLETE_HISTORY_REQUIRED')
        history['closes']=[by_date[day] for day in dates]
    observations=monthly_exit_observations(**normalized)
    state=None;result=None
    for row in observations:
        result=advance_monthly_exit(state=state,account_id=account_id,decision_date=row['decision_date'],
            session_date=row['session_date'],closes=row['closes'],unit_ids=row['unit_ids'],baseline_targets=baseline)
        state=result['state']
    require(result is not None,'FOLLOWUP_CAP_EMPTY_HISTORY')
    require(all(saved.get(key)==value for key,value in state.items()),'FOLLOWUP_CAP_STATE_REPLAY_MISMATCH')
    require(result['effective_target_quantities']==projection['effective_target_quantities'] and
            result['reasons']==projection['reasons'],'FOLLOWUP_CAP_EFFECTIVE_MISMATCH')
    require(projection['signal_date']==inputs['signal_date']==saved['session_date'],'FOLLOWUP_CAP_SIGNAL_DATE')
    return dict(status='CAP_SIZING_AND_MONTHLY_EXIT_REPLAYED',sessions=len(observations),
                effective_target_quantities=result['effective_target_quantities'],capture_admitted=False,
                account_writes=False)
