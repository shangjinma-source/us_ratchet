"""Opt-in observation layer around frozen v7; no policy or target publication."""
from pathlib import Path
from hashlib import sha256
from fastapi import APIRouter
from fastapi.routing import APIRoute
from fastapi.responses import Response
from core.strategy_account_difference import require
from data.strategy_unified_server_preparation_v7 import build_unified_server_preparation_v7, _read
from data.strategy_bounded_source_gate_v1 import BoundedSourceGateV1
from data.strategy_profiled_reviewed_domain_packet_admission_v1 import create_profiled_reviewed_domain_packet_admission_v1
from data.strategy_daily_advice_journal_v1 import DailyAdviceJournalV1
from data.strategy_observed_daily_admission_v1 import ObservedDailyAdmission
from api.strategy_daily_preview_v3 import create_router as preview_router
from api.strategy_advice_observations_v1 import create_router as observations_router

OBSERVATION_SOURCES = {
    'data/strategy_unified_server_preparation_v8.py',
    'data/strategy_daily_advice_journal_v1.py',
    'data/strategy_observed_daily_admission_v1.py',
    'api/strategy_advice_observations_v1.py',
    'web/strategy_advice_review.js',
}
JOURNAL_PATH = 'data/strategy_account/daily_advice_v1.sqlite3'


def attach_observations(*, prepared, root, daily_configuration, daily_reference,
                        validate_observation_sources):
    """Explicit composition, no closure inspection or replacement of frozen methods."""
    monthly = prepared['monthly']
    def gate():
        prepared['validate_code']()
        validate_observation_sources()
    gate()
    daily = create_profiled_reviewed_domain_packet_admission_v1(
        monthly=monthly,clock=monthly.clock,validate_code=gate,root=root,
        server_configuration=daily_configuration)
    references = dict(daily_configuration=daily_reference,
        policy_id=daily_configuration.get('policy_id'),
        policy_execution_enabled=daily_configuration.get('policy_execution_enabled',False),
        evidence_references=daily_configuration.get('evidence'))
    journal = DailyAdviceJournalV1(Path(root)/JOURNAL_PATH,clock=monthly.clock)
    observed = ObservedDailyAdmission(service=daily,monthly=monthly,journal=journal,
        clock=monthly.clock,validate_sources=gate,policy_references=references)
    routes = [route for route in prepared['router'].routes if isinstance(route,APIRoute)
              and route.path == '/api/strategy-daily-v3/preview' and route.methods == {'POST'}]
    require(len(routes)==1,'OBSERVED_DAILY_ROUTE_REQUIRED')
    router=APIRouter()
    router.routes.extend(route for route in prepared['router'].routes if route is not routes[0])
    router.include_router(preview_router(service=observed))
    router.include_router(observations_router(journal=journal,account_id=monthly.accounts.read()['account_id'],validate_sources=gate))
    @router.get('/static/strategy_advice_review.js')
    def review_script():
        gate()
        raw=(Path(root)/'web/strategy_advice_review.js').read_bytes()
        gate()
        return Response(content=raw,media_type='application/javascript')
    gate()
    return dict(prepared,router=router,advice_journal=journal,observed_daily=observed)


def build_unified_server_preparation_v8(*,root,configuration_path,configuration_sha256,clock=None):
    root=Path(root).absolute()
    reference=dict(path=configuration_path,sha256=configuration_sha256)
    raw,configuration=_read(root,reference)
    require(set(configuration)=={'schema','base_v7','source_pins'} and
            configuration['schema']=='OBSERVED_UNIFIED_PREPARATION_V8','OBSERVED_PREPARATION_FIELDS')
    require(set(configuration['source_pins'])==OBSERVATION_SOURCES,'OBSERVATION_SOURCE_SCOPE')
    actual={name:sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()
            for name in OBSERVATION_SOURCES}
    require(configuration['source_pins']==actual,'OBSERVATION_RUNNING_SOURCE_MISMATCH')
    _,v7=_read(root,configuration['base_v7'])
    _,v6=_read(root,v7['base_v6'])
    daily_reference=v6['daily_configuration']
    _,daily=_read(root,daily_reference)
    combined=dict(v6['source_pins'])
    for name,digest in configuration['source_pins'].items():
        require(name not in combined or combined[name]==digest,'OBSERVATION_SOURCE_CONFLICT')
        combined[name]=digest
    extra_gate=BoundedSourceGateV1(root=root,source_pins=combined,
        configuration_pins={ref['path']:ref['sha256'] for ref in
            (reference,configuration['base_v7'],v7['base_v6'],daily_reference)})
    extra_gate()
    prepared=build_unified_server_preparation_v7(root=root,
        configuration_path=configuration['base_v7']['path'],
        configuration_sha256=configuration['base_v7']['sha256'],clock=clock)
    prepared=attach_observations(prepared=prepared,root=root,daily_configuration=daily,
        daily_reference=daily_reference,validate_observation_sources=extra_gate)
    require(_read(root,reference)[0]==raw,'OBSERVATION_CONFIGURATION_CHANGED')
    return prepared
