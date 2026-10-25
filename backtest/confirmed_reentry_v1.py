"""Research-only weak exit with three completed ON closes before reentry."""
def confirmed_reentry_target(target, shares, plans, enabled, diagnostics, monthly_ceiling):
    result=dict(target);blocked=[]
    if not enabled:return result,blocked
    for sid in set(plans)-{s for s,q in monthly_ceiling.items() if q>0}:plans.pop(sid)
    for sid,ceiling in monthly_ceiling.items():
        if ceiling<=0:continue
        on=diagnostics[sid]['on']
        if type(on) is not bool:raise ValueError('MISSING_BOOLEAN_SIGNAL')
        state=plans.get(sid)
        if on:
            if state and state['exited']:
                state['confirmations']+=1
                if state['confirmations']<3:
                    result[sid]=0
                    if target.get(sid,0)>0:blocked.append(sid)
                    continue
            plans.pop(sid,None)
            continue
        state=plans.setdefault(sid,dict(count=0,exited=False,confirmations=0))
        state['confirmations']=0
        if not state['exited']:
            state['count']=state['count']+1 if shares.get(sid,0)>0 else 0
            if state['count']>=5:state['exited']=True
        if state['exited']:
            result[sid]=0
            if target.get(sid,0)>0:blocked.append(sid)
    return result,blocked
