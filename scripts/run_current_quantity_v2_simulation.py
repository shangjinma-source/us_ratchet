"""Explicit isolated daily runtime. Default preflight is read-only and offline."""
import argparse
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
import sys
from zoneinfo import ZoneInfo

if __package__ in (None,''):sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from backtest.current_quantity_v2_daily_evidence_providers import DailyEvidenceProviders
from backtest.current_quantity_v2_daily_simulation import run_daily
from backtest.current_quantity_v2_simulation_store import SimulationStore
from backtest.current_quantity_v2_simulated_settlement import _references
from backtest.current_quantity_v2_close_capture_simulation import _read
from data.current_quantity_v2_difference_plan import require,stamp
from data.current_quantity_v2_monthly_retarget import active_proposal,active_entry_policy
from data.current_quantity_v2_simulation_origin_files import SimulationOriginFilesReader
from data.current_quantity_v2_source_admission_policy import SOURCE_WITHDRAWALS
from data.current_quantity_v2_verified_snapshot_bundle import VerifiedSnapshotBundleService
from data.current_quantity_v2_bounded_unit_review import BoundedPublicUnitReview
from data.current_quantity_v2_monthly_bounded_review import MonthlyBoundedUnitReview
from data.current_quantity_v2_monthly_origins import MonthlyOriginReader
from data.current_quantity_v2_monthly_composition import MonthlyFileConfiguration
from data.current_quantity_v2_paper_review_provider import DerivedPaperReviewProvider
from data.current_quantity_v2_paper_action_sources import PaperActionEvidenceSources
from data.current_quantity_v2_pullback_runtime import LazyPullbackCapStore
from data.current_quantity_v2_simulation_paths import validate_cap_configuration
from backtest.current_quantity_v2_monthly_simulation import digest


def _absolute(value):
    require(type(value) is str and Path(value).is_absolute(), 'EXPLICIT_ABSOLUTE_RUNTIME_PATH_REQUIRED')
    return Path(value).resolve()


def _fees(config,root,state):
    value=json.loads(_read(root,config['fees_path'],{config['fees_path']:config['fees_sha256']}))
    from backtest.current_quantity_v2_minute_day_fill import exact
    if value.get('schema')=='EXPLICIT_SIMULATION_FEE_MODEL_V1':
        require(set(value)=={'schema','status','fixed_per_order','notional_rate'}
                and value['status']=='MODELLED_FEES_NOT_BROKER_FEES', 'EXPLICIT_MODELLED_FEE_STATUS_REQUIRED')
        fixed,rate=exact(value['fixed_per_order']),exact(value['notional_rate'])
        require(fixed>=0 and rate>=0, 'NONNEGATIVE_EXPLICIT_FEES_REQUIRED')
        return {oid:str(fixed+rate*order['quantity']*exact(order['limit_price']))
                for oid,order in state['chain']['ledger']['orders'].items()}
    require(value.get('schema')=='EXPLICIT_SIMULATION_ORDER_FEES_V1' and type(value.get('order_fees')) is dict,
            'EXPLICIT_ORDER_FEES_REQUIRED')
    orders=state['chain']['ledger']['orders']
    require(set(orders)<=set(value['order_fees']), 'EXPLICIT_ORDER_FEES_MISSING')
    result={oid:value['order_fees'][oid] for oid in orders}
    require(all(exact(fee)>=0 for fee in result.values()), 'NONNEGATIVE_EXPLICIT_FEES_REQUIRED')
    return result


def _accepted_archive_roots(store,state):
    """Derive exact capture directories only from persisted completed operations."""
    accepted={batch['request']['acceptance_id']:batch['request']['kind'] for batch in state['batches'] if batch.get('kind')=='ACCEPTANCE'}
    roots=[];monthly=None
    for operation in store.inspect_operations(state['simulation_id'])['operations']:
        if operation['status']!='COMPLETE':continue
        request=operation['request'];kind=request.get('kind')
        if kind=='SAME_MONTH_CONTINUATION_V1':
            if accepted.get('daily-continuation-'+request['session'])!='CONTINUATION':continue
            roots.append(_absolute(request['storage_directory'])/digest([state['simulation_id'],request['session'],operation['operation_id']]))
        elif kind=='BOUND_MONTHLY_OBSERVATION_V1':
            session=request['monthly_request']['session']
            if accepted.get('monthly-observation-'+session)!='MONTHLY_RETARGET':continue
            archive=_absolute(request['storage_directory'])/digest([state['simulation_id'],session])/'captures'
            roots.append(archive);monthly=archive/'blobs'
    return roots,monthly


