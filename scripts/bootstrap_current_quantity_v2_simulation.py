"""Explicit fresh-cash isolated bootstrap. Default is offline read-only preflight."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

if __package__ in (None, ''): sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backtest.current_quantity_v2_close_capture_simulation import _read
from backtest.current_quantity_v2_simulation_bootstrap import bootstrap
from backtest.current_quantity_v2_simulation_store import SimulationStore
from backtest.current_quantity_v2_minute_day_fill import MODEL, exact
from data.current_quantity_v2_difference_plan import require, stamp
from data.current_quantity_v2_service_factory import create_service
from data.current_quantity_v2_verified_snapshot_bundle import VerifiedSnapshotBundleService
from data.current_quantity_v2_source_admission_policy import SOURCE_WITHDRAWALS
from data.current_quantity_v2_current_cash_sources import CurrentQuantityV2CurrentCashSources
from data.current_quantity_v2_current_cash_service import CurrentQuantityV2CurrentCashService
from data.current_quantity_v2_pullback_runtime import EXPERIMENTAL_POLICY, LazyPullbackCapStore
from data.current_quantity_v2_execution_month import validate_execution_month
from data.current_research_intraday_execution import fetch_intraday_chart
from data.current_quantity_v2_simulation_paths import validate_cap_configuration
from api.current_quantity_v2_difference import PUBLIC_SOURCE_REASONS, public_source_reason


def public_bootstrap_reason(error):
    """Allow only fixed codes; never render source exception text or URLs."""
    reason=str(error)
    prefix='BOOTSTRAP_FRESH_PROPOSAL_UNAVAILABLE:'
    if reason.startswith(prefix) and reason[len(prefix):] in PUBLIC_SOURCE_REASONS | {'SOURCE_UNAVAILABLE'}:
        return reason
    if reason in PUBLIC_SOURCE_REASONS | {
        'BOOTSTRAP_ALREADY_EXISTS','BOOTSTRAP_RESEARCH_UNAVAILABLE',
        'BOOTSTRAP_SOURCE_BINDING_CHANGED','BOOTSTRAP_1000_WINDOW_ELAPSED',
        'BOOTSTRAP_ATTEMPT_REQUIRES_REVIEW','ACTUAL_ACCEPTANCE_SESSION_REQUIRED',
        'INVALID_BOOTSTRAP_CONFIG','PINNED_IDENTITY_MANIFEST_REQUIRED',
    }:
        return reason
    return type(error).__name__


def absolute(value):
    require(type(value) is str and Path(value).is_absolute(), 'EXPLICIT_ABSOLUTE_BOOTSTRAP_PATH_REQUIRED')
    return Path(value).resolve()


def remaining_calendar(schedule, now, schedule_path):
    require(schedule['schema']=='SCHEDULED_REGULAR_SESSIONS_V1','SIMULATION_SCHEDULE_SCHEMA')
    day=stamp(now).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    rows=schedule['sessions'];dates=[row['date'] for row in rows]
    require(dates==sorted(set(dates)) and day in dates,'ACTUAL_ACCEPTANCE_SESSION_REQUIRED')
    selected=[row for row in rows if row['date']>=day]
    for row in selected:
        opening,closing=stamp(row['open_at']),stamp(row['close_at'])
        require(opening<closing and opening.astimezone(ZoneInfo('America/New_York')).date().isoformat()==row['date']
                and closing.astimezone(ZoneInfo('America/New_York')).date().isoformat()==row['date'], 'INVALID_SCHEDULE_SESSION')
    return dict(session_dates=[row['date'] for row in selected],closes={row['date']:row['close_at'] for row in selected},
                source_references=[schedule_path])


def preflight(*,config_path,config_sha256,now):
    path=absolute(str(config_path));config=json.loads(_read(path.parent,path.name,{path.name:config_sha256}))
    require(set(config)-{'identity_manifest_path'}=={'schema','root','descriptor','initial_month','schedule','simulation_id','account_id',
            'initial_cash','model','fees','database_path','audit_directory','pullback','scope'}
            and config['schema']=='ISOLATED_CURRENT_CASH_BOOTSTRAP_V1'
            and config['scope']=='CONDITIONAL_RESEARCH_ONLY_NOT_BROKER_OR_FORWARD_CERTIFICATION', 'INVALID_BOOTSTRAP_CONFIG')
    require(config['model']==MODEL and exact(config['initial_cash'])>0,'EXPLICIT_BOOTSTRAP_MODEL_CASH_REQUIRED')
    require(all(type(config[k]) is str and config[k].strip() for k in ('simulation_id','account_id')), 'BOOTSTRAP_ID_REQUIRED')
    root=absolute(config['root']);db=absolute(config['database_path']);audit=absolute(config['audit_directory'])
    pullback=config['pullback']
    require(type(pullback) is dict and set(pullback)=={'policy','database_path'}
            and pullback['policy']==EXPERIMENTAL_POLICY,'CURRENT_EXPERIMENTAL_PULLBACK_REQUIRED')
    cap=absolute(pullback['database_path'])
    validate_cap_configuration(simulation_database=db,cap_database=Path(pullback['database_path']),policy=pullback['policy'])
    require(db!=cap and not db.is_relative_to(audit) and not cap.is_relative_to(audit), 'BOOTSTRAP_STORAGE_PATH_COLLISION')
    store=SimulationStore(db)
    if db.exists():
        try:store.read(config['simulation_id'])
        except ValueError as error:
            if str(error)!='SIMULATION_NOT_FOUND':raise
        else:raise ValueError('BOOTSTRAP_ALREADY_EXISTS')
    values={}
    for key in ('descriptor','initial_month','schedule','fees'):
        item=config[key];require(type(item) is dict and set(item)=={'path','sha256'},'BOOTSTRAP_PINNED_DOCUMENT_REQUIRED')
        values[key]=json.loads(_read(root,item['path'],{item['path']:item['sha256']}))
    research=VerifiedSnapshotBundleService(create_service(root=root,descriptor_path=config['descriptor']['path'],
        descriptor_sha256=config['descriptor']['sha256']),source_withdrawals=SOURCE_WITHDRAWALS)
    descriptor,data,_,files=research._load()
    research.require_source_hashes_admitted(descriptor['source_hashes'])
    if 'identity_manifest_path' in config:
        require(config['identity_manifest_path'] in descriptor['source_hashes'],'PINNED_IDENTITY_MANIFEST_REQUIRED')
    day=stamp(now).astimezone(ZoneInfo('America/New_York')).date().isoformat()
    month=values['initial_month'];month_files=dict(files);month_pins=dict(descriptor['source_hashes'])
    for name,h in month['source_hashes'].items():month_files[name]=_read(root,name,{name:h});month_pins[name]=h
    validate_execution_month(month,decision_date=data['search_arguments']['decision_date'],
        original_pins=descriptor['source_hashes'],session=day,files=month_files,pins=month_pins)
    calendar=remaining_calendar(values['schedule'],now,config['schedule']['path'])
    for name,h in values['schedule'].get('source_hashes',{}).items():_read(root,name,{name:h})
    fees=values['fees']
    require(set(fees)=={'schema','status','fixed_per_order','notional_rate'}
            and fees['schema']=='EXPLICIT_SIMULATION_FEE_MODEL_V1'
            and fees['status']=='MODELLED_FEES_NOT_BROKER_FEES'
            and exact(fees['fixed_per_order'])>=0 and exact(fees['notional_rate'])>=0,
            'EXPLICIT_MODELLED_FEE_POLICY_REQUIRED')
    return dict(config=config,root=root,store=store,research=research,calendar=calendar,
        summary=dict(status='PREFLIGHT_OK_NOT_STARTED',simulation_id=config['simulation_id'],initial_cash=config['initial_cash'],
                     first_session=calendar['session_dates'][0],last_session=calendar['session_dates'][-1],
                     model=config['model'],fee_model=fees,selection_fee_bps=data['search_arguments']['fee_bps'],
                     pullback_policy=pullback['policy'],network_used=False,search_calls=0,account_created=False))


def run(*,config_path,config_sha256,execute=False,clock=None,fetch=None):
    clock=clock or (lambda:datetime.now(timezone.utc))
    checked=preflight(config_path=config_path,config_sha256=config_sha256,now=clock())
    if not execute:return checked['summary']
    config=checked['config'];research=checked['research'];root=checked['root']
    caps=LazyPullbackCapStore(config['pullback']['database_path'],clock=lambda:clock().isoformat(),max_history_rows=512,max_history_bytes=128*1024*1024)
    sources=CurrentQuantityV2CurrentCashSources(root=root,snapshot_service=research,server_account_id=config['account_id'],
        fetch=fetch or fetch_intraday_chart,clock=clock,execution_month_mandate=config['initial_month'],
        **({'identity_manifest_path':config['identity_manifest_path']} if 'identity_manifest_path' in config else {}),
        pullback_policy=config['pullback']['policy'],pullback_cap_store=caps,audit_storage_root=config['audit_directory'])
    service=CurrentQuantityV2CurrentCashService(resolver=sources.resolve,account_reader=sources.account_reader,
                                               prepare=sources.capture,clock=clock)
    view=research.calculate(config['initial_cash'])
    require(view.get('decision_id'), 'BOOTSTRAP_RESEARCH_UNAVAILABLE')
    preview=service.preview(view['decision_id'])
    require(preview.get('status')=='READY' and preview.get('proposal_id'),
            'BOOTSTRAP_FRESH_PROPOSAL_UNAVAILABLE:'+public_source_reason(preview.get('reason')))
    with sources.lock:
        supplied=service.initial_resolver(config['account_id'],preview['proposal_id'],clock())
        # Re-read explicit configuration and source bytes after capture/search;
        # actual bootstrap clock still governs acceptance/initial valuation.
        final=preflight(config_path=config_path,config_sha256=config_sha256,now=clock())
        def guard(pins):
            research.require_source_hashes_admitted(pins)
            bundle=research.verified_snapshot_bundle(view['research_id'])
            require(all(pins.get(path)==digest for path,digest in bundle['source_hashes'].items()),
                    'BOOTSTRAP_SOURCE_BINDING_CHANGED')
        result=bootstrap(store=checked['store'],simulation_id=config['simulation_id'],**supplied,
            initial_cash=config['initial_cash'],model=config['model'],calendar=final['calendar'],
            source_admission_guard=guard,clock=clock)
    return dict(status='CREATED_ISOLATED_SIMULATION',simulation_id=config['simulation_id'],revision=result['revision'],
                accepted_at=result['simulation']['origin']['ledger']['acceptance']['accepted_at'],
                scheduler_activated=False,real_account=False,forward_certified=False)


def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--config',required=True)
    parser.add_argument('--config-sha256',required=True);parser.add_argument('--execute',action='store_true');args=parser.parse_args(argv)
    try:
        result=run(config_path=args.config,config_sha256=args.config_sha256,execute=args.execute)
        print(json.dumps(result));return 0
    except Exception as error:
        print(json.dumps(dict(status='BLOCKED',reason=public_bootstrap_reason(error),error_type=type(error).__name__,created=False)));return 1


if __name__=='__main__':raise SystemExit(main())
