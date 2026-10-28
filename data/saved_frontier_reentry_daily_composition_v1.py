"""Unrouted composition retaining the real base provider and risk preview.

The builder supplies configuration bytes, never browser source references. No
configuration generator, activation, production route or trade authorization is
installed here. Conditional source evidence cannot authorize recovery; this
version preserves unresolved locks until a certified identity path is available.
"""
from copy import deepcopy
from pathlib import Path
from hashlib import sha256
import json
from core.strategy_account_ledger import require
from core.reentry_buy_scope_v1 import digest
from data.saved_frontier_daily_composition_v1 import SavedFrontierDailyComposition
from data.reentry_reference_evidence_v1 import review_reference_interval
from data.reentry_preview_projection_v1 import project_reference_preview
from data.reentry_daily_response_v1 import format_reference_advice, POLICY_ID
from data.reentry_publication_guard_v1 import seal_projection,check_publication
from data.strategy_daily_session_capture import stamp

class SavedFrontierReentryDailyComposition:
    def __init__(self, *, root, risk_store, configuration_reader,
                 monthly_service, monthly_view, evidence_reader, execution_provider,
                 clock, policy_execution_enabled=False, policy_id=None, fee_bps=None,
                 sleep=None, monotonic=None):
        require(callable(configuration_reader),'REENTRY_SERVER_CONFIGURATION_REQUIRED')
        self.root=root;self.risk=risk_store;self.configuration_reader=configuration_reader
        self.monthly=monthly_service;self.view=monthly_view;self.reader=evidence_reader;self.clock=clock
        self.base_arguments=dict(monthly_service=monthly_service,monthly_view=monthly_view,
            execution_provider=execution_provider,clock=clock,policy_execution_enabled=policy_execution_enabled,
            policy_id=policy_id,fee_bps=fee_bps,sleep=sleep,monotonic=monotonic)

    def _configuration(self):
        raw=self.configuration_reader();require(type(raw) is bytes,'REENTRY_SERVER_CONFIG_BYTES')
        config=json.loads(raw)
        require(set(config)=={'schema','reference_sources'} and config['schema']=='SERVER_REENTRY_COMPOSITION_CONFIG_V1'
                and type(config['reference_sources']) is dict,'REENTRY_COMPOSITION_CONFIG_SCHEMA')
        return config,sha256(raw).hexdigest()

    def preview(self, *, expected_revision,target_id,expected_proposal_id):
        captured=[]
        def reader(*args,**kwargs):
            answer=self.reader(*args,**kwargs);captured.append(deepcopy(answer));return answer
        config,config_hash=self._configuration()
        # Fresh per-call closure; no shared last-evidence or cross-request state.
        base=SavedFrontierDailyComposition(evidence_reader=reader,**self.base_arguments)
        original=base.preview(expected_revision=expected_revision,target_id=target_id,
                              expected_proposal_id=expected_proposal_id)
        state=deepcopy(self.monthly.accounts.read());target=deepcopy(self.monthly.current())
        require(state['revision']==expected_revision and target['target_id']==target_id,'REENTRY_BASE_BINDING_CHANGED')
        proposal=deepcopy(self.view.require_proposal(target_id=target_id,expected_proposal_id=expected_proposal_id))
        risk=deepcopy(self.risk.read(state['account_id']));reference=deepcopy(self.risk.read_reference(state['account_id']))
        binding=dict(account_id=state['account_id'],account_revision=expected_revision,target_id=target_id,proposal_id=expected_proposal_id)
        def unchanged(expected_reference):
            self.monthly.validate_current_target_pins()
            require(self.monthly.accounts.read()==state and self.monthly.current()==target and
                self.view.require_proposal(target_id=target_id,expected_proposal_id=expected_proposal_id)==proposal,
                'REENTRY_CURRENT_BINDING_CHANGED')
            require(self.risk.read(state['account_id'])==risk,'REENTRY_ORIGINAL_RISK_CHANGED')
            require(self.risk.read_reference(state['account_id'])==expected_reference,'REENTRY_REFERENCE_CHANGED')
            require(self._configuration()[1]==config_hash,'REENTRY_CONFIGURATION_CHANGED')
        def preserved(status=None,reason=None):
            unchanged(reference)
            output=deepcopy(original)
            output.update(policy_id=POLICY_ID,base_policy_id=original.get('policy_id'),production_released=False,
                reference_projection=dict(schema='REFERENCE_PROJECTION_SUMMARY_V1',projection_sha256=digest(original),
                    reference_version=reference['version'] if reference else 0,reference_state_sha256=digest(reference),
                    configuration_sha256=config_hash,buy_status={}),reference_mode='ORIGINAL_NO_BUY_PATH_PRESERVED')
            if status is not None:output.update(status=status,reason=reason,new_orders=[],reference_quotes={},difference={})
            return output
        if reference is None:return preserved('WAIT','WAIT_EXPLICIT_REFERENCE_ACTIVATION')
        if original['status']!='READY':return preserved() # Original WAIT/HOLD never upgraded.
        decision=risk['session_date'];effective=original['effective_target_quantities']
        buys=sorted(s for s,q in effective.items() if q>state['shares'].get(s,0))
        ledger_targets=original['difference']['binding']['target_quantities']
        if ledger_targets!=effective or not buys:
            # Existing zero-cash/data-wait helper certifies a SELL-only subset.
            # It must not be inflated into full-target prices or BUY permission.
            require(not any(o['side']=='BUY' for o in original['new_orders']),'REENTRY_SUBSET_BUY_FORBIDDEN')
            unchanged(reference);current=stamp(self.clock())
            require(stamp(original['risk_valid_from'])<=current<stamp(original['risk_valid_until']),'REENTRY_ORIGINAL_EXPIRED')
            for quote in original['reference_quotes'].values():
                require(current<stamp(quote['reference_valid_until']),'REENTRY_ORIGINAL_QUOTE_EXPIRED')
            return preserved()
        reviews={}
        for origin,lock in reference['locks'].items():
            source=config['reference_sources'].get(origin)
            if source is None:continue
            result=review_reference_interval(root=self.root,configuration_reference=source,lock=lock,
                decision_session=decision,as_of=stamp(self.clock()).isoformat())
            reviews[origin]=result
            # Current reviewer explicitly does NOT certify a closed identity domain.
            # Its observed price chain cannot alone remove a lock or authorize other BUYs.
            # No production authority for a closed domain is installed in this version.

        unchanged(reference)
        # Until a separately certified closed identity/unit interval is available,
        # do not mutate reference state or promote conditional observations to a
        # scope certificate. All unresolved locks block BUYs; SELLs remain intact.
        proofs=[]
        projected=project_reference_preview(account=state,original_preview=original,reference_state=reference,
            decision_session=decision,scope_proofs=proofs,now=stamp(self.clock()).isoformat())
        response=format_reference_advice(original_preview=original,projection=projected,account=state,configuration_sha256=config_hash)
        seal=seal_projection(projection=projected,configuration_sha256=config_hash)
        unchanged(reference)
        for reviewed in reviews.values():
            for name,expected in (reviewed.get('evidence') or {}).get('source_hashes',{}).items():
                path=(Path(self.root)/name).resolve()
                require(path.is_relative_to(Path(self.root).resolve()) and sha256(path.read_bytes()).hexdigest()==expected,
                        'REENTRY_REFERENCE_SOURCE_CHANGED')
        current_state=self.monthly.accounts.read();current_target=self.monthly.current()
        current_proposal=self.view.require_proposal(target_id=target_id,expected_proposal_id=expected_proposal_id)
        checked=check_publication(projection=projected,seal=seal,
            current_binding=dict(account_id=current_state['account_id'],account_revision=current_state['revision'],
                target_id=current_target['target_id'],proposal_id=current_proposal['proposal_id']),
            current_reference_state=self.risk.read_reference(state['account_id']),
            current_configuration_sha256=self._configuration()[1],now=stamp(self.clock()).isoformat())
        # No source files, account snapshots or private commit contexts escape.
        return dict(response,publication_check=checked,publication_seal=seal,
                    requires_publication_check=False,production_released=False,
                    source_coverage='CONDITIONAL_PROVIDER_AND_CURRENT_OFFICIAL_NOTICE_SCOPE')
