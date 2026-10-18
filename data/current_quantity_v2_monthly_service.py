"""Explicit read-only monthly raw-source bridge; no production source or search.

Source pins establish byte consistency, not authenticity. The enclosing service
must hold its source guard through the store commit; double reads are not a lock.
"""
from collections import OrderedDict
from copy import deepcopy
from threading import RLock
from data.current_quantity_v2_difference_service import CurrentQuantityV2DifferenceService,document,decode_execution_package
from data.current_quantity_v2_difference_plan import require,stamp
from data.current_quantity_v2_paper_chain import review_chain
from data.current_quantity_v2_monthly_retarget import build_monthly_retarget


class QuantityV2MonthlySourceBridge:
    def __init__(self,*,store,resolver,clock):
        self.store=store;self.resolver=resolver;self.clock=clock
        self._lock=RLock();self._proposals=OrderedDict()

    def _evidence(self,state,decision_id,now):
        ledger=review_chain(state)['ledger'];aid=ledger['account_id']
        package=deepcopy(self.resolver(aid,decision_id))
        identity=CurrentQuantityV2DifferenceService._package_identity(package)
        files=package['files'];paths=package['documents']
        basic={'capital_decision','target_mandate','identities','unit_continuity','held_unit_continuity','quote_receipts','account_review'}
        require(set(paths)==basic or set(paths)==basic|{'pullback_policy','pullback_proofs'},'MONTHLY_DOCUMENT_FIELDS')
        decision=document(files[paths['capital_decision']]);mandate=document(files[paths['target_mandate']])
        require(decision['decision_id']==decision_id and mandate['account_id']==aid,'DECISION_BINDING_MISMATCH')
        needed={sid for mapping in (ledger['shares'],decision['target_quantities']) for sid,q in mapping.items() if q>0}
        sell_only={sid for sid,q in ledger['shares'].items() if q>0 and decision['target_quantities'].get(sid,0)==0}
        execution=decode_execution_package(package,needed=needed,now=stamp(now),sell_only=sell_only)
        review=document(files[paths['account_review']])
        observed=max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at']))
        derived=review.get('schema')=='QUANTITY_V2_DERIVED_PAPER_REVIEW_V1'
        if derived:
            from data.current_quantity_v2_paper_review import validate_paper_review
            from data.current_quantity_v2_paper_chain import validate_derived_review_sources
            validate_paper_review(review,state,now)
            validate_derived_review_sources(review,package['source_hashes'])
        else:
            require(set(review)=={'account_id','state_revision','pending_rights','reviewed_at','source_references'},'EXPLICIT_ACCOUNT_REVIEW_REQUIRED')
        require(review['account_id']==aid and review['state_revision']==ledger['revision']
            and review['pending_rights']==[] and observed<=stamp(review['reviewed_at'])<=stamp(now)
            and (review['source_references'] or derived) and all(p in package['source_hashes'] for p in review['source_references']), 'EXPLICIT_ACCOUNT_REVIEW_REQUIRED')
        account=dict(account_id=aid,revision=ledger['revision'],cash=ledger['cash'],shares=deepcopy(ledger['shares']),
            observed_at=max(stamp(ledger['last_recorded_at']),stamp(ledger['last_effective_at'])).isoformat(),
            open_orders=[deepcopy(o) for o in ledger['orders'].values() if not o['closed']],
            reserved_cash=ledger['reserved_cash'],reserved_shares=deepcopy(ledger['reserved_shares']),
            pending_rights=deepcopy(review['pending_rights']))
        # Verified paper ledger supports fills only; this is not a broker-rights assertion.
        args=dict(capital_decision=decision,target_mandate=mandate,account_state=account,
            target_scope='ACCOUNT_EQUITY_TARGET',held_unit_continuity=document(files[paths['held_unit_continuity']]),**execution)
        if derived:args['account_review']=deepcopy(review)
        if 'pullback_policy' in paths:args['pullback_policy']=document(files[paths['pullback_policy']])
        require(CurrentQuantityV2DifferenceService._package_identity(self.resolver(aid,decision_id))==identity,'PROPOSAL_SOURCE_CHANGED')
        return args,identity

    def preview(self,*,account_id,decision_id,expected_revision):
        state=review_chain(self.store.read(account_id));ledger=state['ledger']
        require(ledger['account_id']==account_id and ledger['revision']==expected_revision,'STALE_REVISION')
        args,identity=self._evidence(state,decision_id,self.clock())
        require(self.store.read(account_id)==state,'ACCOUNT_CHANGED')
        proposal=build_monthly_retarget(state,proposal_inputs=args,now=self.clock())
        require(CurrentQuantityV2DifferenceService._package_identity(self.resolver(account_id,decision_id))==identity,'PROPOSAL_SOURCE_CHANGED')
        require(self.store.read(account_id)==state,'ACCOUNT_CHANGED')
        final=build_monthly_retarget(state,proposal_inputs=args,now=self.clock())
        require(final['orders']==proposal['orders'] and final['target_quantities']==proposal['target_quantities'],'REFERENCE_NOT_ACCEPTABLE')
        with self._lock:
            self._proposals[proposal['proposal_id']]=dict(proposal=deepcopy(proposal),package_identity=identity)
            self._proposals.move_to_end(proposal['proposal_id'])
            while len(self._proposals)>32:self._proposals.popitem(last=False)
        public={k:deepcopy(v) for k,v in proposal.items() if k not in ('causal_inputs','binding')}
        public.update(scope='MONTHLY_RETARGET',created_at=proposal['causal_inputs']['now'],execution_references={sid:{key:deepcopy(ref[key]) for key in ('security_id','ticker','session','currency','price_basis','last_price','last_at','minute_low','minute_start','minute_end','captured_at','checked_at','valid_until','session_open','session_close')} for sid,ref in args['execution_references'].items()},prior_revision=expected_revision,shares=deepcopy(ledger['shares']),
            securities=deepcopy(args['securities']),orders_created=False,account_mutated=False,source_bytes_verified=True,source_authenticated=False,
            account_state_origin='VERIFIED_PAPER_LEDGER_NO_BROKER_RIGHTS_CERTIFICATION')
        for sid,ref in args['execution_references'].items():
            if 'pullback' in ref:public['execution_references'][sid]['pullback']=deepcopy(ref['pullback'])
        public.setdefault('unit_review',dict(policy='EXPLICIT_UNIT_REVIEW',coverage_complete=False,
            source_authenticated=False,limitations=['显式审阅仅验证已提供来源，不认证公司行动完整性']))
        return public

    def monthly_resolver(self,state,proposal_id,now):
        state=review_chain(state);now=stamp(now);ledger=state['ledger']
        with self._lock:
            require(proposal_id in self._proposals,'PROPOSAL_UNKNOWN_OR_EVICTED')
            saved=deepcopy(self._proposals[proposal_id]);proposal=saved['proposal'];old=proposal['causal_inputs']
        require(proposal['account_id']==ledger['account_id'],'PROPOSAL_ACCOUNT_MISMATCH')
        require(proposal['binding']['prior_revision']==ledger['revision'],'STALE_REVISION')
        require(stamp(old['now'])<=now,'ACCEPTANCE_BEFORE_PROPOSAL')
        args,identity=self._evidence(state,proposal['capital_decision_id'],now)
        require(identity==saved['package_identity'],'PROPOSAL_SOURCE_CHANGED')
        for sid,ref in args['execution_references'].items():ref['checked_at']=old['execution_references'][sid]['checked_at']
        args['now']=old['now']
        require(args==old,'PROPOSAL_SOURCE_CHANGED')
        current=build_monthly_retarget(state,proposal_inputs=args,now=now)
        require(current['orders']==proposal['orders'] and current['target_quantities']==proposal['target_quantities'],'REFERENCE_NOT_ACCEPTABLE')
        return proposal
