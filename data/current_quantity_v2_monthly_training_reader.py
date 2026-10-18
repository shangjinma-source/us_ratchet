"""Explicit generate-time market-to-account binding; no IO during construction."""
from copy import deepcopy
from zoneinfo import ZoneInfo
from data.current_quantity_v2_difference_plan import require,stamp,number
from data.current_quantity_v2_difference_service import document
from data.current_quantity_v2_monthly_training import _checked,compile_saved_training,build_monthly_training_package,_daily
from data.current_quantity_v2_monthly_retarget import active_proposal
from data.current_quantity_v2_paper_chain import review_chain

class MonthlyMarketTrainingReader:
    def __init__(self,*,market_reader,paper_review_provider,clock):
        self.market_reader=market_reader;self.paper_review_provider=paper_review_provider;self.clock=clock;self._saved=None

    def capture(self,state):
        self._saved=None;state=review_chain(state);ledger=state['ledger'];now=stamp(self.clock())
        supplied=deepcopy(self.market_reader(deepcopy(state)))
        require(set(supplied)=={'source_package','manifest_path','calendar_path','identities_path','held_bar_sources'},'MONTHLY_MARKET_READER_CONTRACT')
        files,pins=_checked(supplied['source_package']);calendar=document(files[supplied['calendar_path']]);old=active_proposal(ledger)
        require(all(o['closed'] for o in ledger['orders'].values()) and number(ledger['reserved_cash'])==0 and not any(ledger['reserved_shares'].values()),'PRIOR_ORDERS_OPEN')
        require(max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))<=stamp(calendar['decision_close_at']),'VALUATION_PRECEDES_LEDGER')
        oldmonth=old.get('target_month') or old['causal_inputs']['target_mandate']['target_month']
        require(calendar['target_month']>oldmonth and calendar['target_month']==now.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m')
            and old['causal_inputs']['capital_decision']['decision_date']<calendar['decision_date']<=calendar['active_date']
            and calendar['active_date'][:7]==calendar['target_month']
            and stamp(calendar['decision_close_at'])<=stamp(calendar['active_open_at'])<=now,'MONTHLY_CALENDAR_MISMATCH')
        compiled=compile_saved_training(supplied['source_package'],supplied['manifest_path']);data=compiled['input']
        require(data['search_arguments']['decision_date']==calendar['decision_date'],'COMPILER_CALENDAR_BINDING')
        identities=document(files[supplied['identities_path']])['securities'];domain=set(data['search_arguments']['prices'])
        held={s for s,q in ledger['shares'].items() if q};missing=held-domain
        require(missing<=set(supplied['held_bar_sources']) and held|domain<=set(identities),'COMPILER_HELD_VALUATION_DOMAIN')
        prioridentities=old.get('securities',old['causal_inputs'].get('securities',{}))
        for sid in held:
            require(sid in prioridentities and all(identities[sid].get(k)==prioridentities[sid].get(k) for k in ('ticker','issuer_id','security_class')),'TRAINING_HELD_IDENTITY_CHANGED')
        supplied['held_bar_sources']={s:supplied['held_bar_sources'][s] for s in sorted(missing)}
        for sid,path in supplied['held_bar_sources'].items():
            _,closes=_daily(files[path],identities[sid]['ticker']);require(closes.get(calendar['decision_date']) is not None,'MISSING_HELD_DECISION_CLOSE')
        proof=self.paper_review_provider.capture({'state':deepcopy(state)})
        for p,raw in proof['files'].items():
            require(p not in files or files[p]==raw,'MONTHLY_MARKET_SOURCE_CONFLICT');files[p]=raw;pins[p]=proof['source_hashes'][p]
        supplied['account_review_path']=proof['account_review_path']
        build_monthly_training_package(state,**supplied,now=stamp(self.clock()))
        self._saved=(deepcopy(state),deepcopy(supplied))
        return deepcopy(supplied)

    def read(self,state):
        state=review_chain(state);require(self._saved is not None and self._saved[0]==state,'MONTHLY_MARKET_READER_UNAVAILABLE')
        supplied=deepcopy(self._saved[1]);build_monthly_training_package(state,**supplied,now=stamp(self.clock()))
        return supplied
    __call__=capture
