"""Native monthly daily capture with unchanged transport and explicit review authority.

The reviewer is a server-owned admission dependency, never browser data or an
inferred vendor basis. A successful fetch alone cannot authorize normalization.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical,require
from core.strategy_account_split_v1 import replay
from core.saved_monthly_frontier_proposal import build_frontier_proposal
from data.monthly_risk_epoch import initial_completed_risk_session,validate_monthly_epoch
from data.strategy_daily_session_capture import stamp,reject_links
from data.saved_frontier_live_reader_v1 import capture_namespace
from data.strategy_monthly_supplement_gzip_v1 import capture_supplement
from docs.candidates.split_frontier_supplement_20261105 import review_generation
from docs.candidates.split_native_month_daily_20261105 import project_native_month_daily


def prepare_request(*,state,target,proposal,risk_state,calendar,identities,now):
    require(replay(state['account_id'],[r['payload'] for r in state['events']])==state,'NATIVE_CAPTURE_ACCOUNT_REPLAY')
    require(target['target_id']==sha256(canonical(target['payload'])).hexdigest() and proposal==build_frontier_proposal(target=target),'NATIVE_CAPTURE_TARGET_CHANGED')
    from docs.candidates.split_calendar_extension_20261105 import validate_calendar_extension
    validate_calendar_extension(pinned=calendar,current=calendar)
    sessions=calendar['sessions'];dates=[r['date'] for r in sessions];current=stamp(now)
    day=current.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    require(day in dates,'WAIT_SUPPLEMENT_SESSION');index=dates.index(day);session=sessions[index]
    require(stamp(session['open'])<=current<stamp(session['close']),'WAIT_SUPPLEMENT_SESSION')
    same=risk_state is not None and risk_state['target_month']==target['payload']['target_month']
    if risk_state is not None:require(risk_state['account_id']==state['account_id'],'NATIVE_CAPTURE_RISK_ACCOUNT')
    completed=[r['date'] for r in sessions if stamp(r['close'])<=current]
    decision=risk_state['decision_date'] if same else initial_completed_risk_session(inputs=dict(base_target=dict(monthly_target_created_at=target['payload']['created_at']),signal_date=completed[-1],session_dates=dates,session_close_times=dict(closes={r['date']:r['close'] for r in sessions})),target=target,now=current)
    validate_monthly_epoch(decision_date=decision,target_month=target['payload']['target_month'],session_dates=dates)
    require(index>=20 and dates.index(decision)<index,'SUPPLEMENT_MONTHLY_WINDOW')
    quantities=proposal['payload']['proposed_target_quantities'];needed={s for s,q in quantities.items() if q}|{s for s,q in state['shares'].items() if q}|{o['security_id'] for o in state['orders'].values() if o['status']=='OPEN' and o['remaining_quantity']>0}
    if risk_state is not None:needed|=set(risk_state['peaks'])|set(risk_state['exited'])
    require(0<len(needed)<=250 and needed==set(identities),'NATIVE_CAPTURE_DOMAIN')
    binding=dict(account_id=state['account_id'],account_revision=state['revision'],target_id=target['target_id'],session=day)
    request=dict(account_id=state['account_id'],state_revision=state['revision'],window_start=sessions[min(index-20,dates.index(decision))]['open'],observed_floor=session['open'],securities={s:dict(ticker=identities[s]['ticker']) for s in sorted(needed)},current_target_quantities={s:quantities.get(s,0) for s in sorted(needed)})
    return dict(request=request,binding=binding,session=session,decision_date=decision,review_binding=dict(binding,proposal_id=proposal['proposal_id'],risk_state_sha256=sha256(canonical(risk_state)).hexdigest()),calendar_sha256=sha256(canonical(calendar)).hexdigest())


class NativeMonthCaptureReader:
    def __init__(self,*,monthly_view,risk_store,research_root,capture_root,calendar,identities,context_sha256,review_capture,clock,validate_sources,fetch_daily=None,fetch_official=None):
        self.view,self.risk=monthly_view,risk_store
        self.research_root,self.capture_root=Path(research_root),Path(capture_root)
        self.context=dict(calendar=deepcopy(calendar),identities=deepcopy(identities));self.context_hash=context_sha256
        self.review_capture,self.clock,self.validate=review_capture,clock,validate_sources
        self.fetch_daily,self.fetch_official=fetch_daily,fetch_official
        require(callable(review_capture),'NATIVE_INDEPENDENT_REVIEW_REQUIRED')
    def __call__(self,state,target,now,*,proposal):
        self.validate();require(sha256(canonical(self.context)).hexdigest()==self.context_hash,'NATIVE_CAPTURE_CONTEXT_CHANGED')
        before=deepcopy(self.risk.read(state['account_id']));started=stamp(now)
        prepared=prepare_request(state=state,target=target,proposal=proposal,risk_state=before,now=started,**self.context)
        def unchanged(expected_risk=before):
            self.validate()
            require(self.view.monthly.accounts.read()==state and self.view.monthly.current()==target,'NATIVE_CAPTURE_ACCOUNT_OR_TARGET_CHANGED')
            require(self.view.require_proposal(target_id=target['target_id'],expected_proposal_id=proposal['proposal_id'])==proposal,'NATIVE_CAPTURE_PROPOSAL_CHANGED')
            require(self.risk.read(state['account_id'])==expected_risk,'NATIVE_CAPTURE_RISK_CHANGED')
            require(started<=stamp(self.clock())<stamp(prepared['session']['close']),'NATIVE_CAPTURE_SESSION_ENDED')
        def read_binding():unchanged();return deepcopy(prepared['binding'])
        unchanged();reject_links(self.capture_root)
        directory=capture_namespace(self.capture_root,started=self.clock(),session=prepared['session'])/'native-gzip-v1'
        capture=capture_supplement(directory=directory,request=prepared['request'],binding=prepared['binding'],read_binding=read_binding,execute=True,clock=self.clock,fetch_daily=self.fetch_daily,fetch_official=self.fetch_official)
        unchanged()
        require(capture.get('status')=='CAPTURED_REVIEW_REQUIRED','NATIVE_CAPTURE_INCOMPLETE_REQUIRES_RECOVERY')
        # This separate authority must bind exact returned bytes and its own basis evidence.
        review_started=stamp(self.clock())
        admitted=self.review_capture(capture=deepcopy(capture),prepared=deepcopy(prepared),state=deepcopy(state),target=deepcopy(target),proposal=deepcopy(proposal),risk_state=deepcopy(before),now=review_started)
        review_finished=stamp(self.clock())
        require(set(admitted)=={'review_bytes','trusted_review_sha256','files'},'NATIVE_CAPTURE_REVIEW_INTERFACE')
        require(sha256(admitted['review_bytes']).hexdigest()==admitted['trusted_review_sha256'],'NATIVE_CAPTURE_REVIEW_HASH')
        review=json.loads(admitted['review_bytes']);files=admitted['files'];docs=review['documents'];inputs=json.loads(files[docs['normalized_inputs']])
        require(json.loads(files[docs['calendar']])==self.context['calendar'] and json.loads(files[docs['identities']])['securities']==self.context['identities'],'NATIVE_CAPTURE_CONTEXT_REVIEW_CHANGED')
        require(review['monthly_decision_date']==prepared['decision_date'] and review['risk_state_sha256']==prepared['review_binding']['risk_state_sha256'],'NATIVE_CAPTURE_REVIEW_SNAPSHOT')
        reviews={};received={}
        for sid,path in capture['documents']['action_receipts'].items():
            receipt=json.loads(capture['files'][path]);raw=capture['files'][receipt['raw_path']]
            require(files[docs['raw_by_security'][sid]]==raw,'NATIVE_CAPTURE_RAW_REPLACED')
            reviews[sid]=json.loads(files[docs['unit_reviews'][sid]])['raw_normalization'];received[sid]=receipt['received_at']
        require(review['source_received_by_security']==received and stamp(review['source_received_at'])==max(map(stamp,received.values())),'NATIVE_CAPTURE_RECEIVED_BINDING')
        require(max(review_started,stamp(capture['finished_at']),max(map(stamp,received.values())))<=stamp(review['reviewed_at'])<=review_finished,'NATIVE_CAPTURE_REVIEW_CLOCK')
        checked=review_generation(capture=capture,request=prepared['request'],binding=prepared['binding'],inputs=inputs,identities=self.context['identities'],reviews=reviews,now=stamp(review['reviewed_at']))
        require(checked['inputs']==inputs,'NATIVE_CAPTURE_NORMALIZED_CHANGED')
        # Preserve every real transport receipt and wire byte in the immutable risk archive.
        for path,raw in capture['files'].items():require(files.get('capture/'+path)==raw,'NATIVE_CAPTURE_ARCHIVE_INCOMPLETE')
        unchanged()
        result=project_native_month_daily(research_root=self.research_root,risk_path=self.risk.path,target_id=target['target_id'],state=state,now=stamp(self.clock()).isoformat(),enabled=True,**admitted)
        unchanged(expected_risk=result['risk_projection']['state'])
        return dict(result,capture_id=capture['capture_id'],capture_directory=str(directory),review_binding=prepared['review_binding'],automatic_source_approval=False)
