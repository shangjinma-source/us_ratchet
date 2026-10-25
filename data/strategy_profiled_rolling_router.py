"""Unactivated profiled router; explicit generation only, old target identity retained."""
from core.strategy_account_ledger import require
from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter,_scoped
from data.strategy_account_runtime_archive import configuration_for_target as original_target
from data.strategy_profiled_runtime_archive import configuration_for_target,require_archived_configuration
from data.strategy_profiled_runtime import build_runtime
from data.strategy_profiled_monthly_release import resolve_monthly_runtime
from data.strategy_continuous32_target_decision import PROFILE_ID
from data.strategy_account_monthly_release import validate_account_identity_coverage

class ProfiledRollingMonthlyRuntimeRouter(RollingMonthlyRuntimeRouter):
    def __init__(self,**kwargs):
        require(kwargs.get('migration_control') is None,'PROFILE_MIGRATION_NOT_IMPLEMENTED')
        kwargs.setdefault('runtime_builder',build_runtime)
        super().__init__(**kwargs)

    @_scoped
    def _for_target(self,target):
        profile=target['payload']['decision']['payload']['input_binding'].get('selector_profile')
        if profile is None:
            # Profiled archives retain the exact old configuration too.
            from data.strategy_account_runtime_archive import _document
            from scripts.register_quantity_v2_paper_protocol import safe_path
            from hashlib import sha256
            raw=safe_path(self.root,self.archive_path).read_bytes()
            require(sha256(raw).hexdigest()==self.archive_sha256,'ARCHIVE_SOURCE_CHANGED')
            resolver=original_target if _document(raw).get('schema')=='REAL_STRATEGY_RUNTIME_ARCHIVE_V1' else configuration_for_target
        else:
            require(profile==PROFILE_ID,'UNKNOWN_SELECTOR_PROFILE')
            resolver=configuration_for_target
        config=resolver(root=self.root,archive_path=self.archive_path,archive_sha256=self.archive_sha256,target=target)
        return self._runtime(config),config

    @_scoped
    def _selection_configuration(self,state,reason):
        return resolve_monthly_runtime(root=self.root,registry_path=self.registry_path,registry_sha256=self.registry_sha256,clock=self.clock,account_state=state)

    @_scoped
    def generate(self,*,event_id,reason,expected_revision,previous_target_id):
        require(type(event_id)is str and 0<len(event_id)<=128,'TARGET_EVENT_ID_REQUIRED')
        require(reason in {'INITIAL','MONTHLY_SELECTION','EXPLICIT_RECONFIGURE'},'EXPLICIT_GENERATION_REASON_REQUIRED')
        request=dict(event_id=event_id,reason=reason,expected_revision=expected_revision,previous_target_id=previous_target_id)
        old=self.targets.operation(event_id)
        if old:
            require(old['payload']['request']==request,'TARGET_EVENT_CONFLICT');return old
        previous=self.targets.current()
        require(previous_target_id==(previous['target_id'] if previous else None),'STALE_TARGET')
        state=self.accounts.read();require(state is not None and state['revision']==expected_revision,'STALE_REVISION')
        config=self._selection_configuration(state,reason)
        require_archived_configuration(root=self.root,archive_path=self.archive_path,archive_sha256=self.archive_sha256,configuration=config)
        validate_account_identity_coverage(self.root,config,state)
        return self._runtime(config).generate(**request)
