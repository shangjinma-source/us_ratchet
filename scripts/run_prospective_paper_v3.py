"""Configured V3 monthly-chain runner; existing registration only, explicit initialization."""
import argparse
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath

from data.strategy_paper_application_descriptor_v2 import require, stamp, classify_window
from data.strategy_daily_session_capture import reject_links
from backtest.current_strategy_prospective_paper_book_v2 import _context
from backtest.current_strategy_prospective_paper_admission_store_v2 import ProspectivePaperAdmissionStore
from backtest.current_strategy_prospective_paper_admission_reader_v2 import registered_selection
from backtest.current_strategy_prospective_paper_coordinator_v2 import ProspectivePaperCoordinator
from backtest.current_strategy_prospective_paper_run_once_v2 import ProspectivePaperRunOnce
from data.strategy_prospective_paper_daily_context_v2 import CapturedPaperDailyContext
from data.strategy_prospective_paper_selection_v2 import verify_prospective_target
from data.strategy_account_identity import PinnedStrategyIdentity
from backtest.current_strategy_paper_bootstrap_v2 import initialize_registered_paper
from data.strategy_account_evidence_provider import StrategyAccountEvidenceProvider
from data.strategy_prospective_paper_selection_sources_v2 import capture_selection_sources
from data.strategy_paper_application_descriptor_v2 import NY
from data.strategy_paper_monthly_training_bridge_v2 import load_monthly_training
from scripts.run_paper_monthly_chain_v3 import load_published_month, run as maintain_monthly_chain

SOURCE='scripts/run_prospective_paper_v3.py'


def training_route(config, app, at):
    """Seed is usable only in the registered first month when a policy follows."""
    seed=bool(config.get('selection_training_manifest'))
    registry=bool(config.get('selection_monthly_registry'))
    policy=bool(config.get('selection_monthly_policy'))
    require(not (registry and (seed or policy)), 'PAPER_RUNTIME_TRAINING_ROUTE_CONFLICT')
    if seed and policy:
        month=stamp(at).astimezone(NY).strftime('%Y-%m')
        first=app['plan']['first_session']['date'][:7]
        require(month>=first,'PAPER_RUNTIME_BEFORE_INITIAL_MONTH')
        return 'seed' if month==first else 'policy'
    return 'seed' if seed else 'policy' if policy else 'registry' if registry else None


def require_current_month_training(*, historical, training_closed_at, calendar_bytes, now):
    """Do not relabel an old fixed training snapshot as a new monthly selection."""
    current=stamp(now);month=current.astimezone(NY).strftime('%Y-%m')
    sessions=json.loads(calendar_bytes)['sessions']
    previous=[row for row in sessions if row['date'][:7]<month]
    require(previous and any(row['date'][:7]==month for row in sessions),
            'PAPER_MONTHLY_TRAINING_CALENDAR_COVERAGE')
    boundary=max(previous,key=lambda row:row['date'])
    previous_month=(current.astimezone(NY).date().replace(day=1)-timedelta(days=1)).strftime('%Y-%m')
    require(boundary['date'][:7]==previous_month,'PAPER_MONTHLY_TRAINING_CALENDAR_COVERAGE')
    closed=stamp(training_closed_at)
    require(historical['decision_date']==closed.astimezone(NY).date().isoformat(),
            'PAPER_MONTHLY_TRAINING_DATE_MISMATCH')
    require(stamp(boundary['close'])<=closed<=current,
            'PAPER_MONTHLY_TRAINING_REFRESH_REQUIRED')
    require(any(row['date']==historical['decision_date'] and stamp(row['close'])==closed
                for row in sessions), 'PAPER_MONTHLY_TRAINING_CLOSE_NOT_REGISTERED')


