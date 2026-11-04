"""Unmounted live-binding check held under the three-source write barrier.

Successful entry is consistency only, not source/broker authority or activation.
The caller must keep the scope open through its eventual coordinated switch.
"""
from contextlib import contextmanager
from hashlib import sha256
import json
from core.strategy_account_ledger import require
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from data.strategy_split_bundle_v1 import verify_split_bundle
from data.strategy_account_split_migration_v1 import checked_path
from data.strategy_split_write_barrier_v1 import freeze_split_sources


@contextmanager
def bound_split_sources(*, paths, bundle_directory, expected_manifest_sha256, timeout=1.0):
    directory=checked_path(bundle_directory)
    with freeze_split_sources(paths=paths,timeout=timeout) as frozen:
        raw=(directory/'complete.json').read_bytes()
        require(sha256(raw).hexdigest()==expected_manifest_sha256,'SPLIT_LIVE_MANIFEST_CHANGED')
        manifest=verify_split_bundle(directory)
        inputs=json.loads((directory/'inputs.json').read_bytes())
        account=StrategyAccountStore(frozen['account']).read()
        target=StrategyMonthlyTargetStore(frozen['target']).current()
        risk=MonthlyPeakExitStore(frozen['risk']).read(manifest['account_id'])
        require(account is not None and account['account_id']==manifest['account_id']
                and account['revision']==manifest['source_account_revision'],'SPLIT_LIVE_ACCOUNT_CHANGED')
        require(target==inputs['target'],'SPLIT_LIVE_TARGET_CHANGED')
        require(risk==inputs['risk_before'],'SPLIT_LIVE_RISK_CHANGED')
        require((directory/'complete.json').read_bytes()==raw,'SPLIT_LIVE_MANIFEST_CHANGED')
        yield dict(manifest=manifest,source_consistency_verified=True,
                   production_activated=False,source_authenticated=False,broker_evidence_authenticated=False)
