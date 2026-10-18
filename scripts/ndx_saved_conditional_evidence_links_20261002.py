"""Bind saved SEC evidence to explicit class selections, without PIT admission."""
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/saved_conditional_evidence_links_20261002_v1'
PINS = {
    'batch': ('data/cache/research/full_pool_saved_evidence_batch_20261002_v1/batch.json', '53e2c75e4f317ba1ced555a3821669d2a73d2c3bd49c89c73aecd1f147441a69'),
    'publication': ('data/cache/research/full_pool_saved_evidence_batch_20261002_v1/publication.json', 'e4d728fee63cee0f764e4e5d83015672e11a1a466e7bc2fa57d7d761c5ab87a2'),
    'independent_readback': ('DYNAMIC_FULL_POOL_SAVED_EVIDENCE_INDEPENDENT_READBACK_20261002.md', 'acf9dfccc038a0d4064e3738b9248c1ebc14fab94a0a7762f02fbd444b96a31b'),
    'asml_evidence': ('data/cache/research/asml_incumbent_identity_20261002_v1/identity.json', '85cdde6403d93a544679886c5b85b7c68fb9fd8e7657ad84ea8ac5c9591d544d'),
    'asml_publication': ('data/cache/research/asml_incumbent_identity_20261002_v1/publication.json', '87836bfddc6fe331db194b23df308c51e460c062b4c2d34ee4e67c0786001784'),
    'selection': ('research_contracts/full_pool_security_group_selection_20261002_v1.json', '611eda9d6e476bd0909256bf7fcffbecb9ddcb0ecdf4ece09d06b06d0eacad9e'),
    'core': ('backtest/ndx_saved_conditional_evidence_links_research.py', '05ec58738bd6dc4b6b54028924d31da807e8763af2188c49804d4a9dd2e9134e'),
}
WINDOW = {'first': '2026-03-20', 'last': '2026-09-21'}
FLAGS = dict.fromkeys(('point_in_time_verified', 'identity_interval_verified', 'provider_binding_verified',
    'risk_interval_verified', 'legal_training_input_admitted', 'promotion_allowed', 'execution_authorized',
    'full_universe_coverage_verified', 'fit_performed', 'http_performed', 'old_audit_called',
    'prices_recomputed', 'filing_raw_bytes_reparsed', 'parent_wiring_modified', 'panel_modified',
    'full_transitive_source_closure_reverified', 'original_review_risk_reclassified'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def assemble(batch, selection, documents, references, linker):
    require(batch['schema'] == 'FULL_POOL_SAVED_EVIDENCE_BATCH_V1', 'Saved batch schema differs')
    inventory = batch['inventory_preserved']
    require(len(inventory['rows']) == 101 and len(inventory['historical_denominators']) == 15,
            'Complete current and historical denominator required')
    require(len({row['ticker'] for row in inventory['rows']}) == 101, 'Unique complete current rows')
    require(selection['schema'] == 'SAVED_SEC_CONDITIONAL_SELECTION_CONTRACT_V1'
            and selection['assumed_window'] == WINDOW, 'Explicit selection scope required')
    require(selection['batch_reference'] == references['batch'] and selection['research_only'] is True
            and type(selection['row_count']) is int and selection['row_count'] == 53, 'Selection source scope differs')
    for value in (batch, selection):
        for flag in ('point_in_time_verified', 'identity_interval_verified', 'promotion_allowed', 'legal_training_input_admitted'):
            require(value[flag] is False, 'Parent authority differs')
    queue = inventory['extraction_queue']
    choices = selection['rows']
    require(len(queue) == len(choices) == len(batch['extraction_rows']) == 53, 'Complete 53-row source and contract')
    require(set(documents) == set(batch['document_references']), 'Complete derived document map')
    links = []
    used_indexes = set()
    for index, (item, choice, extraction_row) in enumerate(zip(queue, choices, batch['extraction_rows'])):
        row_index = item['inventory_row_index']
        require(type(row_index) is int and 0 <= row_index < 101 and row_index not in used_indexes,
                'Unique exact inventory index required')
        used_indexes.add(row_index)
        require(choice['ticker'] == item['ticker'] == inventory['rows'][row_index]['ticker']
                and type(choice['inventory_row_index']) is int and choice['inventory_row_index'] == row_index,
                'Selection row identity differs')
        digest = item['raw_reference']['sha256']
        document_reference = batch['document_references'][digest]
        require(choice['raw_sha256'] == digest and choice['document_reference'] == document_reference,
                'Selection document reference differs')
        require(len(choice['selected_group_indexes']) == 1 and type(choice['selected_group_indexes'][0]) is int
                and type(choice['selected_title_fact_index']) is int
                and choice['selected_group_pointer'] == '/extraction/same_context_security_groups/' + str(choice['selected_group_indexes'][0])
                and choice['selected_title_fact_pointer'] == '/extraction/dei_facts/' + str(choice['selected_title_fact_index']),
                'Explicit single title and exact group/fact pointers required for this saved batch')
        for flag in ('point_in_time_verified', 'identity_interval_verified', 'promotion_allowed', 'legal_training_input_admitted'):
            require(choice[flag] is False, 'Selection row authority differs')
        support = choice['supporting_evidence']
        review = item['review_match']['decision']
        require(support['review_reference'] == item['review_match']['reference']
                and all(support[key] == review[key] for key in ('selection_date', 'evidence_available_date', 'effective_from')),
                'Saved review availability source differs')
        require(support['early_window_review_availability_verified'] is False
                and support['local_first_available_at'] is None
                and support['review_selection_postdates_window_start'] is (review['selection_date'] > WINDOW['first']),
                'Saved availability claim differs')
        if item['ticker'] == 'ASML':
            handling = choice['class_handling']
            require(handling['source_references'] == {'identity.json': references['asml_evidence'],
                                                     'publication.json': references['asml_publication']}
                    and handling['new_window_class_identity_verified'] is False,
                    'ASML supplemental evidence differs')
        if item['ticker'] == 'PDD':
            handling = choice['class_handling']
            require(type(handling['ordinary_shares_per_ads']) is int and handling['ordinary_shares_per_ads'] == 4
                    and handling['holdings_conversion_performed'] is False and handling['price_conversion_performed'] is False,
                    'PDD original ADS class must not convert holdings or prices')
        require(extraction_row['original_queue_item'] == item
                and extraction_row['document_sha256'] == digest
                and extraction_row['status'] == 'EXTRACTED_SAVED_FACTS_NOT_IDENTITY_ADMISSION',
                'Saved extraction row differs')
        chosen = deepcopy(choice)
        chosen['reviewed_contract_reference'] = dict(references['selection'], json_pointer=f'/rows/{index}')
        result = linker(queue_item=item, extracted_document=documents[digest],
                        document_reference=document_reference, selection_contract=chosen, assumed_window=deepcopy(WINDOW))
        for flag in ('point_in_time_verified', 'identity_interval_verified', 'provider_binding_verified',
                     'risk_interval_verified', 'legal_training_input_admitted', 'promotion_allowed', 'execution_authorized'):
            require(result[flag] is False, 'Evidence link grants unexpected authority')
        links.append({'inventory_row_index': row_index, 'ticker': item['ticker'],
                      'queue_reference': dict(references['batch'], json_pointer=f'/inventory_preserved/extraction_queue/{index}'),
                      'selection_contract': chosen, 'document_reference': deepcopy(document_reference), 'link': result, **FLAGS})
    rows = []
    by_index = {row['inventory_row_index']: index for index, row in enumerate(links)}
    for index, row in enumerate(inventory['rows']):
        rows.append({'ticker': row['ticker'], 'original_inventory_row': deepcopy(row),
                     'parent_reference': dict(references['batch'], json_pointer=f'/inventory_preserved/rows/{index}'),
                     'new_link_index': by_index.get(index),
                     'status': 'NEW_SAVED_CONDITIONAL_EVIDENCE_LINK' if index in by_index else
                               'REUSE_EXISTING_CONDITIONAL_COORDINATE' if row['already_wired_conditional_coordinate'] else
                               'UNRESOLVED_SOURCE_LEADS_PRESERVED', **FLAGS})
    return {'schema': 'SOURCE_BOUND_SAVED_CONDITIONAL_EVIDENCE_LINKS_V1', 'assumed_window': deepcopy(WINDOW),
            'rows': rows, 'links': links, 'historical_denominators': deepcopy(inventory['historical_denominators']),
            'selection_contract_preserved': deepcopy(selection), 'inventory_summary_preserved': deepcopy(inventory['summary']),
            'saved_parent_inventory_reference': dict(references['batch'], json_pointer='/inventory_preserved'),
            'summary': {'current_row_count': 101, 'historical_coordinate_count': 15, 'new_evidence_link_count': 53,
                        'preserved_existing_coordinate_count': sum(row['already_wired_conditional_coordinate'] for row in inventory['rows']),
                        'unlinked_source_lead_count': sum(row['status'] == 'UNRESOLVED_SOURCE_LEADS_PRESERVED' for row in rows),
                        'new_typed_panel_column_count': 0, 'verified_pit_eligible_count': None}, **FLAGS}


def write_new(path, value):
    raw = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == raw, 'Output bytes changed')
    return {'path': str(path), 'sha256': sha(raw)}


def run():
    require(not OUTPUT.exists(), 'Fixed namespace exists; no retry')
    sources = {str(SOURCE): LOADED_SHA}
    references, raw = {}, {}
    for role, (relative, digest) in PINS.items():
        require(len(digest) == 64, 'Pending source pin: ' + role)
        path = ROOT / relative
        data = path.read_bytes()
        require(sha(data) == digest, 'Pinned source differs: ' + role)
        sources[str(path)] = digest
        references[role] = {'path': str(path), 'sha256': digest}
        raw[role] = data
    batch, receipt, selection = (json.loads(raw[role]) for role in ('batch', 'publication', 'selection'))
    require(receipt['batch_reference'] == references['batch'] and receipt['source_hashes'] == batch['source_hashes']
            and receipt['status'] == 'PUBLISHED_EVIDENCE_ONLY_NOT_ADMISSION', 'Saved publication differs')
    asml = json.loads(raw['asml_evidence'])
    asml_receipt = json.loads(raw['asml_publication'])
    require(asml_receipt['identity_reference'] == references['asml_evidence']
            and asml_receipt['source_hashes'] == asml['source_hashes']
            and asml_receipt['status'] == 'PUBLISHED_CONDITIONAL_SID_SIDECAR_ONLY', 'ASML publication differs')
    require(asml['annual_registered_class'] == 'Ordinary Shares' and asml['security_class'] == 'New York Shares'
            and asml['point_in_time_verified'] is False and asml['cross_document_identity_certified'] is False,
            'ASML class scope differs')
    documents = {}
    for digest, reference in batch['document_references'].items():
        path = Path(reference['path'])
        data = path.read_bytes()
        require(sha(data) == reference['sha256'], 'Derived document changed')
        sources[str(path)] = reference['sha256']
        documents[digest] = json.loads(data)
    module_name = 'backtest.ndx_saved_conditional_evidence_links_research'
    require(module_name not in sys.modules, 'Fresh CLI import required')
    module = importlib.import_module(module_name)
    require(Path(module.__file__).resolve() == Path(references['core']['path']).resolve(), 'Core import path differs')
    def guard():
        require(all(sha(Path(path).read_bytes()) == digest for path, digest in sources.items()), 'Bound source drift')
    guard()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        write_new(OUTPUT / 'started.json', {'source_hashes': sources, 'retry_allowed': False, **FLAGS})
        result = assemble(batch, selection, documents, references, module.link_saved_conditional_evidence)
        result.update(source_hashes=sources, input_references=references,
                      supplemental_saved_evidence={'asml': json.loads(raw['asml_evidence'])})
        guard()
        result_reference = write_new(OUTPUT / 'links.json', result)
        guard()
        publication = write_new(OUTPUT / 'publication.json', {
            'schema': 'SAVED_CONDITIONAL_EVIDENCE_LINKS_PUBLICATION_V1', 'status': 'PUBLISHED_CONDITIONAL_LINKS_NO_ADMISSION',
            'links_reference': result_reference, 'source_hashes': sources, **FLAGS})
        guard()
        require(all(sha(Path(reference['path']).read_bytes()) == reference['sha256']
                    for reference in (result_reference, publication)), 'Publication changed')
        require({path.name for path in OUTPUT.iterdir()} == {'started.json', 'links.json', 'publication.json'},
                'Unexpected namespace files')
        return {'links_reference': result_reference, 'publication_reference': publication, 'summary': result['summary']}
    except Exception as error:
        write_new(OUTPUT / 'failure.json', {'status': 'FAILED_DO_NOT_CONSUME', 'error': str(error), 'retry_allowed': False})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if not parser.parse_args().execute:
        parser.error('Explicit --execute required')
    print(json.dumps(run(), indent=2))
