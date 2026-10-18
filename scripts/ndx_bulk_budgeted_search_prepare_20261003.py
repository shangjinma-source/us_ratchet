"""Create-only finite search inputs. Never import a fitter or dispatch a task."""
import argparse
from copy import deepcopy
from datetime import date
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
sys.path.insert(0, str(ROOT))
OUTPUT = ROOT / 'data/cache/research/bulk_budgeted_search_prepare_20261003_v1'
PINS = {
    'plan': ('data/cache/research/bulk_all_k_plan_20261003_v1/plan.json', '77b596400afb7fea37652bc9155a5ef1e075a24ef4c89277f52cd4ac6bb64671'),
    'plan_publication': ('data/cache/research/bulk_all_k_plan_20261003_v1/publication.json', 'c5988351adb898c00626c2473b9e8e363fca3975651522263b07c80bed3b6691'),
    'panel': ('data/cache/research/bulk_conditional_panel_20261003_v1/panel.json', 'f6a0dab67ac375dfdf4283574f6a392e883110a6bc01efdbca72564873430b71'),
    'panel_publication': ('data/cache/research/bulk_conditional_panel_20261003_v1/publication.json', '895b1d0f71fb3f4b1175845c3390f3d286c672519fa4aa2c0a13bb930f6a2a9d'),
    'rebinding': ('data/cache/research/bulk_completed_task_rebinding_20261003_v1/rebinding.json', 'e2a3cb619a2cd46a2f7d557be91f362342676089756de6baf9ac4c9692daf29d'),
    'rebinding_publication': ('data/cache/research/bulk_completed_task_rebinding_20261003_v1/publication.json', '377db67bbf5be163b96d2f4a2b22f7b808668c0a66bf82d437c41573d2e4d3ec'),
    'contract': ('research_contracts/bulk_budgeted_search_round1_20261003_v1.json', '6cdfed2f0dc076e21ff04e80886fa90f4c89ccd677351a0337451efe53e002c7'),
}
CODE_PINS = {
    'backtest/ndx_bulk_budgeted_search_schedule_research.py': 'e3e477328b50c43f3bfed31ded0ef0d545dc180ab2980c5b4165331c601897df',
    'backtest/ndx_bulk_lazy_task_materialization_research.py': 'a35b074f24b765c64a7bd7ddfa577c083afaaa9dfdbb41c06021b43ea506699a',
    'backtest/ndx_issuer_combination_index_research.py': 'bc24b924ba53f093f7f9bfc05fd237234fbed851ff5d32f7b41324a08594d87b',
    'backtest/ndx_issuer_task_materialization_research.py': '11348bd4aa99b8ee61bacdd12438aaf3c600e1f808e430130464895c22a2df88',
    'backtest/ndx_issuer_shard_prepare_research.py': '722f48952a6d0c8c878df76eedeb0b8ca3b1e3feeb77560598414890ae00a4ec',
    'backtest/ndx_membership_cardinality_plan_research.py': '4f433404895070613d217acc8a245e6fb346f2835652fe1a934eb2be909c943c',
    'backtest/ndx_cardinality_search.py': 'cc5c25fa656564d462d2905ff343d4196820d5343b8f3858f47d432beb509117',
    'backtest/ndx_membership_scope_research.py': '19eae33257ed44620484bd992bce630b3838490bfd190866a51ac080f87330c6',
    'backtest/ndx_dynamic_cutoff_refit_research.py': '33e0f20d1541bc42344f84dd3eae4bc6d61bfaf703ecef07c5e78a5dd547e0bd',
}
AUDIT_PINS = {
    'DYNAMIC_BULK_ALL_K_PLAN_INDEPENDENT_READBACK_20261003.md': 'bb6cc3a353ab6086e8526197206b8a395efd41ea95b9d7eae833296ee6ae904c',
    'scripts/bulk_all_k_plan_independent_review_20261003.py': '0447600ecaf9aab0510b57013bfd67d856543aba7622bafd73c94435d3feeaf9',
    'DYNAMIC_BULK_COMPLETED_TASK_REBINDING_INDEPENDENT_READBACK_20261003.md': 'c3bfb7cdec2932fd73a6ba65235bb253bc3e9ef47d8abaa3edc38f846cf76715',
    'scripts/bulk_completed_task_rebinding_independent_review_20261003.py': '78be911abd92bc01fca04dfd9811b6dd89fc91ee77cfa2042720fb7a097cb8bd',
    'DYNAMIC_BULK_CONDITIONAL_PANEL_INDEPENDENT_READBACK_20261003.md': '8a432b70dfc3393850242873b700eb54097bec9981c8f488cc88bd578295c879',
    'scripts/ndx_bulk_conditional_panel_independent_review_20261003.py': '5a3d35ba39e6a719dfafaa3e4e348f065c5cd297c403a08e087c78f02c5c1b0b',
}
FALSE = dict.fromkeys(('fit_performed', 'execution_authorized', 'promotion_allowed',
    'point_in_time_verified', 'legal_training_input_admitted', 'all_plan_tasks_completed',
    'economic_comparison_performed', 'winner_selected', 'old_raw_reaudited'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def merge_sources(target, additions):
    for path, expected in additions.items():
        require(path not in target or target[path] == expected, 'Conflicting source hash')
        target[path] = expected


def guard(sources):
    require(sha(SOURCE.read_bytes()) == LOADED_SHA, 'Loaded wrapper source drift')
    require(str(SOURCE) not in sources or sources[str(SOURCE)] == LOADED_SHA, 'Wrapper source map conflict')
    for path, expected in sources.items():
        require(type(expected) is str and len(expected) == 64, 'Unresolved source pin')
        require(sha(Path(path).read_bytes()) == expected, 'Source drift: ' + path)


def project_panel(document, reference):
    panel = document['panel']
    require(document['schema'] == 'BULK_CONDITIONAL_TYPED_PANEL_DOCUMENT_V1' and
            panel['schema'] == 'LATEST_BULK_CONDITIONAL_TYPED_PANEL_V1', 'Panel schema')
    for item in (document, panel):
        require(all(item[field] is False for field in ('point_in_time_verified',
            'legal_training_input_admitted', 'promotion_allowed', 'execution_authorized', 'fit_performed')), 'Authority upgrade')
    frame = panel['returns']
    universe = panel['universe']
    require(frame['type'] == 'dataframe' and frame['index_kind'] == 'DatetimeIndex' and
            universe['type'] == 'dataframe' and universe['index_kind'] == 'RangeIndex', 'Typed coordinates')
    require(len(frame['columns']) == len(set(frame['columns'])) == 77 and
            frame['dtypes'] == ['float64'] * 77 and len(frame['index']) == len(frame['data']) == 126, 'Full 126x77 frame')
    days = []
    for timestamp in frame['index']:
        require(type(timestamp) is str and timestamp == timestamp[:10] + 'T00:00:00' and
                date.fromisoformat(timestamp[:10]).isoformat() == timestamp[:10], 'Complete canonical timestamp')
        days.append(timestamp[:10])
    require(days == sorted(set(days)) and days[-1] == panel['cutoff'], 'Exact cutoff dates')
    require(all(type(row) is list and len(row) == 77 and all(type(value) is float and
            math.isfinite(value) and value > -1 for value in row) for row in frame['data']), 'Saved float returns')
    require(len(universe['columns']) == len(set(universe['columns'])) and
            len(universe['data']) == len(universe['index']) == 77 and
            universe['index'] == list(range(77)) and
            len(universe['dtypes']) == len(universe['columns']) and
            all(len(row) == len(universe['columns']) for row in universe['data']), 'Full typed universe')
    rows = [dict(zip(universe['columns'], row)) for row in universe['data']]
    require([row['security_id'] for row in rows] == sorted({row['security_id'] for row in rows}) and
            len({row['issuer_id'] for row in rows}) == 76 and
            sorted(row['ticker'] for row in rows) == frame['columns'], 'Entire SID to ticker projection')
    return dict(panel_reference=deepcopy(reference), panel_content_sha256=panel['panel_content_sha256'],
        dates=days, columns=deepcopy(frame['columns']), returns=deepcopy(frame['data']),
        universe=[{key: row[key] for key in ('security_id', 'ticker', 'issuer_id', 'risk_chain')} for row in rows])


def write_new(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Written bytes differ')
    return dict(path=str(path), sha256=sha(raw))


def load_inputs():
    sources = {str(SOURCE): LOADED_SHA}
    merge_sources(sources, {str(ROOT / path): expected for path, expected in {**CODE_PINS, **AUDIT_PINS}.items()})
    references = {}
    documents = {}
    for role, (relative, expected) in PINS.items():
        path = ROOT / relative
        raw = path.read_bytes()
        require(sha(raw) == expected, 'Pinned input changed: ' + role)
        merge_sources(sources, {str(path): expected})
        documents[role] = strict_json(raw)
        references[role] = dict(path=str(path), sha256=expected)
    merge_sources(sources, documents['plan']['plan']['fitter_source_hashes'])
    guard(sources)
    for role, filename in (('plan', 'plan.json'), ('panel', 'panel.json'), ('rebinding', 'rebinding.json')):
        parent = Path(references[role]['path']).parent
        require({path.name for path in parent.iterdir()} == {'started.json', filename, 'publication.json'},
                'Incomplete or failed parent namespace: ' + role)
    # A CLI process is fresh. Cached dependency modules must not evade byte pins.
    for name in (path[:-3].replace('/', '.') for path in CODE_PINS):
        require(name not in sys.modules, 'Fresh pure-core import required')
    scheduler = importlib.import_module('backtest.ndx_bulk_budgeted_search_schedule_research')
    materializer = importlib.import_module('backtest.ndx_bulk_lazy_task_materialization_research')
    for module in (scheduler, materializer):
        merge_sources(sources, module.LOADED)
    guard(sources)
    return documents, references, sources, scheduler, materializer


def assemble(documents, references, scheduler, materializer):
    plan_document = documents['plan']
    plan = plan_document['plan']
    panel_document = documents['panel']
    rebinding = documents['rebinding']
    contract = documents['contract']
    for role, field, status in (
        ('plan', 'plan_reference', 'PLANNED_NOT_ENUMERATED'),
        ('panel', 'panel_reference', 'PUBLISHED_CONDITIONAL_PANEL_ONLY'),
        ('rebinding', 'rebinding_reference', 'PUBLISHED_REFERENCE_ONLY')):
        receipt = documents[role + '_publication']
        require(receipt[field] == references[role] and receipt['status'] == status and
                receipt['source_hashes'] == documents[role]['source_hashes'], 'Publication binding: ' + role)
        require(all(documents[role][field] is False for field in ('point_in_time_verified',
            'legal_training_input_admitted', 'promotion_allowed', 'execution_authorized', 'fit_performed')), 'Parent authority')
    require(contract['schema'] == 'BULK_BUDGETED_SEARCH_ROUND_CONTRACT_V1' and
            contract['algorithm'] == 'BULK_ISSUER_COVER_STRATIFIED_RANK_V1', 'Budget contract schema')
    require(type(contract['round']) is int and contract['round'] == 1 and
            contract['retained_cardinalities'] == list(range(4, 21)) and
            all(type(k) is int for k in contract['retained_cardinalities']), 'Exact round and cardinalities')
    for field, expected in (('combinations_per_cardinality', 32), ('maximum_proposals', 4096),
                            ('maximum_materialized_combinations', 544), ('weight_specification_count', 3), ('new_fit_count', 0)):
        require(type(contract[field]) is int and contract[field] == expected, 'Exact budget: ' + field)
    require(contract['seed_hex'] == sha(b'NDX_BULK_CONDITIONAL_SEARCH_ROUND1_20261003') and
            contract['uses_economic_scores_for_selection'] is False, 'Fixed score-independent seed')
    require(all(contract[field] is False for field in ('full_search_completed', 'point_in_time_verified',
            'promotion_allowed', 'execution_authorized')), 'Contract authority')
    require(plan['context']['panel_reference'] == references['panel'] and
            rebinding['input_references']['plan'] == references['plan'] and
            rebinding['input_references']['panel'] == references['panel'], 'Same plan and panel')
    require(type(rebinding['externally_rebound_task_count']) is int and rebinding['externally_rebound_task_count'] == 504 and
            type(rebinding['new_fit_count']) is int and rebinding['new_fit_count'] == 0 and
            type(rebinding['new_wrapper_call_attempt_count']) is int and rebinding['new_wrapper_call_attempt_count'] == 0,
            'Sealed504 reference-only')
    require(plan_document['complete_observed_provenance_and_missing'] == panel_document['panel']['observed_provenance_and_missing'] ==
            rebinding['complete_observed_provenance_and_missing'] and len(plan_document['complete_observed_provenance_and_missing']) == 101,
            'Full101 provenance')
    sidecars = plan_document['preserved_evidence_sidecar_references']
    require(set(sidecars) == {'original_evidence_and_projection', 'incremental_evidence_and_projection',
            'v3_incremental_evidence_and_projection', 'v4_incremental_evidence_and_projection',
            'v5_incremental_evidence_and_projection', 'v6_incremental_evidence_and_projection',
            'bulk_incremental_evidence_and_projection'}, 'Seven exact evidence layers')
    for key, value in sidecars.items():
        require(key in panel_document and value == dict(references['panel'], json_pointer='/' + key), 'Exact sidecar reference')
    panel = project_panel(panel_document, references['panel'])
    schedule = scheduler.plan_budgeted_positions(lazy_plan=plan, seed_hex=contract['seed_hex'],
        combinations_per_k={k: 32 for k in contract['retained_cardinalities']}, max_proposals=4096,
        existing_completed_reference=references['rebinding'])
    # Final pure-core schema is pinned before publication.
    require(schedule['status'] == 'PLANNED_NOT_ATTEMPTED' and schedule['materialization_allowed'] is True and
            len(schedule['positions']) == 544, 'Incomplete point selection')
    materialized = materializer.materialize_positions(lazy_plan=plan, plan_reference=references['plan'], panel=panel,
        positions=schedule['positions'], max_combinations=544,
        completed_rebinding=dict(reference=references['rebinding'], document=rebinding))
    require(materialized['combination_count'] == 544 and materialized['materialized_task_count'] == 1632 and
            materialized['complete_saved_completed_task_count'] == 504 and
            materialized['selected_completed_intersection_count'] + materialized['new_unattempted_task_count'] == 1632 and
            materialized['remaining_full_plan_uncompleted_count'] == rebinding['remaining_uncompleted_task_count'],
            'Complete finite materialization and original remaining denominator')
    return dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_V1', status='PREPARED_NOT_ATTEMPTED',
        input_references=deepcopy(references), contract=deepcopy(contract), schedule=schedule, materialized=materialized,
        complete_observed_provenance_and_missing=deepcopy(plan_document['complete_observed_provenance_and_missing']),
        preserved_evidence_sidecar_references=deepcopy(plan_document['preserved_evidence_sidecar_references']),
        original_completed_task_count=504, new_fit_count=0, new_wrapper_call_attempt_count=0,
        full_plan_task_denominator=plan['planned_canonical_task_count'],
        remaining_uncompleted_task_count=rebinding['remaining_uncompleted_task_count'], **FALSE)


def run():
    require(not OUTPUT.exists(), 'Immutable namespace exists; no retry')
    documents, references, sources, scheduler, materializer = load_inputs()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        write_new(OUTPUT / 'started.json', dict(source_hashes=sources, retry_allowed=False, **FALSE))
        value = assemble(documents, references, scheduler, materializer)
        value['source_hashes'] = sources
        guard(sources)
        result = write_new(OUTPUT / 'preparation.json', value)
        guard(sources)
        receipt = write_new(OUTPUT / 'publication.json', dict(schema='BULK_BUDGETED_SEARCH_PREPARATION_PUBLICATION_V1',
            status='PREPARED_NOT_ATTEMPTED', preparation_reference=result, source_hashes=sources, **FALSE))
        guard(sources)
        for reference in (result, receipt):
            require(sha(Path(reference['path']).read_bytes()) == reference['sha256'], 'Final readback')
        require({path.name for path in OUTPUT.iterdir()} == {'started.json', 'preparation.json', 'publication.json'}, 'Unexpected output files')
        return dict(preparation_reference=result, publication_reference=receipt)
    except Exception as error:
        write_new(OUTPUT / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME', error=str(error), retry_allowed=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true')
    require(parser.parse_args().publish, 'Explicit --publish required')
    print(json.dumps(run()))
