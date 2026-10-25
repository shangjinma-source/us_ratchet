"""Loopback-only synthetic browser acceptance, never the user's account or market data.

Usage: python scripts/serve_strategy_cash_browser_fixture.py --run-dir tmp/NEW_DIRECTORY
Uses production components, routers, ledger and V2 selector with tiny synthetic evidence.
"""
from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha256
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'tests')]

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, FileResponse
from api.strategy_account import create_router as account_router, StrategyAccountService
from api.strategy_monthly_target import create_router as target_router
from core.strategy_account_ledger import canonical
from core.strategy_account_store import StrategyAccountStore
from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
from data.strategy_account_target_service import StrategyAccountTargetService, MINIMUM_RUNTIME_PATHS
from data.strategy_monthly_target_service import StrategyMonthlyTargetService, LIFECYCLE_PATHS
from test_strategy_account_target_decision import fixture


def create_app(run_dir):
    run_dir = Path(run_dir).resolve()
    if ROOT / 'tmp' not in run_dir.parents or run_dir.exists():
        raise ValueError('NEW_DIRECTORY_UNDER_REPOSITORY_TMP_REQUIRED')
    run_dir.mkdir(parents=True)
    arguments, original_limits = fixture(str(run_dir))
    now = datetime.fromisoformat(arguments['now'])
    database = run_dir / 'synthetic-account.sqlite3'
    store = StrategyAccountStore(database, clock=lambda: now)
    target_store = StrategyMonthlyTargetStore(run_dir / 'synthetic-target.sqlite3')
    runtime = run_dir / 'runtime'
    pins = {}
    for name in MINIMUM_RUNTIME_PATHS | LIFECYCLE_PATHS:
        raw = (ROOT / name).read_bytes()
        destination = runtime / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw)
        pins[name] = sha256(raw).hexdigest()
    counters = {'selection_evidence_calls': 0, 'execution_evidence_calls': 0, 'requests': []}

    def selection_evidence(state):
        counters['selection_evidence_calls'] += 1
        evidence = {key: deepcopy(arguments[key]) for key in
                    ('source_package', 'manifest_path', 'marks_path', 'unit_review_path')}
        package = evidence['source_package']
        path = evidence['unit_review_path']
        review = json.loads(package['files'][path])
        review['account_revision'] = state['revision']
        package['files'][path] = canonical(review)
        package['source_hashes'][path] = sha256(package['files'][path]).hexdigest()
        return evidence

    selection = StrategyAccountTargetService(
        store=store, evidence_provider=selection_evidence, runtime_root=runtime,
        runtime_pins=pins, maximum_mark_age_seconds=120, execution_fee_bps='0', clock=lambda: now)

    def execution_evidence(state, target, at):
        counters['execution_evidence_calls'] += 1
        limits = deepcopy(original_limits)
        for value in limits.values():
            value.update(ticker='SNDK', buy_evaluated=True, buy_reason='SYNTHETIC_TEST',
                         sell_reason='SYNTHETIC_TEST',
                         reference_valid_until=(now + timedelta(seconds=120)).isoformat())
        return dict(marks=json.loads(arguments['source_package']['files'][arguments['marks_path']]), limits=limits)

    monthly = StrategyMonthlyTargetService(selection_service=selection, target_store=target_store,
                                           execution_provider=execution_evidence, clock=lambda: now)

    def resolver(ticker):
        if ticker != 'SNDK':
            raise ValueError('SYNTHETIC_FIXTURE_ONLY_SUPPORTS_SNDK')
        return dict(ticker=ticker, security_id='B', source_references=['synthetic-identity'],
                    source_hashes={'synthetic-identity': 'a' * 64})

    account_service = StrategyAccountService(database_path=database, account_id='strategy',
                                             resolver=resolver, clock=lambda: now)
    state = account_service.initialize({'event_id': 'fixture-init'})['account']
    for event in [
        dict(event_id='fixture-cash', kind='CASH_CONFIRM', amount='26518.74', cash_basis='TOTAL_UNINVESTED'),
        dict(event_id='fixture-fill', kind='DIRECT_FILL', ticker='SNDK', side='BUY', quantity=14,
             price='1322.21', fees='0', executed_at=(now - timedelta(seconds=60)).isoformat()),
    ]:
        state = account_service.append({'expected_revision': state['revision'], 'event': event})['account']
    app = FastAPI()
    app.include_router(account_router(database_path=database, account_id='strategy', resolver=resolver, clock=lambda: now))
    app.include_router(target_router(service=monthly))

    def evidence():
        current_target = target_store.current()
        return dict(synthetic=True, fixed_clock=now.isoformat(), run_directory=str(run_dir),
                    counters=counters, account=account_service.read(),
                    saved_target=(dict(target_id=current_target['target_id'],
                                       quantities=current_target['payload']['target_quantities'])
                                  if current_target else None),
                    selector_core_calls=selection.current[0].get('core_calls') if selection.current else None)

    @app.middleware('http')
    async def record(request, call_next):
        response = await call_next(request)
        if request.url.path.startswith('/api/'):
            counters['requests'].append(dict(method=request.method, path=request.url.path, status=response.status_code))
            (run_dir / 'evidence.json').write_text(json.dumps(evidence(), ensure_ascii=False, indent=2), encoding='utf-8')
        return response

    @app.get('/fixture/evidence')
    def read_evidence():
        return evidence()

    @app.get('/web/{name}')
    def component(name: str):
        if name not in {'strategy_account.js', 'strategy_monthly_target.js'}:
            from fastapi import HTTPException
            raise HTTPException(404)
        return FileResponse(ROOT / 'web' / name, media_type='application/javascript')

    # Extract the exact production account-to-target hooks. Legacy UI side effects
    # are inert here; neither production server nor any production database is used.
    source = (ROOT / 'web/index.html').read_text(encoding='utf-8')
    hooks = source[source.index('let realStrategyTargetAccountKey = null;'):source.index('let currentPortfolioResearchVersion = null;')]
    mount_start = source.index("  if (!window.StrategyAccountUI?.mount)")
    mounts = source[mount_start:source.index('\n  } catch (_) {', mount_start)]
    html = '''<!doctype html><html lang="zh"><meta charset="utf-8"><title>隔离合成验收</title>
<style>body{font:16px system-ui;margin:24px;color:#123}header{background:#fff0bc;padding:20px}section{border:1px solid #ccd;padding:20px;margin:16px 0}table{width:100%;border-collapse:collapse}td,th{padding:12px;border-bottom:1px solid #ddd;text-align:left}input,select,button{padding:10px;margin:6px}button{cursor:pointer}</style>
<header><h1>隔离合成验收 — 不是实盘建议</h1>合成日期 2026-11-02，合成 SNDK 14 股。所有金额、价格、选股证据仅用于软件验证；数据库只在 tmp。输入 2000 验证扣除已有持仓后的增量建议。</header>
<section id="panelStrategyMonthlyTarget"><h2>今日建议（合成）</h2><div id="strategyMonthlyTarget"></div></section>
<div id="panelCurrentPortfolioPreview" hidden></div><section><h2>操作与持仓（合成）</h2><div id="realStrategyAccount"></div></section>
<script src="/web/strategy_account.js"></script><script src="/web/strategy_monthly_target.js"></script>
<script>const $=id=>document.getElementById(id);let realStrategyCashOnlyBlocked=false;function invalidateRealStrategyAdvice(){};
''' + hooks + '\n' + mounts + '</script></html>'

    @app.get('/', response_class=HTMLResponse)
    def page():
        return html

    (run_dir / 'evidence.json').write_text(json.dumps(evidence(), ensure_ascii=False, indent=2), encoding='utf-8')
    return app


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True)
    args = parser.parse_args()
    import uvicorn
    uvicorn.run(create_app(args.run_dir), host='127.0.0.1', port=8012)
