"""Publish saved classification coverage without recategorizing or replaying audits."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import types

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/saved_classification_coverage_20261003_v1'
BOUND = {
    'wiring': ('data/cache/research/bulk_conditional_wiring_20261003_v1/wiring.json', 'e4f4328043254667ff334ebc7aaf0fe530d451339f5b9d4b1ba0a20c37b9b8a5'),
    'wiring_publication': ('data/cache/research/bulk_conditional_wiring_20261003_v1/publication.json', '7f9ba6d89271fded96727e4dbfdd08ccc58ff249d352fddf5f97a8366f345e12'),
    'wiring_review_report': ('DYNAMIC_BULK_CONDITIONAL_WIRING_INDEPENDENT_READBACK_20261003.md', '3600f8f179331c5cd864669a5f278f2c12fa36db39e1c836e9bae206efb494bc'),
    'wiring_reader': ('scripts/ndx_bulk_conditional_wiring_independent_review_20261003.py', 'c5ed4f3468001292c13452ec64889ed25f3309032444b9014d4a23079267a901'),
    'training_panel': ('data/cache/research/dated_training_panel_20261003_v1/panel.json', '895f31e30647e1422bcd2feab3025f8e9103c745f9d176549d59a069a30b9d96'),
    'training_publication': ('data/cache/research/dated_training_panel_20261003_v1/publication.json', '2b64693fd54c1358429ca9df8ac5c9b685882d419a275a7b4384e878c5c1a2a5'),
    'training_audit': ('DYNAMIC_DATED_TRAINING_PANEL_INDEPENDENT_READBACK_20261003.json', '38b5a61dbfae53264c8691e421d1bbb00140f567d437b5692543c9313a0d95bd'),
    'training_reader': ('scripts/ndx_dated_training_panel_independent_review_20261003.py', '7a7cd393f3d02e11b96facbad3b259dee6337cb3f69bbc21dbc94556f4f66309'),
    'core': ('backtest/ndx_saved_risk_classification_coverage_research.py', '116b6eaff2621216490ab77cdc96d0b7af6b5d38a70345e42197f7c61f79486e'),
}
FLAGS = dict.fromkeys(('point_in_time_verified', 'promotion_allowed', 'execution_authorized',
    'fit_performed', 'risk_reclassified', 'old_audits_reexecuted', 'future_independent_oos',
    'full_transitive_source_closure_reverified', 'official_classification_conflict_audited'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def exact(left, right, message):
    require(encode(left) == encode(right), message)


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def parse(blob):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(blob, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def references():
    return {role: dict(path=str(ROOT / path), sha256=value) for role, (path, value) in BOUND.items()}


def guard(sources):
    require(sources.get(str(SOURCE)) == LOADED, 'Loaded source binding')
    for path, expected in sources.items():
        require(digest(Path(path).read_bytes()) == expected, 'Source drift: ' + path)


def validate_evidence(documents, blobs, refs):
    wiring, panel = documents['wiring'], documents['training_panel']
    wp, pp, audit = (documents[k] for k in ('wiring_publication', 'training_publication', 'training_audit'))
    require(wp['schema'] == 'BULK_CONDITIONAL_WIRING_PUBLICATION_V1' and wp['status'] == 'PUBLISHED_CONDITIONAL_METADATA_ONLY', 'Wiring receipt')
    require(pp['schema'] == 'DATED_CONDITIONAL_TRAINING_PANEL_PUBLICATION_V1' and pp['status'] == 'PUBLISHED_TRAINING_PAYLOAD_NOT_FITTED', 'Panel receipt')
    exact(wp['wiring_reference'], refs['wiring'], 'Published wiring')
    exact(pp['panel_reference'], refs['training_panel'], 'Published training panel')
    exact(wp['source_hashes'], wiring['source_hashes'], 'Wiring original source claims')
    exact(pp['source_hashes'], panel['source_hashes'], 'Training original source claims')
    for value in (wiring, panel, wp, pp):
        for key in ('point_in_time_verified', 'promotion_allowed', 'execution_authorized', 'fit_performed'):
            require(value[key] is False, 'Conditional evidence authority')
    require(audit['schema'] == 'DATED_TRAINING_PANEL_INDEPENDENT_READBACK_V1' and audit['status'] == 'PASS', 'Saved training audit')
    for key, role in (('panel_sha256', 'training_panel'), ('publication_sha256', 'training_publication'), ('reader_sha256', 'training_reader')):
        require(audit[key] == refs[role]['sha256'], 'Training audit hash binding')
    for key, value in dict(security_count=77, issuer_count=76, observed_security_count=101,
        training_return_rows=126, training_numeric_cells=9702, preserved_sidecar_count=7,
        evaluation_numeric_fields_in_fit_payload=0).items():
        require(type(audit[key]) is int and audit[key] == value, 'Saved training audit scope')
    for key in ('fit_performed', 'raw_redecoded',
        'old_audit_repeated', 'point_in_time_verified', 'legal_training_input_admitted',
        'liquidity_qualification_at_training_cutoff_verified'):
        require(audit[key] is False, 'Saved training audit limitations')
    report = blobs['wiring_review_report'].decode('utf-8')
    require('PASS' in report, 'Saved wiring review report')
    for role in ('wiring', 'wiring_publication', 'wiring_reader'):
        require(refs[role]['sha256'] in report, 'Saved report exact binding')


def save(path, value):
    blob = encode(value)
    with path.open('xb') as stream:
        stream.write(blob)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == blob, 'Saved output bytes')
    return dict(path=str(path), sha256=digest(blob))


def run(*, execute=False):
    require(execute is True, 'Explicit execution')
    require(not OUTPUT.exists(), 'Create-only namespace; no retry')
    refs = references()
    sources = {str(SOURCE): LOADED}
    blobs = {}
    for role, ref in refs.items():
        blob = Path(ref['path']).read_bytes()
        require(digest(blob) == ref['sha256'], 'Fixed source bytes')
        require(ref['path'] not in sources or sources[ref['path']] == ref['sha256'], 'Conflicting sources')
        sources[ref['path']] = ref['sha256']
        blobs[role] = blob
    documents = {role: parse(blobs[role]) for role in ('wiring', 'wiring_publication',
        'training_panel', 'training_publication', 'training_audit')}
    validate_evidence(documents, blobs, refs)
    module = types.ModuleType('_saved_classification_display')
    module.__file__ = refs['core']['path']
    exec(compile(blobs['core'], module.__file__, 'exec'), module.__dict__)
    guard(sources)
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        save(OUTPUT / 'started.json', dict(schema='SAVED_CLASSIFICATION_COVERAGE_STARTED_V1',
            input_references=refs, source_hashes=sources, retry_allowed=False, **FLAGS))
        coverage = module.summarize_saved_classification(wiring=documents['wiring'],
            training_panel=documents['training_panel'],
            wiring_reference=dict(refs['wiring'], json_pointer=''),
            training_reference=dict(refs['training_panel'], json_pointer=''))
        guard(sources)
        result = save(OUTPUT / 'coverage.json', dict(schema='SOURCE_BOUND_SAVED_CLASSIFICATION_COVERAGE_V1',
            coverage=coverage, input_references=refs, source_hashes=sources,
            parent_source_hashes_preserved={role: documents[role]['source_hashes'] for role in ('wiring', 'training_panel')},
            wiring_audit_evidence_type='SAVED_REPORT_AND_READER_NOT_NEW_MACHINE_ATTESTATION',
            direct_source_bytes_authenticated=True, **FLAGS))
        publication = save(OUTPUT / 'publication.json', dict(schema='SAVED_CLASSIFICATION_COVERAGE_PUBLICATION_V1',
            status='PUBLISHED_CONDITIONAL_SAVED_LABEL_COVERAGE', coverage_reference=result,
            source_hashes=sources, **FLAGS))
        guard(sources)
        require({p.name for p in OUTPUT.iterdir()} == {'started.json', 'coverage.json', 'publication.json'}, 'Exact successful namespace')
        for ref in (result, publication):
            require(digest(Path(ref['path']).read_bytes()) == ref['sha256'], 'Final output bytes')
        return result
    except Exception as error:
        save(OUTPUT / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME', error=str(error), retry_allowed=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    print(json.dumps(run(execute=parser.parse_args().execute)))
