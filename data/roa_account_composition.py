"""Attach explicitly configured ROA to the already authenticated account service."""
import asyncio,logging
from contextlib import asynccontextmanager
from datetime import datetime,timezone
from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool
from inspect import getclosurevars
from pathlib import Path
from zoneinfo import ZoneInfo
from fastapi.routing import APIRoute
from api.strategy_account import StrategyAccountService
from api.roa_strategy import create_router
from core.strategy_account_difference import require
from data.roa_execution_lifecycle import RoaExecutionLifecycle
from data.roa_strategy_service import RoaStrategyService
from data.roa_daily_signal import RoaDailySignalProvider,load_completed_close_prices
from data.roa_quote_provider import RoaQuoteProvider
from data.roa_session_reader import RoaSessionReader
from data.roa_close_recovery import TrustedCloseRecovery,holdings_at
from data.roa_limit_policy import cent_last_price_limit


def attach_roa(*, prepared, root, configuration, validate_sources, clock=None):
    root=Path(root).resolve();clock=clock or (lambda:datetime.now(timezone.utc))
    routes=[r for r in prepared['router'].routes if isinstance(r,APIRoute) and r.path=='/api/strategy-account' and r.methods=={'GET'}]
    require(len(routes)==1,'ROA_ACCOUNT_ROUTE_REQUIRED')
    account=getclosurevars(routes[0].endpoint).nonlocals.get('service')
    require(type(account) is StrategyAccountService,'ROA_ACCOUNT_SERVICE_REQUIRED')
    require(account.account_id==configuration['account_id'],'ROA_ACCOUNT_SCOPE')
    def local(name):
        path=(root/name).resolve();require(path.is_relative_to(root/'data/strategy_account'),'ROA_STATE_PATH')
        require(not any(p.is_symlink() for p in [path,*path.parents]),'ROA_STATE_SYMLINK');return path
    calendar=RoaSessionReader(root)
    signal=RoaDailySignalProvider(root=root,path=local(configuration['daily_signal_path']),
        expected_contract_hashes=configuration['contract_hashes'],clock=clock,monthly_selections=configuration.get('monthly_selections'),base_input_root=configuration.get('base_input_root'))
    lifecycle=RoaExecutionLifecycle(path=local(configuration['lifecycle_path']),account_id=account.account_id,
        strategy_epoch=configuration['strategy_epoch'],contract_sha256=configuration['contract_sha256'])
    def identities():
        result={r['security_id']:r for r in signal.frozen_roster()}
        for row in account.project(account.store.read())['account']['holdings']:
            identity=account.resolver(row['ticker'])
            require(identity['security_id']==row['security_id'],'ROA_HELD_IDENTITY_CHANGED')
            result[row['security_id']]=identity
        return result
    # A missing execution admission may display plans but cannot fetch/execute orders.
    def limits(price,phase):
        require(configuration.get('execution_admission') is not None,'EXECUTION_ADMISSION_REQUIRED')
        require(configuration['execution_admission']['limit_policy']=='CENT_LAST_PRICE_LIMIT','LIMIT_POLICY_NOT_APPROVED')
        return cent_last_price_limit(price,phase)
    quotes=RoaQuoteProvider(identity_map={},session_reader=calendar,limit_builder=limits,clock=clock)
    def quote_provider(state,sids,session,phase,now):
        validate_sources();quotes.identities=identities()
        return quotes(state,sids,session,phase,now)
    def require_stop_history():
        state=lifecycle.read();last=state.get('last_close');pending=set(state.get('pending',[]))
        if not last or not pending:return
        next_session=next((d for d in calendar.sessions() if d>last),None)
        require(next_session is not None,'WAIT_CLOSE_HISTORY_RECONCILIATION')
        if clock()<datetime.fromisoformat(calendar(next_session)['close_at']):return
        covered=set().union(*(set(e.get('pending',[])) for e in state['events'] if e['phase']=='CLOSE' and e['session']==next_session))
        historical=holdings_at(account.store.read(),calendar(next_session)['close_at'])
        remaining={sid for sid in pending if historical.get(sid,0)>0}
        require(remaining<=covered,'WAIT_CLOSE_HISTORY_RECONCILIATION')
    class Guarded(RoaStrategyService):
        def snapshot(self):
            with self.lock:
                validate_sources();require_stop_history();result=super().snapshot();validate_sources();return result
        def save_cash(self,body):
            validate_sources();return super().save_cash(body)
        def cash_status(self,body):
            validate_sources();return super().cash_status(body)
    service=Guarded(account_service=account,lifecycle=lifecycle,signal_provider=signal,
        session_provider=calendar,quote_provider=quote_provider,clock=clock,
        execution_admission=configuration.get('execution_admission'))
    require(not any(getattr(r,'path','').startswith('/api/strategy-roa/') for r in prepared['router'].routes),'ROA_DUPLICATE_ROUTE')
    prepared['router'].include_router(create_router(coordinator=service))
    def close_prices(session,held):
        validate_sources();ids=identities()
        # Historical actual fills may concern a stock no longer held or selected.
        for event in account.store.read()['events']:
            evidence=event['payload'].get('identity_evidence')
            if evidence and evidence.get('security_id') in held:
                identity=account.resolver(evidence['ticker'])
                require(identity['security_id']==evidence['security_id'],'ROA_CLOSE_IDENTITY_CHANGED')
                ids[identity['security_id']]=identity
        require(set(held)<=set(ids),'ROA_CLOSE_IDENTITY_MISSING')
        capture=load_completed_close_prices(identity_map={s:ids[s] for s in held},session=session,
            now=clock(),session_reader=calendar,evidence_dir=local(configuration['close_evidence_path']))
        pins={row['raw_path']:row['raw_sha256'] for row in capture['evidence'].values()}
        if not held:pins=calendar(session)['source_hashes']
        validate_sources()
        return dict(prices=capture['prices'],source_hashes=pins)
    recovery=TrustedCloseRecovery(account_store=account.store,lifecycle=lifecycle,
        directory=local(configuration['close_recovery_path']),evidence_root=root,
        calendar=calendar,calendar_sessions=calendar.sessions(),price_reader=close_prices,clock=clock)
    def observe_completed_session(session):
        validate_sources()
        result=recovery.observe(session)
        validate_sources()
        return result
    maintenance_status={}
    def maintain_completed_session():
        """Catch up completed exchange sessions with journal-time holdings, not today's shares."""
        now=clock();day=now.astimezone(ZoneInfo('America/New_York')).date().isoformat()
        try:
            validate_sources()
            sessions=calendar.sessions()
            latest=next((d for d in reversed(sessions) if d<=day and datetime.fromisoformat(calendar(d)['close_at'])<=now),None)
            completed=[d for d in sessions if latest is not None and d<=latest]
            if not completed:
                maintenance_status.update(status='WAIT',session=day,reason='WAIT_COMPLETED_SESSION');return
            latest=completed[-1]
            state=lifecycle.read();previous=state.get('last_close')
            if previous:
                with service.lock:recovered=observe_completed_session(previous)
                maintenance_status.update(status='RECOVERED_PRIOR_CLOSE',session=previous,account_revision=recovered['account_revision'])
                state=lifecycle.read()
            starts=[e['session'] for e in state['events'] if e['phase']=='OPEN']
            first=min(starts) if starts else None
            missing=[d for d in completed if (previous is not None and d>previous) or (previous is None and first is not None and d>=first)]
            if missing:
                # Today's already-materialized OPEN is not a historical checkpoint.
                require(not any(e.get('materialized_revision') and e['session']>missing[0] for e in state['events']), 'WAIT_CLOSE_HISTORY_RECONCILIATION')
                for session in missing:
                    with service.lock:
                        require_stop_history()
                        observed=observe_completed_session(session)
                    maintenance_status.update(status='RECOVERED_PRIOR_CLOSE',session=session,account_revision=observed['account_revision'])
            # QQQ market history also recovers when no OPEN plan has ever existed.
            market=signal.refresh_completed()
            validate_sources()
            maintenance_status.pop('reason',None)
            maintenance_status.update(status='COMPLETE',session=latest,account_revision=account.store.read()['revision'],market=market,recovered_sessions=missing,close_scope='OBSERVED_LIFECYCLE_SESSIONS' if previous or first else 'NO_LIFECYCLE_OPEN')
        except Exception as error:
            maintenance_status.update(status='WAIT',session=day,reason=str(error))
            logging.getLogger(__name__).warning('ROA close maintenance deferred: %s',error)
    original=prepared['router']
    @asynccontextmanager
    async def lifespan(app):
        async with original.lifespan_context(app):
            async def loop():
                while True:
                    await run_in_threadpool(maintain_completed_session)
                    await asyncio.sleep(60)
            task=asyncio.create_task(loop())
            try:yield
            finally:
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass
    wrapper=APIRouter(lifespan=lifespan)
    wrapper.routes.extend(original.routes)
    prepared=dict(prepared,router=wrapper)
    return dict(prepared,roa_maintain_completed_session=maintain_completed_session,roa_maintenance_status=maintenance_status,roa_service=service,roa_signal_provider=signal,
        roa_observe_completed_session=observe_completed_session,roa_enabled=True)
