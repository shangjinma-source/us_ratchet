"""Strict reviewed pullback draft validation, with no registration or activation API.

Critical machine parameters are explicit; canonical SHA constants bind remaining
reviewed policy sections without duplicating narrative economics. Changed rules
require a reviewed version, never a runtime-loaded self-signing reference.
Caller supplies a byte reader; verified listed files are not a transitive freeze.
"""
import hashlib
import json
import re
from pathlib import PurePosixPath

SCHEMA='VARIABLE_CARDINALITY_PULLBACK_PROSPECTIVE_PROTOCOL_CANDIDATE_V1'
TOP_KEYS = frozenset({'user_return_drawdown_priority', 'decision_policy_inherited_from_v3', 'review_status', 'schema', 'schedule_authority', 'reporting', 'activation_gates', 'failure_gates', 'background_comparators', 'frozen_at', 'frozen', 'reference_hashes', 'candidate_code_hashes', 'authored_on', 'status', 'selection', 'domain_data_calendar', 'activation', 'execution', 'validator_boundary', 'supersedes_draft', 'formal_dual_benchmark_claim_gate', 'monthly_capital_and_targets', 'role', 'predecessor_boundary', 'not_performed', 'start'})
REVIEWED_POLICY_SHA256 = {'activation': '7386927d43f4b4be5db1275b44524ecb52443a0a2aa6273d2e1e5217a1f8c7cb',
 'activation_gates': '9c5f7b786f4ea58999ee7d5d42affe3c04afe4c0bc0540f77d3ba7ab46496143',
 'background_comparators': 'bc3866cb6c4f3c9b9a6b0918a8e5c5c9aaed523d4cf23276b21d41a2dc227560',
 'decision_policy_inherited_from_v3': '5f23cdaf786d4a677f2e31a7033ccf9972e85b7198f7c986fc3994a5391b6d69',
 'domain_data_calendar': '15a938c35b00563633afb6e849f70299805f4ce8aea98515765028c9f67cea3d',
 'execution': 'dafe63d7bef9fdd38d2cbd0841195ca629d8abf4155b2a119ad49f16c87189a3',
 'failure_gates': '39e4ab7ff8286c557545806066c87a3f107feb4bc967d09a62995ed15e12dc88',
 'formal_dual_benchmark_claim_gate': '7f07671a092521ff0b21f745b8de6ee04907de2ef6f34b4b7e0d2c83dc46a6a9',
 'monthly_capital_and_targets': '911a964f4ae30cf7b15a6ff9393867c8061d22d0be7abc0dfbbec87b982d691c',
 'reporting': '6e078684af04e9ac673a908b7da4fdfdce07fe6a6e08b8440a9e551a2ed0a9f6',
 'schedule_authority': '1e32cb1bf16a308a57afc1d3f23eb9e203057dae4cb8fb39645f0a69c95bdb1f',
 'selection': 'e70a60d26644afb2efa0aeeb2d8759fc81dc3fed7d3e13136d0c19874aa3e7ea',
 'user_return_drawdown_priority': '4d5130f3e516ae40809c5375e4b377eb67eb89536e28f1713ab09c8cb61bebb4'}
ACTIVATION_KEYS = frozenset({'forward_account_created', 'registered_at', 'automatic_schedule_created', 'capital_currency', 'independent_year_started', 'start_decision_date', 'account_id', 'independent_year_completed', 'start_active_session', 'intended_duration', 'initial_capital', 'broker_orders_authorized', 'forward_observation_schedule'})
CODE_PATHS = frozenset({'data/current_quantity_v2_paper_chain.py', 'data/current_quantity_v2_pullback_proof.py', 'data/current_research_capital_decision_v2.py', 'data/current_quantity_v2_pullback_runtime.py', 'data/current_quantity_v2_difference_plan.py', 'backtest/return_priority_fresh_cash_quantity_search_v2.py', 'data/current_quantity_v2_pullback_sources.py', 'data/current_quantity_v2_pullback_cap_store.py', 'backtest/current_quantity_v2_annual_clock.py', 'data/current_quantity_v2_monthly_retarget.py', 'backtest/current_quantity_v2_minute_day_fill.py', 'data/current_quantity_v2_current_cash_plan.py', 'data/current_quantity_v2_pullback_entry.py', 'data/current_quantity_v2_current_cash_continuation.py'})
REFERENCE_PATHS = frozenset({'research_contracts/monthly_top1_prospective_protocol_frozen_20261015_v1.json', 'data/current_quantity_v2_prospective_protocol.py', 'research_contracts/user_return_drawdown_priority_20261016_v1.json', 'research_contracts/user_annual_replay_cadence_20261015.json', 'tmp/current_quantity_v2_service_admission_20261015_v5/descriptor.json', 'research_contracts/monthly_quantity_v2_prospective_protocol_candidate_20261015_v3.json', 'research_contracts/original_weight_next12_control_draft_20261015_v1.json'})


def require(condition,code):
    if not condition:raise ValueError(code)