def load_runner(*,root,configuration_path,expected_sha256,clock=None,transports=None,initialize=False,initialize_if_due=False):
    root=Path(root).absolute();reject_links(root)
    clock=clock or (lambda:datetime.now(timezone.utc))
    def read(reference):
        name=reference['path']
        require(type(name) is str and '\\' not in name and ':' not in name and
                not PurePosixPath(name).is_absolute() and all(p not in ('','.','..') for p in name.split('/')),
                'PAPER_RUNTIME_SOURCE_PATH')
        path=root/name;reject_links(path)
        require(path.is_file() and path.stat().st_nlink==1,'PAPER_RUNTIME_SOURCE_FILE')
        size=path.stat().st_size
        require(size<=32*1024*1024,'PAPER_RUNTIME_SOURCE_CHANGED')
        # Thousands of small pinned sources must not each request a 32 MiB
        # buffer. Read one extra byte to catch growth; the hash still checks
        # every byte and rejects truncation or replacement during the read.
        with path.open('rb') as stream:raw=stream.read(size+1)
        require(len(raw)<=32*1024*1024 and sha256(raw).hexdigest()==reference['sha256'],
                'PAPER_RUNTIME_SOURCE_CHANGED')
        return raw
    config=json.loads(read(dict(path=configuration_path,sha256=expected_sha256)))
    require(config['schema']=='REGISTERED_PROSPECTIVE_PAPER_RUNTIME_V2','PAPER_RUNTIME_SCHEMA')
    descriptor_raw=read(config['descriptor']);descriptor=json.loads(descriptor_raw)
    authority=dict(descriptor_arguments=dict(descriptor_bytes=descriptor_raw,
        trusted_descriptor_sha256=config['descriptor']['sha256'],approval_bytes=read(config['approval']),
        trusted_approval_sha256=config['approval']['sha256'],calendar_bytes=read(config['calendar']),
        code_bytes={p:read(dict(path=p,sha256=h)) for p,h in descriptor['code_sha256'].items()},
        source_bytes={p:read(dict(path=p,sha256=h)) for p,h in descriptor['source_sha256'].items()}),
        registration_bytes=read(config['registration']),trusted_registration_sha256=config['registration']['sha256'],
        trusted_integration_review_sha256=config['integration_review']['sha256'])
    read(config['integration_review'])
    app=_context(authority,clock())
    require(SOURCE in app['code_sha256'],'PAPER_RUNTIME_CODE_PIN_REQUIRED')
    require(set(config)-{'selection_training_manifest','selection_monthly_registry','selection_monthly_policy'}=={'schema','descriptor','approval','calendar','registration','integration_review',
        'daily_sources','daily_release_path','cap_release_path','identity_manifest','securities','training_context'},
        'PAPER_RUNTIME_CONFIG_FIELDS')
    require(set(config['securities'])<=set(config['daily_sources']),'PAPER_RUNTIME_SOURCE_DOMAIN')
    require({'training_manifest_sha256','historical_search_arguments_sha256','training_closed_at',
             'historical_price_basis'}==set(config['training_context']),'PAPER_RUNTIME_TRAINING_FIELDS')
    for name in ('daily_release_path','cap_release_path'):
        require(config[name] in app['source_sha256'],'PAPER_RUNTIME_RELEASE_MISSING')
    requests={}
    for sid,item in config['daily_sources'].items():
        raw=read(item['configuration']);daily=json.loads(raw)
        first_window=daily['schema']=='PAPER_FIRST_DAILY_WINDOW_V2'
        require((first_window and daily['security_id']==sid and 'parent' not in item) or
                (daily['schema']=='SERVER_MONTHLY_WINDOW_CAPTURE_V1' and daily['security']['security_id']==sid),
                'PAPER_RUNTIME_DAILY_TEMPLATE')
        references=[daily['identity']] if first_window else [item['parent'],daily['identity_review']]
        for reference in references:
            require(app['source_sha256'].get(reference['path'])==reference['sha256'],
                    'PAPER_RUNTIME_UNREGISTERED_DAILY_SOURCE')
            read(reference)
        require(read(daily['calendar'])==authority['descriptor_arguments']['calendar_bytes'],
                'PAPER_RUNTIME_DAILY_CALENDAR')
        for reference in daily['source_pins']:read(reference)
        requests[sid]=dict(configuration_bytes=raw,configuration_sha256=item['configuration']['sha256'])
        if not first_window:requests[sid]['parent_reference']=item['parent']
    identity_ref=config['identity_manifest'];read(identity_ref)
    identity=PinnedStrategyIdentity(root,identity_ref['path'],identity_ref['sha256'])
    for sid,security in config['securities'].items():
        require(identity(security['ticker'])['security_id']==sid,'PAPER_RUNTIME_IDENTITY_CHANGED')
    require(not (config.get('selection_monthly_registry') and
        (config.get('selection_training_manifest') or config.get('selection_monthly_policy'))),
        'PAPER_RUNTIME_TRAINING_ROUTE_CONFLICT')
    if config.get('selection_monthly_registry'):read(config['selection_monthly_registry'])
    if config.get('selection_monthly_policy'):
        reference=config['selection_monthly_policy'];read(reference)
        require(app['source_sha256'].get(reference['path'])==reference['sha256'],
                'PAPER_RUNTIME_MONTHLY_POLICY_NOT_REGISTERED')
    training_provider=None
    if config.get('selection_training_manifest'):
        reference=config['selection_training_manifest'];read(reference)
        require(reference['sha256']==config['training_context']['training_manifest_sha256'],
                'PAPER_RUNTIME_SELECTION_TRAINING_CHANGED')
        training_provider=StrategyAccountEvidenceProvider(root=root,manifest_path=reference['path'],
            manifest_sha256=reference['sha256'],training_closed_at=config['training_context']['training_closed_at'],
            market_capture=None,action_capture=None,limits_builder=None,
            output_root=root/app['storage']['evidence']/'selection-source',runtime_pins=app['code_sha256'],clock=clock)
        _,historical=training_provider.training()
        require(set(historical['prices'])<=set(config['securities']),'PAPER_RUNTIME_CANDIDATE_COVERAGE')
    if initialize_if_due:
        complete_path=(root/app['storage']['ledger']).parent/'bootstrap.complete.json'
        reject_links(complete_path)
        for name in ('bootstrap.failed.json','bootstrap.started.json'):
            marker=complete_path.parent/name;reject_links(marker)
            require(not marker.exists() or (name=='bootstrap.started.json' and complete_path.is_file()),
                    'PAPER_RUNTIME_BOOTSTRAP_RECOVERY_REQUIRED')
        if not complete_path.exists():
            phase=classify_window(plan=app['plan'],calendar_bytes=authority['descriptor_arguments']['calendar_bytes'],now=clock())
            require(phase['status']=='FIRST_DECISION_WINDOW','PAPER_SCHEDULE_'+phase['status'])
            initialize=True
    if initialize:
        initialize_registered_paper(root=root,authority=authority,clock=clock)
    namespace=(root/app['storage']['ledger']).parent
    failed=namespace/'bootstrap.failed.json';started=namespace/'bootstrap.started.json'
    complete=namespace/'bootstrap.complete.json'
    for path in (failed,started,complete):reject_links(path)
    require(not failed.exists() and (not started.exists() or complete.is_file()),
            'PAPER_RUNTIME_BOOTSTRAP_RECOVERY_REQUIRED')
    store=ProspectivePaperAdmissionStore(root=root,authority=authority,clock=clock)
    def selection(target):return registered_selection(store,target)
    def verify(result):
        saved=selection(result['decision_id'])
        require(saved['selection_result']==result,'PAPER_RUNTIME_TARGET_CHANGED')
        return verify_prospective_target(result,**saved['selection_arguments'])
    coordinator=ProspectivePaperCoordinator(root=root,authority=authority,
        admission_loader=store.load,target_verifier=verify,clock=clock)
    # Explicit read-only preflight: missing stores cannot become empty accounts.
    coordinator.read();coordinator.current_target_id()
    transports=dict(transports or {})
    selection_transports={k:v for k,v in transports.items() if k in ('market_fetch','halt_fetch','action_fetch','rss_fetch')}
    def monthly_source_loader(book,at):
        provider=training_provider
        closed=config['training_context']['training_closed_at']
        route=training_route(config,app,at)
        if route in ('registry','policy'):
            if route=='policy':
                monthly=load_published_month(root=root,policy_reference=config['selection_monthly_policy'],
                    runtime_pins=app['code_sha256'],output_root=root/app['storage']['evidence']/'monthly-routes',
                    clock=lambda:stamp(at))
            else:
                reference=config['selection_monthly_registry'];read(reference)
                monthly=load_monthly_training(root=root,registry_path=reference['path'],registry_sha256=reference['sha256'],
                    runtime_pins=app['code_sha256'],output_root=root/app['storage']['evidence']/'selection-source',
                    clock=lambda:stamp(at))
            require(set(monthly['securities'])<=set(config['securities']),'PAPER_RUNTIME_MONTHLY_SOURCE_COVERAGE')
            for sid,metadata in monthly['securities'].items():
                require(config['securities'][sid]['ticker']==metadata['ticker'] and
                        identity(metadata['ticker'])['security_id']==sid,'PAPER_RUNTIME_MONTHLY_IDENTITY_CHANGED')
            provider=monthly['provider'];closed=monthly['training_context']['training_closed_at']
        _,current_historical=provider.training()
        require_current_month_training(historical=current_historical,
            training_closed_at=closed,
            calendar_bytes=authority['descriptor_arguments']['calendar_bytes'],now=at)
        admitted=store.load()
        month=clock().astimezone(NY).strftime('%Y-%m')
        return capture_selection_sources(book=book,authority=authority,
            admitted_decisions=admitted['decisions'],admitted_settlements=admitted['settlements'],
            training_provider=provider,identity_resolver=identity,securities=config['securities'],
            output_directory=root/app['storage']['evidence']/'selection-source'/month,
            clock=clock,**selection_transports)
    def snapshot_reader():
        current=coordinator.read()
        return dict(account_id=current['account_id'],account_revision=current['revision'],
                    target_id=coordinator.current_target_id())
    context=CapturedPaperDailyContext(root=root,authority=authority,admission_store=store,
        selection_loader=selection,request_templates=requests,release_path=config['daily_release_path'],clock=clock,
        fetch_daily=transports.pop('daily_fetch',None),fetch_official=transports.pop('daily_official_fetch',None),
        snapshot_reader=snapshot_reader)
    runner=ProspectivePaperRunOnce(root=root,authority=authority,coordinator=coordinator,
        admission_store=store,daily_context=context,identity_resolver=identity,
        securities=config['securities'],training_context=config['training_context'],
        cap_release_path=config['cap_release_path'],clock=clock,
        monthly_source_loader=monthly_source_loader if training_provider or config.get('selection_monthly_registry') or config.get('selection_monthly_policy') else None,**transports)
    def maintenance():
        reference=config.get('selection_monthly_policy')
        if reference is None:return dict(status='MONTHLY_CHAIN_NOT_CONFIGURED',account_writes=False)
        read(reference)
        return maintain_monthly_chain(root=root,policy_reference=reference,execute=True,clock=clock)
    runner.monthly_maintenance=maintenance
    return runner