def preflight(*,config_path,config_sha256,session):
    path=_absolute(str(config_path));raw=_read(path.parent,path.name,{path.name:config_sha256});config=json.loads(raw)
    required={'schema','root','database_path','simulation_id','schedule_path','schedule_sha256','runtime_directory',
              'fees_path','fees_sha256','capture_audit_roots','monthly_blob_root','monthly','pullback'}
    require(set(config)==required and config['schema']=='ISOLATED_V2_DAILY_RUNTIME_V1', 'INVALID_RUNTIME_CONFIGURATION')
    root=_absolute(config['root']);runtime=_absolute(config['runtime_directory'])
    store=SimulationStore(_absolute(config['database_path']));current=store.read(config['simulation_id'])
    state=current['simulation'];require('valuation' in state, 'VALUATION_REGISTRATION_REQUIRED')
    schedule=json.loads(_read(root,config['schedule_path'],{config['schedule_path']:config['schedule_sha256']}))
    require(schedule['schema']=='SCHEDULED_REGULAR_SESSIONS_V1','SIMULATION_SCHEDULE_SCHEMA')
    dates=state['valuation']['registration']['calendar']['session_dates']
    require(session in dates,'SIMULATION_SESSION_NOT_REGISTERED')
    for day in [d for d in dates if d<=session]:
        rows=[row for row in schedule['sessions'] if row['date']==day]
        require(len(rows)==1 and stamp(rows[0]['close_at'])==stamp(state['valuation']['registration']['calendar']['closes'][day]),
                'REGISTERED_CLOSE_MISMATCH')
    fees=_fees(config,root,state)
    require(type(config['capture_audit_roots']) is list,'INVALID_ORIGIN_ARCHIVE_ROOTS')
    configured_roots=[_absolute(p) for p in config['capture_audit_roots']]
    derived_roots,derived_monthly=_accepted_archive_roots(store,state);roots=configured_roots+derived_roots
    require(all(p.is_dir() for p in roots),'ORIGIN_ARCHIVE_ROOT_MISSING')
    def origins(simulation,reference):
        # Recovery can advance accepted references after preflight; resolve only
        # their exact completed-operation directories at each actual read.
        derived,_=_accepted_archive_roots(store,simulation)
        return SimulationOriginFilesReader(capture_audit_roots=configured_roots+derived)(simulation,reference)
    for reference in _references(state['chain']).values():origins(state,reference)
    guard=VerifiedSnapshotBundleService(SimpleNamespace(root=root),source_withdrawals=SOURCE_WITHDRAWALS).require_source_hashes_admitted
    active=active_proposal(state['chain']['ledger']);causal=active['causal_inputs']
    guard(causal['frozen_execution_package']['source_hashes'] if active['target_scope']=='NEW_CASH_CURRENT_QUOTE_ALLOCATION' else causal['source_hashes'])
    monthly=config['monthly']
    if monthly is not None:
        require(set(monthly)=={'path','sha256','review_mode'} and monthly['review_mode'] in ('DERIVED_PAPER_BOUNDED','STATIC_EXPLICIT'),
                'INVALID_MONTHLY_CONFIGURATION')
        configuration=MonthlyFileConfiguration(root=root,path=monthly['path'],sha256_value=monthly['sha256'],
            clock=lambda:datetime.fromisoformat(session+'T10:00:00').replace(tzinfo=ZoneInfo('America/New_York')))
        value=configuration._config()
        if active['target_month']!=session[:7]:
            # Reuse the real V2 reader's exact fields, one-row month selection,
            # byte limits and manifest/calendar bindings; no search or writes.
            market=configuration.market_reader(state['chain'])
            guard(market['source_package']['source_hashes'])
        for row in value.get('market_entries',[]):
            if row.get('target_month')==session[:7]:
                guard(row['source_hashes'])
                configuration._package(row['source_hashes'])
    # Missing monthly inputs block new decisions, not already accepted history.
    monthly_missing = monthly is None and (active['target_month']!=session[:7]
        or active['target_scope']=='MONTHLY_CURRENT_QUOTE_ALLOCATION')
    monthly_blob_root=derived_monthly or (_absolute(config['monthly_blob_root']) if config['monthly_blob_root'] is not None else None)
    if monthly is not None and (active['target_scope']=='MONTHLY_CURRENT_QUOTE_ALLOCATION' or active['target_month']!=session[:7]):
        require(monthly_blob_root is not None and monthly_blob_root.is_dir(), 'MONTHLY_ORIGIN_ARCHIVE_REQUIRED')
    pullback=config['pullback']
    if pullback is not None:
        require(set(pullback)=={'policy','database_path'} and type(pullback['policy']) is dict,'INVALID_PULLBACK_CONFIGURATION')
        validate_cap_configuration(simulation_database=config['database_path'],cap_database=_absolute(pullback['database_path']),policy=pullback['policy'])
    require(active_entry_policy(state['chain']['ledger'])==(pullback['policy'] if pullback else None),
            'RUNTIME_ENTRY_POLICY_DIFFERS_FROM_ACCEPTED_POLICY')
    fee_document=json.loads(_read(root,config['fees_path'],{config['fees_path']:config['fees_sha256']}))
    fee_policy={key:fee_document[key] for key in ('schema','status','fixed_per_order','notional_rate') if key in fee_document}
    entry_policy=dict(status='EXPLICIT_PULLBACK',policy=pullback['policy']) if pullback else dict(status='NO_PULLBACK_CONFIGURED_NEAR_QUOTE_RULES')
    return dict(config=config,store=store,state=state,root=root,runtime=runtime,origins=origins,guard=guard,monthly_blob_root=monthly_blob_root,
                summary=dict(status='PREFLIGHT_OK_HISTORY_ONLY' if monthly_missing else 'PREFLIGHT_OK',
                             new_decisions_allowed=not monthly_missing,
                             decision_block_reason='MONTHLY_CONFIGURATION_REQUIRED' if monthly_missing else None,
                             simulation_id=config['simulation_id'],session=session,
                             revision=current['revision'],explicit_fee_orders=len(fees),network_used=False,
                             buy_entry_policy=entry_policy,fee_policy=fee_policy,
                             operations=store.inspect_operations(config['simulation_id'])['operations']))


