"""Explicit server-source bridge for current-quote new-cash paper proposals.

No default account, network, selection, registration or production mounting.
Resolver and account_reader are server-owned read-only providers. A source hash
is local byte integrity, never authentication of an external issuer or account.
"""
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime
from hashlib import sha256
from threading import RLock
import re
from data.current_cash_portfolio_research import ResearchExpiredError
from data.current_quantity_v2_current_cash_plan import (
    SCOPE,canonical,closure,require,build_current_cash_plan)
from data.current_quantity_v2_current_cash_ledger_adapter import (
    freeze_current_cash_proposal,build_recorded_cash_proposal)


class CurrentQuantityV2CurrentCashService:
    """resolver(decision_id)->{capital_decision,account_state,genesis_declaration,execution_package}.

    account_reader(account_id) returns the full explicit strategy account state;
    no missing orders/reservations/rights are filled with empty defaults. The
    initial resolver is called under the existing store transaction; its readers
    must not call back into that store or acquire its write lock.
    """
    def __init__(self,*,resolver,account_reader,clock,prepare=None):
        self.resolver=resolver;self.account_reader=account_reader;self.clock=clock
        self.prepare=prepare
        self._lock=RLock();self._proposals=OrderedDict();self._cache_bytes=0

    def _read(self,decision_id):
        require(type(decision_id)is str and re.fullmatch('[a-f0-9]{64}',decision_id),'INVALID_DECISION_ID')
        supplied=deepcopy(self.resolver(decision_id))
        require(type(supplied)is dict and set(supplied)=={'capital_decision','account_state','genesis_declaration','execution_package'},'SOURCE_INPUT_FIELDS')
        require(supplied['capital_decision']['decision_id']==decision_id,'DECISION_BINDING_MISMATCH')
        files,pins,docs=closure(supplied['execution_package']) # Every original file on each source read.
        identity={k:deepcopy(v) for k,v in supplied.items() if k!='execution_package'}
        identity['execution_package']=dict(documents=deepcopy(docs),source_hashes=deepcopy(pins))
        identity=sha256(canonical(identity)).hexdigest()
        account=supplied['account_state']
        require(self.account_reader(account['account_id'])==account,'ACCOUNT_CHANGED')
        return supplied,identity

    @staticmethod
    def _time(now):
        require(isinstance(now,datetime) and now.tzinfo is not None,'AWARE_CLOCK_REQUIRED')
        return now

    def preview(self,decision_id):
        base=dict(decision_id=decision_id,research_only=True,execution_blocked=True,orders_created=False,
            real_account=False,source_authenticated=False,corporate_actions_complete=False,account_mutated=False)
        try:
            if self.prepare is not None:
                require(callable(self.prepare),'INVALID_SOURCE_PREPARER')
                self.prepare(decision_id)
            supplied,identity=self._read(decision_id)
            require(self._read(decision_id)[1]==identity,'PROPOSAL_SOURCE_CHANGED')
            now=self._time(self.clock())
            plan=build_current_cash_plan(**supplied,now=now.isoformat())
            require(plan['status']=='READY',plan.get('reason','CURRENT_CASH_PLAN_UNAVAILABLE'))
            pure=freeze_current_cash_proposal(plan,supplied['execution_package'])
            require(self._read(decision_id)[1]==identity,'PROPOSAL_SOURCE_CHANGED')
            # Final clock also covers decoding, hashing and finite evidence freezing.
            final=self._time(self.clock())
            require(final>=now,'ACCEPTANCE_BEFORE_PROPOSAL')
            current=build_recorded_cash_proposal(**dict(pure['causal_inputs'],now=final.isoformat()))
            require(current['orders']==pure['orders'],'REFERENCE_NOT_ACCEPTABLE')
            if pure['orders']:
                size=len(canonical(pure));require(size<=32*1024*1024,'PROPOSAL_CACHE_ENTRY_LIMIT')
                with self._lock:
                    old=self._proposals.pop(pure['proposal_id'],None)
                    if old:self._cache_bytes-=old['size']
                    self._proposals[pure['proposal_id']]=dict(proposal=deepcopy(pure),identity=identity,size=size)
                    self._cache_bytes+=size
                    while len(self._proposals)>32 or self._cache_bytes>64*1024*1024:
                        _,removed=self._proposals.popitem(last=False);self._cache_bytes-=removed['size']
            result=deepcopy(pure)
            result.pop('causal_inputs');result.pop('execution_references')
            # Rows contain only compact reference times/prices, no raw or evidence paths.
            for row in result['rows']:
                row.pop('source_hashes',None)
            result['securities']={sid:{k:row[k] for k in ('security_id','ticker','issuer_id','security_class','currency')}
                for sid,row in result['securities'].items()}
            result.update(base,target_scope=SCOPE,source_bytes_verified=False,current_execution_bytes_verified=True,
                historical_source_bytes_reverified=False,ledger_acceptance_supported=True,action=plan['action'],
                frozen_dollar_allocations_exact={r['security_id']:r['frozen_dollar_allocation'] for r in plan['rows']},
                quote_validation_checked_at=final.isoformat())
            if not pure['orders']:result['proposal_id']=None
            return result
        except ResearchExpiredError:
            return dict(base,status='UNAVAILABLE',reason='RESEARCH_SNAPSHOT_EXPIRED',orders=[],proposal_id=None,
                execution_target_id=None,source_bytes_verified=False)
        except (ValueError,TypeError,KeyError,IndexError,AttributeError,OSError,ArithmeticError) as error:
            return dict(base,status='UNAVAILABLE',reason=str(error),orders=[],proposal_id=None,
                execution_target_id=None,source_bytes_verified=False)

    def initial_resolver(self,account_id,proposal_id,now):
        """Return immutable preview proposal after full-source/current-account revalidation."""
        with self._lock:
            require(proposal_id in self._proposals,'PROPOSAL_UNKNOWN_OR_EVICTED')
            cached=deepcopy(self._proposals[proposal_id])
        pure=cached['proposal'];inputs=pure['causal_inputs']
        require(pure['account_id']==account_id,'PROPOSAL_ACCOUNT_MISMATCH')
        now=self._time(now)
        require(datetime.fromisoformat(inputs['now'])<=now,'ACCEPTANCE_BEFORE_PROPOSAL')
        decision_id=inputs['capital_decision']['decision_id']
        supplied,identity=self._read(decision_id)
        require(identity==cached['identity'],'PROPOSAL_SOURCE_CHANGED')
        require(self._read(decision_id)[1]==identity,'PROPOSAL_SOURCE_CHANGED')
        require(supplied['account_state']==inputs['account_state'],'ACCOUNT_CHANGED')
        current=build_recorded_cash_proposal(**dict(inputs,now=now.isoformat()))
        require(current['orders']==pure['orders'] and pure['orders'],'REFERENCE_NOT_ACCEPTABLE')
        return dict(proposal=pure,account_state=deepcopy(supplied['account_state']))