def validate_candidate(protocol, *, read_bytes):
    require(isinstance(protocol,dict) and set(protocol)==TOP_KEYS,'UNKNOWN_OR_MISSING_PROTOCOL_FIELD')
    require(protocol['schema']==SCHEMA,'PROTOCOL_SCHEMA')
    require(protocol['status']=='NOT_ACTIVATED' and protocol['frozen'] is False and
            protocol['frozen_at'] is None and protocol['start'] is None,'DRAFT_CANNOT_ACTIVATE_OR_BACKDATE')
    selection=protocol['selection']; execution=protocol['execution']
    for key,value in dict(method='EXACT_SINGLE_SUPPORT_ENUMERATION_FAIR_K_V2',completed_closes=253,
            scenario_count=12,sessions_per_scenario=21,objective_evaluation_budget=8192,
            fee_bps='0',minimum_cash_buffer='0',fixed_seed='fresh-quantity-20261014-v1',
            frequency='ONCE_PER_REGISTERED_TARGET_MONTH').items():
        require(selection.get(key)==value,'SELECTOR_PARAMETER_DRIFT:'+key)
    for key,value in dict(buy_policy_schema='V2_PULLBACK_EXECUTION_POLICY_V1',
            rebound_fraction='1/2',minimum_discount='1/200',maximum_age_seconds=120,
            policy_status='EXPERIMENTAL_NOT_PERFORMANCE_VALIDATED').items():
        require(execution.get(key)==value,'EXECUTION_PARAMETER_DRIFT:'+key)
    # Fixed hashes of reviewed sections, not hashes recomputed from a reference
    # file at validation time. Unknown fields and narrative economic changes fail.
    for section,expected in REVIEWED_POLICY_SHA256.items():
        raw=json.dumps(protocol[section],sort_keys=True,separators=(',',':'),
                       ensure_ascii=False,allow_nan=False).encode('utf-8')
        require(hashlib.sha256(raw).hexdigest()==expected,'POLICY_DRIFT:'+section)
    require(all(type(protocol['selection'][k]) is int for k in ('completed_closes','scenario_count','sessions_per_scenario','objective_evaluation_budget')) and type(protocol['execution']['maximum_age_seconds']) is int,'INTEGER_POLICY_PARAMETERS_REQUIRED')
    activation=protocol['activation']
    require(isinstance(activation,dict) and set(activation)==ACTIVATION_KEYS,'ACTIVATION_FIELDS')
    for key in ('registered_at','start_decision_date','start_active_session','initial_capital',
                'capital_currency','account_id','forward_observation_schedule'):
        require(activation[key] is None,'DRAFT_CANNOT_REGISTER:'+key)
    for key in ('broker_orders_authorized','automatic_schedule_created','forward_account_created',
                'independent_year_started','independent_year_completed'):
        require(activation[key] is False,'DRAFT_FALSE_ACTIVATION:'+key)
    benchmarks=protocol['background_comparators']
    require(set(benchmarks)=={'purpose','012922','incumbent','QQQ'},'BENCHMARK_FIELDS')
    for key in ('012922','incumbent','QQQ'):
        require(benchmarks[key]['required'] is False,'BENCHMARK_NOT_START_GATE')
    for key in ('012922','incumbent'):
        require(benchmarks[key]['required_for_formal_dual_benchmark_claim'] is True,
                'FORMAL_COMPARISON_REQUIREMENTS_RETAINED')
    # The reviewed gate list contains no benchmark prerequisites. Reject new gates
    # rather than interpreting prose to silently reintroduce them.
    preference=protocol['user_return_drawdown_priority']
    require(preference['guaranteed_returns'] is False and preference['return_sacrifice_threshold'] is None
            and preference['hard_drawdown_threshold'] is None,'INVENTED_USER_THRESHOLD')
    code=protocol['candidate_code_hashes'];refs=protocol['reference_hashes']
    require(isinstance(code,dict) and set(code)==CODE_PATHS,'IMPLEMENTATION_REFERENCE_DOMAIN')
    require(isinstance(refs,dict) and set(refs)==REFERENCE_PATHS,'REFERENCE_DOMAIN')
    require(code==REVIEWED_CODE_HASHES and refs==REVIEWED_REFERENCE_HASHES,'UNREVIEWED_SOURCE_VERSION')
    combined={}
    for mapping in (code,refs):
        for path,digest in mapping.items():
            pure=PurePosixPath(path)
            require(not pure.is_absolute() and '..' not in pure.parts and '\\' not in path and ':' not in path,
                    'UNSAFE_REFERENCE_PATH')
            require(isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest) is not None,'INVALID_SHA256')
            require(path not in combined or combined[path]==digest,'REFERENCE_HASH_CONFLICT')
            raw=read_bytes(path)
            require(isinstance(raw,bytes),'RAW_SOURCE_BYTES_REQUIRED')
            require(hashlib.sha256(raw).hexdigest()==digest,'SOURCE_HASH_MISMATCH:'+path)
            combined[path]=digest
    for section in ('supersedes_draft','user_return_drawdown_priority','validator_boundary'):
        link=protocol[section]
        require(link['path'] in refs and link['sha256']==refs[link['path']],'UNBOUND_REFERENCE:'+section)
    return dict(status='VALIDATED_DRAFT_ONLY_NOT_ACTIVATION_READY',activated=False,
        registered=False,independent_year_started=False,listed_source_hashes_verified=True,
        transitive_implementation_closure_verified=False,verified_reference_count=len(combined),
        missing_registration=['Actual start/active session/account/initial capital/currency',
            'Prospective observation trigger, acceptance and fill convention',
            'Actual current-month registration or explicitly late non-backdated bootstrap'],
        missing_source_closure=['Complete executable transitive dependency freeze',
            'Actual forward monthly domain/training/identity/action inputs and calendar',
            'Fresh quote access and capture coverage for prospective decisions',
            'Fee/rights/external-flow accounting convention and daily complete marks'],
        benchmark_missing_is_activation_blocker=False,
        missing_benchmark_scope='Separate formal comparison claims only',
        boundary='No account writes, schedule, registration, search or economic performance inferred')

