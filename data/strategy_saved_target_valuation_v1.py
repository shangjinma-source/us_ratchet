"""Saved-target read-only valuation; market capture is outside the monthly lock."""
from copy import deepcopy
from hashlib import sha256
from fractions import Fraction
from zoneinfo import ZoneInfo
import json
from core.strategy_account_ledger import canonical,replay
from core.strategy_account_difference import require,timestamp
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_account_monthly_release import validate_account_identity_coverage
from data.strategy_account_target_decision import validate_result as validate_original
from data.strategy_continuous32_target_decision import validate_result as validate_continuous,PROFILE_ID,VERSION
from data.strategy_unified_server_preparation_v7 import _read

NY=ZoneInfo('America/New_York')


class SnapshotValuationServiceV1:
    def __init__(self,*,monthly,root,calendar_reference,validate_sources,clock):
        self.monthly,self.root,self.calendar,self.gate,self.clock=monthly,root,deepcopy(calendar_reference),validate_sources,clock

    def _session(self,now):
        raw,calendar=_read(self.root,self.calendar)
        require(calendar['schema']=='FIXED_EXCHANGE_SESSIONS_V1' and calendar['exchange']=='NASDAQ','VALUATION_CALENDAR_INVALID')
        day=now.astimezone(NY).date().isoformat()
        rows=[row for row in calendar['sessions'] if row['date']==day]
        require(len(rows)<=1,'VALUATION_CALENDAR_DUPLICATE')
        if not rows:return None
        row=rows[0]
        return row if timestamp(row['open'])<=now<timestamp(row['close']) else None

    def _saved(self,state,target,runtime,configuration):
        runtime.selection._pins()
        require(target['payload']['runtime_pins']==runtime.selection.pins,'VALUATION_TARGET_PINS')
        payload=target['payload'];decision=payload['decision'];body=decision['payload'];binding=body['input_binding']
        require(sha256(canonical(payload)).hexdigest()==target['target_id'] and
                sha256(canonical(body)).hexdigest()==decision['decision_id'] and
                sha256(canonical(binding)).hexdigest()==body['input_id'],'VALUATION_TARGET_HASH')
        require(decision['status']=='TARGET_READY' and payload['account_id']==binding['account_id']==state['account_id'],
                'VALUATION_ACCOUNT_BINDING')
        profile=binding.get('selector_profile')
        if profile is None:validator=validate_original
        else:
            require(profile==PROFILE_ID and binding.get('selection_method')==VERSION and binding.get('continuous_iterations')==32,'VALUATION_PROFILE_INVALID')
            validator=validate_continuous
        require(validator(body['search_result'],binding['search_arguments'])==body['target_quantities']==payload['target_quantities'],
                'VALUATION_TARGET_QUANTITIES')
        provider=getattr(runtime.execution_provider,'__self__',None)
        require(type(provider)is StrategyAccountEvidenceProvider,'VALUATION_PROVIDER_REQUIRED')
        require(binding['documents']['training_manifest']==provider.manifest_path and
                binding['source_hashes'].get(provider.manifest_path)==provider.manifest_hash,'VALUATION_TRAINING_BINDING')
        raw=provider._read(provider.manifest_path,provider.manifest_hash);manifest=json.loads(raw)
        historical=deepcopy(binding['historical_search_arguments'])
        require(manifest['decision_date']==historical['decision_date']==binding['training_cutoff_date']==
                timestamp(provider.closed).astimezone(NY).date().isoformat(),'VALUATION_TRAINING_DATE')
        require(type(manifest['source_hashes'])is dict and len(manifest['source_hashes'])<2000,'VALUATION_SOURCE_DOMAIN')
        total=0
        for path,digest in manifest['source_hashes'].items():
            total+=len(provider._read(path,digest));require(total<=128*1024*1024,'VALUATION_SOURCE_BUDGET')
        validate_account_identity_coverage(self.root,configuration,state)
        require(replay(state['account_id'],[e['payload'] for e in state['events']])==state,'VALUATION_ACCOUNT_REPLAY')
        package=dict(files={provider.manifest_path:raw},source_hashes={provider.manifest_path:provider.manifest_hash},
                     documents={'training_manifest':provider.manifest_path})
        return provider,package,historical

    def valuation(self,expected_revision=None):
        started=self.clock()
        with self.monthly.snapshot_operation() as snapshot:
            self.gate();state=deepcopy(self.monthly.accounts.read());target=deepcopy(self.monthly.current())
            require(state is not None,'ACCOUNT_NOT_INITIALIZED')
            require(expected_revision is None or expected_revision==state['revision'],'STALE_REVISION')
            held={sid:q for sid,q in state['shares'].items() if q}
            if not held:return dict(status='EMPTY_HOLDINGS',account_revision=state['revision'],holdings=[],market_value='0',account_mutated=False)
            if target is None:return dict(status='WAIT_SAVED_TARGET',account_revision=state['revision'],holdings=[],account_mutated=False)
            session=self._session(started)
            if session is None:return dict(status='WAIT_REGULAR_SESSION',account_revision=state['revision'],holdings=[],account_mutated=False)
            snapshot=deepcopy(dict(snapshot))
            runtime,configuration=self.monthly._for_target(target)
            configuration=deepcopy(configuration)
            provider,package,historical=self._saved(state,target,runtime,configuration)
            self.gate()
        # No training compile, selector, entry/exit limits, or account writes.
        marks=provider._assemble(deepcopy(state),package,historical,target_quantities={},execution_only=True,valuation_only=True)
        with self.monthly.snapshot_operation() as current_snapshot:
            self.gate()
            require(current_snapshot==snapshot and self.monthly.accounts.read()==state and self.monthly.current()==target,
                    'VALUATION_SNAPSHOT_CHANGED')
            current_runtime,current_configuration=self.monthly._for_target(target)
            require(current_configuration==configuration,'VALUATION_ARCHIVE_CHANGED')
            self._saved(state,target,current_runtime,current_configuration)
            self.gate()
            require(self.monthly.accounts.read()==state and self.monthly.current()==target,'VALUATION_SNAPSHOT_CHANGED')
            finished=self.clock()
            require(finished>=started and self._session(finished)==session,'VALUATION_SESSION_CHANGED')
            rows=[];total=Fraction(0)
            require(set(held)<=set(marks),'VALUATION_MARK_DOMAIN')
            for sid,quantity in sorted(held.items()):
                mark=marks[sid];observed=timestamp(mark['observed_at'])
                require(timestamp(session['open'])<=observed<=finished and (finished-observed).total_seconds()<120,
                        'VALUATION_EXPIRED')
                price=Fraction(mark['price'])
                require(price>0 and mark['security_id']==sid and mark['currency']=='USD','VALUATION_MARK_INVALID')
                value=price*quantity;total+=value
                rows.append(dict(security_id=sid,ticker=mark['ticker'],quantity=quantity,price=str(price),observed_at=mark['observed_at'],market_value=str(value)))
            return dict(status='READY',account_revision=state['revision'],target_id=target['target_id'],holdings=rows,
                market_value=str(total),cash_confirmed=state['cash_confirmation_valid'],
                strategy_total=str(total+Fraction(state['total_uninvested_cash'])) if state['cash_confirmation_valid'] else None,
                valued_at=finished.isoformat(),account_mutated=False,public_actions_may_be_missing=True)

