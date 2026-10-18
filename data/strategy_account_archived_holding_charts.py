"""Read held-stock history from one approved archived training source.

Caller must supply the runtime source-pin validation gate and shared router lock.
No runtime admission, market fetch, selection, target creation or account writes.
"""
from copy import deepcopy
import json
from pathlib import Path
from core.strategy_account_ledger import replay, require
from data.strategy_account_runtime_archive import configuration_for_target, require_archived_configuration
from data.strategy_account_holding_charts import StrategyAccountHoldingCharts
from data.strategy_monthly_target_charts import StrategyMonthlyTargetCharts


class ArchivedHoldingCharts:
    def __init__(self, *, root, account_store, account_id, target_store, archive_path,
                 archive_sha256, shared_lock, bootstrap_configuration=None, display_sources=None):
        self.root = Path(root).resolve()
        self.accounts, self.account_id, self.targets = account_store, account_id, target_store
        self.archive_path, self.archive_sha256 = archive_path, archive_sha256
        self.lock = shared_lock
        self.bootstrap = deepcopy(bootstrap_configuration)
        require(display_sources is None or type(display_sources) is dict, 'CHART_DISPLAY_CONFIG_INVALID')
        self.display_sources = deepcopy(display_sources)
        self.reader = StrategyMonthlyTargetCharts(root=self.root,target_service=None)

    def bars(self, *, account_revision, security_id, interval='day', bars=90):
        with self.lock:
            state = self.accounts.read()
            require(state is not None and state['account_id'] == self.account_id, 'ACCOUNT_SCOPE_MISMATCH')
            require(replay(state['account_id'],[event['payload'] for event in state['events']]) == state,
                    'ACCOUNT_REPLAY_MISMATCH')
            require(state['revision'] == account_revision, 'STALE_REVISION')
            require(state['shares'].get(security_id,0) > 0, 'CHART_NOT_HELD')
            names = {event['payload']['identity_evidence']['ticker'] for event in state['events']
                     if event['payload'].get('identity_evidence',{}).get('security_id') == security_id}
            require(len(names) == 1, 'CHART_RECORDED_IDENTITY_REQUIRED')
            ticker = next(iter(names))
            history = self.targets.history()
            def configurations():
                # Only absent SIDs permit fallback; invalid sources never do.
                for target in reversed(history):
                    require(target['payload']['account_id'] == self.account_id, 'TARGET_ACCOUNT_MISMATCH')
                    yield target['target_id'], configuration_for_target(root=self.root,
                        archive_path=self.archive_path,archive_sha256=self.archive_sha256,target=target)
                if self.bootstrap is not None:
                    yield None, require_archived_configuration(root=self.root,
                        archive_path=self.archive_path,archive_sha256=self.archive_sha256,
                        configuration=self.bootstrap)
            for source_target_id, configuration in configurations():
                def pairs(items):
                    value = {}
                    for key,item in items:
                        require(key not in value,'CHART_DUPLICATE_JSON_FIELD')
                        value[key] = item
                    return value
                manifest = json.loads(self.reader._read(configuration['training_manifest'],
                    configuration['training_sha256']),object_pairs_hook=pairs)
                rows = [row for row in manifest['candidates'] if row.get('security_id') == security_id]
                if not rows:
                    continue
                require(len(rows) == 1 and rows[0]['ticker'] == ticker
                        and rows[0]['status'] == 'READY_CONDITIONAL','CHART_IDENTITY_MISMATCH')
                source = StrategyAccountHoldingCharts(root=self.root,account_store=self.accounts,
                    account_id=self.account_id,training_manifest=configuration['training_manifest'],
                    training_sha256=configuration['training_sha256'], display_sources=self.display_sources)
                result = source.bars(account_revision=account_revision,security_id=security_id,
                                     interval=interval,bars=bars)
                current_state = self.accounts.read()
                require(current_state is not None and current_state['account_id'] == self.account_id
                        and current_state['revision'] == account_revision, 'STALE_REVISION')
                latest = self.targets.current()
                require((latest['target_id'] if latest else None)
                        == (history[-1]['target_id'] if history else None),'STALE_TARGET')
                result.update(source_target_id=source_target_id,
                              training_manifest_sha256=configuration['training_sha256'],
                              historical_target_fallback=bool(source_target_id is not None and history
                                  and source_target_id!=history[-1]['target_id']),
                              source_kind='BOOTSTRAP' if source_target_id is None else 'SAVED_TARGET')
                return result
            raise ValueError('HOLDING_CHART_APPROVED_SOURCE_REQUIRED')
