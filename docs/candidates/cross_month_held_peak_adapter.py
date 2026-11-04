"""Isolated B adapter: only carry a continuing holding's peak across month reset."""
from copy import deepcopy
from fractions import Fraction
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from core.monthly_peak_exit import advance_monthly_exit


class CrossMonthHeldPeakAdapter(MonthlyExitCoreResearchAdapter):
    def __init__(self,actions=()):
        super().__init__(actions);self.position_epochs={};self.audit=[]

    def apply(self,*,day,month,target,closes,adjustments=(),position_epochs):
        # Caller supplies execution-ledger lifecycle IDs, not intended targets.
        # Empty means no actual position; new IDs after a true zero/reentry.
        if not isinstance(position_epochs,dict) or any(not isinstance(s,str) or not isinstance(e,str) or not e for s,e in position_epochs.items()):
            raise ValueError('EXECUTED_POSITION_EPOCHS_REQUIRED')
        previous=deepcopy(self.state)
        continuing={s for s,e in position_epochs.items() if self.position_epochs.get(s)==e}
        new_month=previous is not None and previous['decision_date']!=month
        # Use a trial so failures never partially advance research state.
        trial=MonthlyExitCoreResearchAdapter(self.actions);trial.state=deepcopy(self.state);trial.last_day=self.last_day
        effective,outcome=trial.apply(day=day,month=month,target=target,closes=closes,adjustments=adjustments)
        carried={}
        if new_month and trial.state is not None:
            carried={s:Fraction(previous['peaks'][s]) for s in continuing if s in previous['peaks'] and s in closes}
            # Base adapter already validated every supplied split and source.
            for change in adjustments:
                sid=change['security_id']
                if sid in carried:
                    event=next(a for a in self.actions if (a['date'],a['security_id'])==(day,sid))
                    carried[sid]*=Fraction(event['old_shares'])/Fraction(event['new_shares'])
            seeded=deepcopy(trial.state)
            for sid,peak in carried.items():seeded['peaks'][sid]=str(max(peak,Fraction(seeded['peaks'][sid])))
            outcome=advance_monthly_exit(state=seeded,account_id='isolated-research',decision_date=month,session_date=day,closes=closes,unit_ids=seeded['unit_ids'],baseline_targets=target)
            effective=outcome['effective_target_quantities'];trial.state=outcome['state']
        self.state,self.last_day=trial.state,trial.last_day
        self.position_epochs=deepcopy(position_epochs)
        self.audit.append(dict(day=day,month=month,carried_peaks={s:str(p) for s,p in carried.items()},position_epochs=deepcopy(position_epochs)))
        return effective,deepcopy(outcome)


class ExecutedPositionEpochs:
    """Consume every completed ledger snapshot; the book forbids same-SID round trips per session."""
    def __init__(self):self.count=0;self.epochs={};self.processed=0
    def observe(self,state):
        ledger=state['daily_ledger']
        if len(ledger)<self.processed:raise ValueError('LIFECYCLE_LEDGER_REWOUND')
        def advance(shares):
            active={s for s,q in shares.items() if q>0}
            for s in set(self.epochs)-active:del self.epochs[s]
            for s in sorted(active-set(self.epochs)):
                self.count+=1;self.epochs[s]=f'{s}:{self.count}'
        for row in ledger[self.processed:]:advance(row['shares'])
        self.processed=len(ledger);advance(state['shares'])
        return deepcopy(self.epochs)
