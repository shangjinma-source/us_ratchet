"""One isolated current-service context read. Never executes startup hooks/model."""
import inspect,json,sys,time,threading,cProfile,pstats
from hashlib import sha256
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.research.snapshot_timing_probe_20261105 import instrument_router


def main():
    from data.strategy_unified_server_preparation_v32 import build_unified_server_preparation_v32
    from data.strategy_account_runtime import ScopedAccountStore
    from core.strategy_monthly_target_store import StrategyMonthlyTargetStore
    from data.strategy_account_rolling_router import RollingMonthlyRuntimeRouter
    output=ROOT/'tmp/news_context_cprofile_v32_20261105'
    output.mkdir(exist_ok=False)
    active_path=ROOT/'config/strategy_server_active.json';active_raw=active_path.read_bytes();active=json.loads(active_raw)
    configuration_raw=(ROOT/active['configuration_path']).read_bytes()
    assert sha256(configuration_raw).hexdigest()==active['configuration_sha256'],'ACTIVE_CONFIGURATION_HASH_MISMATCH'
    assert json.loads(configuration_raw)['schema']=='CURRENT_ADVICE_UNIFIED_PREPARATION_V32','EXPLICIT_V32_CONFIGURATION_REQUIRED'
    account=ScopedAccountStore(ROOT/'data/strategy_account/real_strategy.sqlite3')
    targets=StrategyMonthlyTargetStore(ROOT/'data/strategy_account/monthly_targets.sqlite3')
    before=(account.read(),targets.current())
    threads={t.ident for t in threading.enumerate()}
    started=time.monotonic()
    prepared=build_unified_server_preparation_v32(root=ROOT,configuration_path=active['configuration_path'],configuration_sha256=active['configuration_sha256'])
    build_seconds=time.monotonic()-started;print('BUILT',build_seconds,flush=True)
    route=next(r for r in prepared['router'].routes if r.path=='/api/news/investment-review')
    service=inspect.getclosurevars(route.endpoint).nonlocals['service']
    router=service.input_operation.__self__
    while not isinstance(router,RollingMonthlyRuntimeRouter):router=router.monthly
    events=[];restore=instrument_router(router,events)
    try:
        profile=cProfile.Profile()
        started=time.monotonic();value=profile.runcall(service.context);elapsed=time.monotonic()-started
        profile.dump_stats(str(output/'context.prof'))
        with (output/'cumulative.txt').open('w',encoding='utf-8') as stream:
            pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('cumulative').print_stats(55)
        with (output/'self_time.txt').open('w',encoding='utf-8') as stream:
            pstats.Stats(profile,stream=stream).strip_dirs().sort_stats('tottime').print_stats(30)
    finally:restore()
    assert (account.read(),targets.current())==before,'FINANCIAL_STATE_CHANGED'
    assert active_path.read_bytes()==active_raw,'ACTIVE_CONFIGURATION_CHANGED'
    assert {t.ident for t in threading.enumerate()}==threads,'UNEXPECTED_THREAD_STARTED'
    report=dict(build_seconds=build_seconds,context_seconds=elapsed,events=events,
        provider_seconds=sum(e['seconds'] for e in events if e['kind']=='provider'),
        outer_lock_wait_seconds=sum(e['wait_seconds'] for e in events if e['kind']=='lock' and e['depth']==1),
        account_unchanged=True,target_unchanged=True,model_calls=0,startup_hooks_executed=False,
        independent_process_no_production_lock_contention=True,
        active_configuration_sha256=sha256(active_raw).hexdigest(),
        context_result_sha256=sha256(json.dumps(value,sort_keys=True).encode()).hexdigest(),
        source_hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),ROOT/'scripts/research/snapshot_timing_probe_20261105.py']})
    (output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)

if __name__=='__main__':main()
