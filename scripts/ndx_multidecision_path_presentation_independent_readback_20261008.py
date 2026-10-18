"""Independent saved presentation reader. No publisher or projection execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import types

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT = ROOT / 'data/cache/research/multidecision_path_comparison_20261003_v1'
AUDIT_ROOT = ROOT / 'data/cache/research/multidecision_path_comparison_independent_readback_20261003_v1'
PRESENTATION_ROOT = ROOT / 'data/cache/research/multidecision_path_presentation_20261008_v1'
OUTPUT = ROOT / 'data/cache/research/multidecision_path_presentation_independent_readback_20261008_v1'
BOUND = {
    'comparison': (str(PARENT / 'comparison.json'), '40e32bbea680775252bcdc880c5ca07cc7163ed5e0af42707ac8c56a009e1656'),
    'publication': (str(PARENT / 'publication.json'), 'bdbb1abdff6253227b73329b4a3a7081f98a12fb180d6bbd06724a2798f4430e'),
    'audit': (str(AUDIT_ROOT / 'independent_readback.json'), '4d50cc9f2d8be07697242363849cc2d051a984dca55f3d325d201f11da942fd2'),
    'reader': (str(ROOT / 'scripts/ndx_multidecision_path_comparison_independent_readback_20261003.py'), 'bc3e4f8b70c7cc01b04089f7c43d9ba7aae511159747bfb47ce6b5e4996fc4d7'),
    'candidate_inputs': (str(ROOT / 'data/cache/research/multidecision_account_inputs_20261003_v1/inputs.json'), 'c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9'),
}
PURE = ROOT / 'backtest/ndx_multidecision_path_presentation_research.py'
PURE_SHA = 'f485d2489285c0a06eef0f0d82490bb0944af90ba7308c807dbaa030eab1e447'
ARTIFACT_BOUND = {
    'presentation': (str(PRESENTATION_ROOT / 'presentation.json'), 'e724a501254b9685144a1c1c98011ae1f248d2e584983c0071de6e9cde2c2782'),
    'publication': (str(PRESENTATION_ROOT / 'publication.json'), 'cd7d75b84154e5004aadb6d4d660566b68dd99384e0b6ec706c8cbe76b02008e'),
    'publisher': (str(ROOT / 'scripts/ndx_multidecision_path_presentation_20261008.py'), '2fc3b4718742534a7e6eed5b2d63f5d52379e5b3e1742d68a9bb394021479934'),
    'checker': (str(ROOT / 'backtest/ndx_multidecision_path_presentation_inspection_research.py'), '43281e297546f352c735c3656ff9624d1011c4ee9260e608a297464f99212d8c'),
}
LINEAGE = ROOT / 'backtest/ndx_history_failed_lineage_guard_20261008.py'
LINEAGE_SHA = 'fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
FLAGS = dict.fromkeys(('account_executed', 'fit_performed', 'financial_recomputation_performed',
    'formal_comparison_passed', 'formal_noninferiority_passed', 'future_independent_oos',
    'point_in_time_verified', 'promotion_allowed', 'source_bytes_authenticated',
    'independent_presentation_readback_passed', 'automatic_retry_allowed'), False)


def require(value, message):
    if not value:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def exact(left, right):
    require(encode(left) == encode(right), 'Exact saved evidence')


def sha(blob):
    return hashlib.sha256(blob).hexdigest()


def reference(path, digest):
    require(type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest), 'Pending source pin')
    require(type(path) is str and Path(path).is_absolute(), 'Absolute source path')
    return dict(path=path, sha256=digest)


def merge(sources, item):
    require(type(item) is dict and set(item) == {'path', 'sha256'}, 'Exact reference fields')
    reference(item['path'], item['sha256'])
    require(item['path'] not in sources or sources[item['path']] == item['sha256'], 'Conflicting source SHA')
    sources[item['path']] = item['sha256']


def decode(blob):
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(blob, object_pairs_hook=pairs,
        parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def load(item, sources, *, body=True):
    merge(sources, item)
    path = Path(item['path'])
    require(not (path.parent / 'failure.json').exists(), 'Failed successful-role source')
    blob = path.read_bytes()
    require(sha(blob) == item['sha256'], 'Consumed source bytes')
    return decode(blob) if body else blob


def private_module(path, blob):
    module = types.ModuleType('_private_presentation_' + Path(path).stem)
    module.__file__ = str(path)
    exec(compile(blob, str(path), 'exec'), module.__dict__)
    return module


def guard(sources, inventories, helper):
    require(sha(SOURCE.read_bytes()) == LOADED, 'Loaded publisher drift')
    diagnostics = helper.diagnostic_members(sources)
    for name, digest in sources.items():
        path = Path(name)
        require(name in diagnostics or not (path.parent / 'failure.json').exists(), 'Failed source closure')
        actual = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1048576), b''):
                actual.update(block)
        require(actual.hexdigest() == digest, 'Source closure drift: ' + name)
    for directory, expected in inventories.items():
        actual = {str(p.resolve()) for p in Path(directory).rglob('*') if p.is_file()}
        require(actual == set(expected), 'Exact source inventory: ' + directory)


def prepare():
    refs = {role: reference(*spec) for role, spec in BOUND.items()}
    pure_ref = reference(str(PURE), PURE_SHA)
    helper_ref = reference(str(LINEAGE), LINEAGE_SHA)
    sources = {str(SOURCE): LOADED}
    helper = private_module(LINEAGE, load(helper_ref, sources, body=False))
    pure_blob = load(pure_ref, sources, body=False)
    docs = {role: load(item, sources) for role, item in refs.items() if role != 'reader'}
    load(refs['reader'], sources, body=False)
    comp, pub, audit = (docs[key] for key in ('comparison', 'publication', 'audit'))
    require(pub['status'] == 'PUBLISHED_SINGLE_PATH_DIAGNOSTICS_PENDING_INDEPENDENT_READBACK_NOT_FORMAL_GATE', 'K publication state')
    exact(pub['comparison_reference'], refs['comparison'])
    exact(audit['comparison_reference'], refs['comparison'])
    exact(audit['publication_reference'], refs['publication'])
    require(audit['status'] == 'PASS' and audit['reader_sha256'] == refs['reader']['sha256'], 'Fixed K independent PASS')
    exact(comp['input_references'], pub['input_references'])
    exact(comp['input_references'], audit['input_references'])
    exact(comp['input_references']['candidate_inputs'], refs['candidate_inputs'])
    exact(comp['source_hashes'], pub['source_hashes'])
    exact(comp['source_inventories'], pub['source_inventories'])
    inventories = {}
    for doc in (comp, pub, audit):
        for path, digest in doc['source_hashes'].items():
            merge(sources, reference(path, digest))
        for directory, files in doc['source_inventories'].items():
            require(type(files) is list and len(files) == len(set(files)), 'Unique source inventory')
            require(directory not in inventories or set(inventories[directory]) == set(files), 'Conflicting inventory')
            inventories[directory] = files
    for item in list(comp['input_references'].values()) + [refs[k] for k in ('comparison', 'publication', 'reader')]:
        require(audit['source_hashes'].get(item['path']) == item['sha256'], 'K audit source role closure')
    for role, filename in (('raw_reference', 'raw_result.json'), ('started_reference', 'started.json')):
        item = pub[role]
        exact(item['path'], str(PARENT / filename))
        body = load(item, sources)
        exact(body['input_references'], comp['input_references'])
        exact(body['source_hashes'], comp['source_hashes'])
        exact(body['source_inventories'], comp['source_inventories'])
        if role == 'raw_reference':
            exact(comp['raw_reference'], item)
            exact(body['result'], comp['comparison'])
            require(body['returned'] is True and body['call_invoked'] is True and body['error'] is None, 'K raw successful return')
            exact(body['started_reference'], pub['started_reference'])
    for directory, names in ((PARENT, ('started.json', 'raw_result.json', 'comparison.json', 'publication.json')),
                             (AUDIT_ROOT, ('started.json', 'independent_readback.json'))):
        expected = sorted(str(directory / name) for name in names)
        require(str(directory) not in inventories or set(inventories[str(directory)]) == set(expected), 'Fixed K inventory')
        inventories[str(directory)] = expected
    audit_start_path = AUDIT_ROOT / 'started.json'
    # This original start has no separate external pin; preserve that limitation.
    audit_start_ref = reference(str(audit_start_path), sha(audit_start_path.read_bytes()))
    audit_start = load(audit_start_ref, sources)
    exact(audit_start['comparison_reference'], refs['comparison'])
    exact(audit_start['publication_reference'], refs['publication'])
    exact(audit_start['source_hashes'], audit['source_hashes'])
    guard(sources, inventories, helper)
    return refs, docs, sources, inventories, helper, pure_blob, audit_start_ref


def save(path, value):
    blob = encode(value)
    with path.open('xb') as stream:
        stream.write(blob)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == blob, 'Durable output bytes')
    return reference(str(path), sha(blob))


def flags(document):
    for key in FLAGS:
        require(document[key] is False, 'Saved presentation authority: ' + key)


def readback(*, execute=False):
    require(execute is True, 'Explicit independent readback')
    require(not OUTPUT.exists(), 'Create-only, no retry')
    artifacts = {role: reference(*spec) for role, spec in ARTIFACT_BOUND.items()}
    refs, docs, sources, inventories, helper, unused_pure_bytes, audit_start = prepare()
    # Reconstruct the producer's closed source map independently. Its projection
    # source is authenticated above but never imported or executed by this reader.
    expected = dict(sources)
    del expected[str(SOURCE)]
    merge(expected, artifacts['publisher'])
    load(artifacts['publisher'], sources, body=False)
    checker_blob = load(artifacts['checker'], sources, body=False)
    document = load(artifacts['presentation'], sources)
    publication = load(artifacts['publication'], sources)
    exact(artifacts['presentation']['path'], str(PRESENTATION_ROOT / 'presentation.json'))
    exact(artifacts['publication']['path'], str(PRESENTATION_ROOT / 'publication.json'))
    require(document['schema'] == 'MULTIDECISION_PATH_PRESENTATION_DOCUMENT_V1', 'Presentation document role')
    require(publication['schema'] == 'MULTIDECISION_PATH_PRESENTATION_PUBLICATION_V1', 'Presentation publication role')
    require(publication['status'] == 'PUBLISHED_SAVED_EVIDENCE_PROJECTION_PENDING_INDEPENDENT_READBACK', 'Published pending independent check')
    exact(publication['presentation_reference'], artifacts['presentation'])
    exact(publication['started_reference'], document['started_reference'])
    exact(document['started_reference']['path'], str(PRESENTATION_ROOT / 'started.json'))
    started = load(document['started_reference'], sources)
    require(started['schema'] == 'MULTIDECISION_PRESENTATION_STARTED_V1', 'Presentation started role')
    for value in (document, publication, started):
        flags(value)
        exact(value['input_references'], refs)
        exact(value['source_hashes'], expected)
    exact(document['source_inventories'], inventories)
    exact(document['original_audit_started_reference'], audit_start)
    require(document['original_audit_start_externally_anchored'] is False and document['independent_readback_status'] == 'PENDING', 'Original evidence limits')
    inventories[str(PRESENTATION_ROOT)] = sorted(str(PRESENTATION_ROOT / name) for name in ('started.json', 'presentation.json', 'publication.json'))
    guard(sources, inventories, helper)
    checker = private_module(artifacts['checker']['path'], checker_blob)
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        start_ref = save(OUTPUT / 'started.json', dict(schema='MULTIDECISION_PRESENTATION_INDEPENDENT_STARTED_V1',
            input_references=refs, artifact_references=artifacts, source_hashes=sources, **FLAGS))
        inspection = checker.inspect_presentation(presentation=document['presentation'], comparison_document=docs['comparison'],
            publication=docs['publication'], audit=docs['audit'], candidate_inputs_document=docs['candidate_inputs'], references=refs)
        guard(sources, inventories, helper)
        report_ref = save(OUTPUT / 'independent_readback.json', dict(schema='MULTIDECISION_PATH_PRESENTATION_INDEPENDENT_READBACK_V1',
            status='PASS_SAVED_EVIDENCE_PROJECTION', presentation_reference=artifacts['presentation'], publication_reference=artifacts['publication'],
            reader_sha256=LOADED, input_references=refs, artifact_references=artifacts, source_hashes=sources,
            source_inventories=inventories, inspection=inspection, publisher_called=False, projection_core_called=False,
            account_engine_called=False, full_h_delivery_complete=False, **FLAGS))
        guard(sources, inventories, helper)
        require({p.name for p in OUTPUT.iterdir()} == {'started.json', 'independent_readback.json'}, 'Exact independent output inventory')
        for item in (start_ref, report_ref):
            require(sha(Path(item['path']).read_bytes()) == item['sha256'], 'Final independent report drift')
        return report_ref
    except BaseException as error:
        save(OUTPUT / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME', error_type=type(error).__name__,
            error=str(error), retry_allowed=False, **FLAGS))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true')
    print(json.dumps(readback(execute=parser.parse_args().execute)))
