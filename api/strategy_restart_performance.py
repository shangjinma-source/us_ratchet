"""Read-only candidate router. Server supplies pinned files and trusted services.

read_account must return the authenticated full ledger from the formal store;
same-revision snapshots rely on that store's integrity, not client claims.
Historical baseline valuation is allowed, but current valuation must be fresh.
"""
from copy import deepcopy
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction
from datetime import datetime, timezone
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from core.strategy_account_ledger import replay
from data.strategy_restart_performance import restart_performance


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


class RestartPerformanceService:
    def __init__(self, *, baseline_path, baseline_sha256, ledger_path, ledger_sha256,
                 read_account, valuation, clock=None):
        self.files = [(Path(baseline_path), baseline_sha256), (Path(ledger_path), ledger_sha256)]
        self.read_account = read_account
        self.valuation = valuation
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def current(self):
        documents = []
        for path, expected in self.files:
            raw = path.read_bytes()
            require(sha256(raw).hexdigest() == expected, 'BASELINE_SOURCE_CHANGED')
            documents.append(json.loads(raw))
        baseline, old = documents
        require(replay(old['account_id'], [r['payload'] for r in old['events']]) == old,
                'BASELINE_REPLAY_MISMATCH')
        require(old['revision'] == baseline['account_revision'] and
                Fraction(old['total_uninvested_cash']) == Fraction(baseline['cash']) and
                {k:q for k,q in old['shares'].items() if q} ==
                {r['security_id']:r['quantity'] for r in baseline['holdings'] if r['quantity']},
                'BASELINE_LEDGER_BINDING_MISMATCH')
        initial = baseline['valuation_evidence']
        require(initial['valued_at'] == baseline['effective_at'] and
                Fraction(initial['strategy_total']) == Fraction(baseline['initial_equity']),
                'BASELINE_VALUATION_MISMATCH')
        initial_check = restart_performance(baseline=baseline, valuations=[initial])
        require(initial_check['status'] == 'READY_RECONCILED_NO_EXTERNAL_FLOW' and
                initial_check['return_fraction'] == '0', 'BASELINE_VALUATION_MISMATCH')
        before = self.read_account()
        current = self.valuation()
        after = self.read_account()
        now = self.clock()
        valued_at = datetime.fromisoformat(current['valued_at'])
        require(now.utcoffset() is not None and valued_at.utcoffset() is not None,
                'AWARE_VALUATION_TIME_REQUIRED')
        require(0 <= (now-valued_at).total_seconds() <= 120, 'CURRENT_VALUATION_EXPIRED')
        require(before['account_id'] == after['account_id'] == old['account_id'] and
                before['revision'] == after['revision'] == current['account_revision'], 'STALE_REVISION')
        result = restart_performance(baseline=baseline, valuations=[current],
            account_evidence={after['revision']:dict(baseline_account=old,current_account=after)})
        return dict(result, account_revision=after['revision'], initial_equity=baseline['initial_equity'],
                    effective_at=baseline['effective_at'], current_equity=current['strategy_total'],
                    valuation_snapshot=deepcopy(current) if result['status']=='READY_RECONCILED_NO_EXTERNAL_FLOW' else None,
                    orders_created=False)


def create_router(*, service):
    router = APIRouter()

    @router.get('/api/strategy-account/restart-performance')
    async def current(request: Request):
        try:
            require(not request.query_params, 'UNSUPPORTED_PARAMETERS')
            result = await run_in_threadpool(service.current)
            status = 200 if result['status'] == 'READY_RECONCILED_NO_EXTERNAL_FLOW' else 409
        except Exception as error:
            reason = str(error) if isinstance(error, ValueError) and str(error).replace('_','').isupper() else 'PERFORMANCE_UNAVAILABLE'
            result = dict(status='UNAVAILABLE',reason=reason,ledger_mutated=False,orders_created=False)
            status = 409
        return JSONResponse(result,status_code=status,headers={'Cache-Control':'no-store'})
    return router


def build_router(*, root, configuration, read_account, valuation, clock=None):
    """Mount only from a server-owned configuration admitted by release pins."""
    from data.strategy_bounded_source_gate_v1 import _no_links
    import re
    require(set(configuration) == {'schema','baseline','ledger'} and
            configuration['schema'] == 'RESTART_PERFORMANCE_CONFIG_V1', 'PERFORMANCE_CONFIG_FIELDS')
    root = Path(root).resolve()
    files = {}
    for name in ('baseline','ledger'):
        reference = configuration[name]
        require(set(reference) == {'path','sha256'}, 'PERFORMANCE_REFERENCE_FIELDS')
        relative = reference['path']
        require(isinstance(relative,str) and relative.startswith('data/strategy_account/performance_baselines/')
                and '\\' not in relative and ':' not in relative and
                all(part not in ('','.','..') for part in relative.split('/'))
                and re.fullmatch('[0-9a-f]{64}',reference['sha256']), 'PERFORMANCE_REFERENCE_INVALID')
        path = root / relative
        _no_links(path)
        require(path.resolve().is_relative_to(root), 'PERFORMANCE_REFERENCE_ESCAPE')
        files[name+'_path'] = path
        files[name+'_sha256'] = reference['sha256']
    service = RestartPerformanceService(**files,read_account=read_account,valuation=valuation,clock=clock)
    return create_router(service=service)