REVIEWED_CODE_HASHES = {'backtest/current_quantity_v2_annual_clock.py': '8dea47bd87c3694cce33871689e7cc2bcf332c48714812241a931a40885bc339',
 'backtest/current_quantity_v2_minute_day_fill.py': '112351aec80270c12f75f27e9429498d7de269d3caee345b605df2be0348910f',
 'backtest/return_priority_fresh_cash_quantity_search_v2.py': 'f813782ab166139c8d30b268a242fa05bd65ce76e9b9b20aa03a0beee2bd01d7',
 'data/current_quantity_v2_current_cash_continuation.py': '7b984d83ffa283181afb198ed2e42db645265d0979cab0ea2e016c591376e1da',
 'data/current_quantity_v2_current_cash_plan.py': 'b9c2c61a41d01e5d8dd3325fd3a7eb5d894b67b0c929e67f6994fa8a7464a2a1',
 'data/current_quantity_v2_difference_plan.py': '06ef796cf0c151797cafa13c045aeee6b9282ff03724ef80774b59b29a794039',
 'data/current_quantity_v2_monthly_retarget.py': '5893a7a4bd6168b8973f58cac050d90eb530091eaa5be9c664d60d6cf5d902bd',
 'data/current_quantity_v2_paper_chain.py': '0e08dfa38e6b94e2d72dc2f0ba1a4a1189c67c41b4997af0ad17149def91a7b6',
 'data/current_quantity_v2_pullback_cap_store.py': '7d0c3e344a2339814753c39930ea6b6e7d448101b0c17d459514bd992a2612ce',
 'data/current_quantity_v2_pullback_entry.py': '48249a9c5e1fa043d1c54d9668da82191bdc0a09fc1ed9fbeb61dab5c3aa4e4f',
 'data/current_quantity_v2_pullback_proof.py': '8bf590b99df98628d705f68b2a1f08451db5b0adc5c9c5c449c17a2229c3bef4',
 'data/current_quantity_v2_pullback_runtime.py': '40e2b1539b64d0ecf73617baff62e8bcb4579e6849eb8759e1edfe2eb4c6cfbb',
 'data/current_quantity_v2_pullback_sources.py': '64a5c392802347c5fdf0d905da86033814db742631024547c6bcd121d3877b6f',
 'data/current_research_capital_decision_v2.py': 'c680c57e669f9c07be40a4f583c420f4432e9b44b3574bc19b635145ed492ea7'}
REVIEWED_REFERENCE_HASHES = {'data/current_quantity_v2_prospective_protocol.py': '66858480c1d2d2c68980944509352725091235e82f2c77b217ccc1945fe56405',
 'research_contracts/monthly_quantity_v2_prospective_protocol_candidate_20261015_v3.json': '3883f5e585d52f3cedfd9fab7653839da85e4e5340bca0cd58e93a9b593c5492',
 'research_contracts/monthly_top1_prospective_protocol_frozen_20261015_v1.json': '395f1f09ce8a79bc545c74c45b9084574264c744503a31be297e61a93c0cafb9',
 'research_contracts/original_weight_next12_control_draft_20261015_v1.json': '009ec91ae835d32b0333de3db39b380d6f5edd158eb080799b67f6a835a27f65',
 'research_contracts/user_annual_replay_cadence_20261015.json': 'abab3eae89769279682136b30a200e0350fbd2c281e4bb84738030f2c912c364',
 'research_contracts/user_return_drawdown_priority_20261016_v1.json': 'e5ec8e61046704a53b5a92cdf61ebf4d094c9fee5be724ba32a89db8a26d4877',
 'tmp/current_quantity_v2_service_admission_20261015_v5/descriptor.json': 'ecc1511d1949a7b061bcd2da9290650b38ec0ba13e9a99299770292ad91e7984'}