def run_runtime(*,config_path,config_sha256,session,triggered_at,execute=False,clock=None,
                transports=None):
    """transports is an explicit test/embedding seam; CLI never imports plugins."""
    checked=preflight(config_path=config_path,config_sha256=config_sha256,session=session)
    if not execute:return checked['summary']
    clock=clock or (lambda:datetime.now(timezone.utc));transport=transports or {}
    config=checked['config'];root=checked['root'];runtime=checked['runtime'];store=checked['store']
    from data.current_quantity_v2_completed_session_minutes import fetch_bytes
    from data.current_research_intraday_execution import fetch_intraday_chart
    from scripts.current_research_official_alert_capture import fetch_official_feed
    quote_fetch=transport.get('quotes',fetch_intraday_chart);rss_fetch=transport.get('rss',fetch_official_feed)
    action_kwargs=dict(rss_fetch=rss_fetch,clock=clock)
    if 'actions' in transport:action_kwargs['fetch']=transport['actions']
    action_sources=PaperActionEvidenceSources(**action_kwargs)
    from data.current_quantity_v2_late_unit_review import BoundedLateUnitReview
    evidence=DailyEvidenceProviders(store=store,root=root,schedule_path=config['schedule_path'],
        schedule_sha256=config['schedule_sha256'],evidence_directory=runtime/'evidence',
        fee_provider=lambda state,day:_fees(config,root,state),origin_files_reader=checked['origins'],clock=clock,
        minute_fetch=transport.get('minutes',fetch_bytes),late_review=BoundedLateUnitReview(action_sources=action_sources,clock=clock))
    policy=config['pullback']['policy'] if config['pullback'] else None
    caps=LazyPullbackCapStore(_absolute(config['pullback']['database_path']),clock=lambda:stamp(clock()).isoformat(),
        max_history_rows=512,max_history_bytes=128*1024*1024) if policy else None
    def current_monthly_blobs(state):
        _,derived=_accepted_archive_roots(store,state)
        return derived or checked['monthly_blob_root']
    def monthly_parts(state):
        require(config['monthly'] is not None,'MONTHLY_CONFIGURATION_REQUIRED')
        row=config['monthly'];configuration=MonthlyFileConfiguration(root=root,path=row['path'],sha256_value=row['sha256'],clock=clock)
        if row['review_mode']=='DERIVED_PAPER_BOUNDED':
            paper=DerivedPaperReviewProvider(storage_root=runtime/'paper-reviews',evidence_reader=action_sources,clock=clock)
        else:
            class StaticReview:
                def capture(self,snapshot):return configuration.account_review_reader(snapshot)
                def read(self,snapshot):return configuration.account_review_reader(snapshot)
                __call__=read
            paper=StaticReview()
        reviewer=MonthlyBoundedUnitReview(account_review_reader=paper,
            origin_reader=MonthlyOriginReader(monthly_blob_root=current_monthly_blobs(state)),fetch=rss_fetch,clock=clock)
        return configuration,paper,reviewer
    def continuation(state,day):
        result=dict(root=root,schedule_path=config['schedule_path'],schedule_sha256=config['schedule_sha256'],
            storage_directory=runtime/'continuation',source_admission_guard=checked['guard'],fetch=quote_fetch,
            pullback_policy=policy,pullback_cap_store=caps)
        if active_proposal(state['chain']['ledger'])['target_scope']=='NEW_CASH_CURRENT_QUOTE_ALLOCATION':
            result['unit_review_reader']=BoundedPublicUnitReview(fetch=rss_fetch,clock=clock)
        else:
            _,_,reviewer=monthly_parts(state);result.update(monthly_blob_root=current_monthly_blobs(state),monthly_review_reader=reviewer)
        return result
    def monthly(state,day):
        configuration,paper,reviewer=monthly_parts(state)
        checked['guard'](configuration.market_reader(state['chain'])['source_package']['source_hashes'])
        return dict(root=root,configuration_path=config['monthly']['path'],configuration_sha256=config['monthly']['sha256'],
            schedule_path=config['schedule_path'],storage_directory=runtime/'monthly',paper_review_provider=paper,
            review_reader=reviewer,fetch=quote_fetch,pullback_policy=policy,pullback_cap_store=caps)
    result=run_daily(store=store,simulation_id=config['simulation_id'],session=session,triggered_at=triggered_at,
        clock=clock,capture_arguments=evidence.capture_arguments,settlement_review=evidence.settlement_review,
        close_arguments=evidence.close_arguments,continuation_arguments=continuation,monthly_arguments=monthly)
    return dict(result,buy_entry_policy=checked['summary']['buy_entry_policy'],fee_policy=checked['summary']['fee_policy'])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('config','config-sha256','session','triggered-at'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--execute',action='store_true');args=parser.parse_args(argv)
    started=datetime.now(timezone.utc).isoformat()
    try:
        result=run_runtime(config_path=args.config,config_sha256=args.config_sha256,session=args.session,
            triggered_at=args.triggered_at,execute=args.execute)
        output={key:result[key] for key in ('status','daily_status','simulation_id','session','revision','buy_entry_policy','fee_policy','new_decisions_allowed','decision_block_reason') if key in result}
        daily=result.get('daily_status','')
        blocked=daily.startswith('BLOCKED')
        if daily:output['status']='BLOCKED' if blocked else ('SKIPPED' if daily in ('ALREADY_COMPLETED','LATE_NO_NEW_DECISION') else 'COMPLETE')
        output.update(started_at=started,finished_at=datetime.now(timezone.utc).isoformat())
        print(json.dumps(output))
        return 2 if blocked else 0
    except Exception as error:
        reason=str(error) if type(error) is ValueError and str(error).replace('_','').isalnum() else type(error).__name__
        print(json.dumps(dict(status='BLOCKED',reason=reason,started_at=started,
                             finished_at=datetime.now(timezone.utc).isoformat())));return 2


if __name__=='__main__':raise SystemExit(main())
