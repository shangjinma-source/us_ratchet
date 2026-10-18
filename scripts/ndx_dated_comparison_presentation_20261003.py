"""Publish Chinese display data only after the full comparison summary is audited."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import types


ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED_SHA = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/dated_comparison_presentation_20261003_v1'
BOUND = {
    'summary': ('data/cache/research/dated_comparison_results_summary_20261003_v1/summary.json', '33f7063589b085300f26823d46b2e96c078fbf55144c8ad075269e45417440e9'),
    'publication': ('data/cache/research/dated_comparison_results_summary_20261003_v1/publication.json', 'c66bf1a809c27328eb51dfd542811e6e3d090d5de0154ee5e07f0426ad0f355f'),
    'audit': ('data/cache/research/dated_comparison_results_summary_independent_readback_20261003_v1/independent_readback.json', 'ce5e676d6cf67a1fc1ba057dc8721ed64c1a53dcd2af94750ffb8140ede788c6'),
    'reader': ('scripts/ndx_dated_comparison_results_summary_independent_readback_20261003.py', '0db059aa4f1adf95ca35a5d3d018c842915353bf9f25e73ab90e997437ca2edb'),
    'adapter': ('backtest/ndx_dated_comparison_presentation_research.py', '8c44d30614ea38e608c2bca28e3ee2c90e8b35fef95844c6190e8eb7ac5292d3'),
}
FALSE_FLAGS = ('formal_comparison_passed', 'future_independent_oos', 'promotion_allowed', 'point_in_time_verified')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def digest(blob):
    return hashlib.sha256(blob).hexdigest()


def reference(role):
    path, checksum = BOUND[role]
    return dict(path=str(ROOT / path), sha256=checksum)


def validate(summary, publication, audit, references):
    require(summary['schema'] == 'SOURCE_BOUND_DATED_COMPARISON_RESULTS_SUMMARY_V1', 'Source-bound summary')
    require(publication['schema'] == 'DATED_COMPARISON_RESULTS_SUMMARY_PUBLICATION_V1' and publication['status'] == 'PUBLISHED_SAVED_DIAGNOSTIC_TABLES', 'Published summary')
    require(audit['schema'] == 'DATED_COMPARISON_RESULTS_SUMMARY_INDEPENDENT_READBACK_V1' and audit['status'] == 'PASS', 'Accepted independent summary audit')
    require(encode(publication['summary_reference']) == encode(references['summary']), 'Publication summary binding')
    require(encode(audit['summary_reference']) == encode(references['summary']), 'Audit summary binding')
    require(encode(audit['publication_reference']) == encode(references['publication']), 'Audit publication binding')
    require(audit['reader_sha256'] == references['reader']['sha256'], 'Independent reader source binding')
    require(encode(publication['source_hashes']) == encode(summary['source_hashes']), 'Published source map')
    for document in (summary, publication, audit):
        for key in FALSE_FLAGS:
            require(document[key] is False, 'Diagnostic authority only: ' + key)
    tables = summary['tables']
    require(type(tables['supplied_comparison_count']) is int and tables['supplied_comparison_count'] == 1632, 'Full comparison queue required')
    require(type(tables['not_supplied_count']) is int and tables['not_supplied_count'] == 0, 'No absent comparison can be presented as full delivery')
    return tables


def guard(sources):
    for path, checksum in sources.items():
        require(digest(Path(path).read_bytes()) == checksum, 'Source changed: ' + path)


def save(path, value):
    blob = encode(value)
    with path.open('xb') as handle:
        handle.write(blob)
        handle.flush()
        os.fsync(handle.fileno())
    require(path.read_bytes() == blob, 'Output readback differs')
    return dict(path=str(path), sha256=digest(blob))


def run(*, execute=False):
    require(type(execute) is bool and execute, 'Explicit execute required')
    require(all(type(checksum) is str and len(checksum) == 64 and all(character in '0123456789abcdef' for character in checksum) for _, checksum in BOUND.values()), 'Future source pins pending')
    require(not OUTPUT.exists(), 'Immutable presentation namespace exists')
    references = {role: reference(role) for role in BOUND}
    sources = {str(SOURCE): LOADED_SHA}
    blobs = {}
    for role, ref in references.items():
        blob = Path(ref['path']).read_bytes()
        require(digest(blob) == ref['sha256'], 'Pinned source differs: ' + role)
        blobs[role] = blob
        sources[ref['path']] = ref['sha256']
    tables = validate(*(json.loads(blobs[role]) for role in ('summary', 'publication', 'audit')), references)
    adapter = types.ModuleType('_dated_chinese_presentation')
    adapter.__file__ = references['adapter']['path']
    exec(compile(blobs['adapter'], adapter.__file__, 'exec'), adapter.__dict__)
    display = adapter.build_tables(tables)
    # Include direct source references for the workbook's provenance section.
    display['tables'].append(dict(name='来源索引', headers=['角色', '路径', 'SHA256'], rows=[[role, ref['path'], ref['sha256']] for role, ref in references.items()], percentage_columns=[]))
    guard(sources)
    OUTPUT.mkdir(parents=True, exist_ok=False)
    flags = {key: False for key in (*FALSE_FLAGS, 'economics_recomputed', 'workbook_created', 'transitive_audits_reexecuted')}
    try:
        save(OUTPUT / 'started.json', dict(schema='DATED_COMPARISON_PRESENTATION_STARTED_V1', input_references=references, source_hashes=sources, **flags))
        payload = dict(schema='SOURCE_BOUND_DATED_COMPARISON_CHINESE_DISPLAY_V1', display=display, input_references=references, source_hashes=sources, verification_scope='DIRECT_SUMMARY_PUBLICATION_AUDIT_AND_READER_BYTES_NO_TRANSITIVE_REPLAY', **flags)
        result = save(OUTPUT / 'presentation.json', payload)
        guard(sources)
        require({path.name for path in OUTPUT.iterdir()} == {'started.json', 'presentation.json'}, 'Unexpected output')
        publication = save(OUTPUT / 'publication.json', dict(schema='DATED_COMPARISON_PRESENTATION_PUBLICATION_V1', status='PUBLISHED_DIAGNOSTIC_DISPLAY_DATA_ONLY', presentation_reference=result, source_hashes=sources, **flags))
        guard(sources)
        require({path.name for path in OUTPUT.iterdir()} == {'started.json', 'presentation.json', 'publication.json'}, 'Unexpected published output')
        guard({ref['path']: ref['sha256'] for ref in (result, publication)})
        return result
    except Exception as error:
        save(OUTPUT / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME', error_type=type(error).__name__, error=str(error), retry_allowed=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    print(json.dumps(run(execute=parser.parse_args().execute)))