def run_scheduled(**arguments):
    """Initialize once when due, publish this month's target, then execute paper."""
    try:
        runner=load_runner(**arguments,initialize_if_due=True)
    except ValueError as error:
        if str(error)=='PAPER_SCHEDULE_WAIT_REGISTERED_START':
            return dict(status='WAIT_REGISTERED_START',account_writes=False)
        raise
    book=runner.coordinator.read()
    settlement=None
    if any(order['closed'] is None for order in book['orders'].values()):
        settlement=runner.run_once()
        # A single scheduled wake must not lose today's decision merely because
        # yesterday's DAY orders were settled first. Re-read the authoritative
        # book; a receipt alone never proves all pending orders were closed.
        book=runner.coordinator.read()
        if any(order['closed'] is None for order in book['orders'].values()):
            return settlement
    app=_context(runner.authority,runner.clock())
    phase=classify_window(plan=app['plan'],calendar_bytes=runner.authority['descriptor_arguments']['calendar_bytes'],
        now=runner.clock(),initialized=True)
    if phase['status']!='DAILY_DECISION_WINDOW':
        daily=settlement if settlement is not None else runner.run_once()
        # Preparation can be slow and must not consume the NY 10:00 decision window.
        monthly=runner.monthly_maintenance()
        return dict(daily,monthly_maintenance=monthly)
    publication=runner.publish_monthly()
    if publication['status'] not in ('MONTHLY_TARGET_PUBLISHED','MONTHLY_TARGET_ALREADY_PUBLISHED'):
        return dict(publication,settlement=settlement) if settlement is not None else publication
    result=runner.run_once()
    return dict(result,settlement=settlement) if settlement is not None else result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',required=True)
    parser.add_argument('--configuration-path',required=True)
    parser.add_argument('--expected-sha256',required=True)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--execute',action='store_true')
    mode.add_argument('--initialize',action='store_true')
    mode.add_argument('--publish-monthly',action='store_true')
    mode.add_argument('--scheduled',action='store_true')
    args=vars(parser.parse_args());execute=args.pop('execute');publish=args.pop('publish_monthly');scheduled=args.pop('scheduled')
    try:
        if scheduled:
            args.pop('initialize');result=run_scheduled(**args)
        else:
            runner=load_runner(**args)
            result=runner.publish_monthly() if publish else runner.run_once() if execute else dict(status=(
                'INITIALIZATION_VERIFIED' if args['initialize'] else 'REGISTERED_RUNTIME_READY'),executed=False)
    except Exception as error:
        result=dict(status='BLOCKED',reason=str(error))
    print(json.dumps(result,ensure_ascii=False))
    return 2 if result['status']=='BLOCKED' else 0


if __name__=='__main__':raise SystemExit(main())
