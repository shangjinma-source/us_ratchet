"""Independent saved H supplement verification; no producer or risk invocation."""
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
PARENT = ROOT / 'data/cache/research/multidecision_holdings_supplement_20261008_v1'
OUTPUT = ROOT / 'data/cache/research/multidecision_holdings_supplement_independent_readback_20261008_v1'
ARTIFACT_BOUND = {'supplement': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_holdings_supplement_20261008_v1\\supplement.json', 'dc23f888b033ada98b34357c960980ca0a02eecfbaeaca40a259155adf0bf8ae'), 'publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_holdings_supplement_20261008_v1\\publication.json', '889733dc35d83cf551b14a9abffdc0eb585d92df57d8d990234441bb106e6fc6'), 'publisher': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_holdings_supplement_20261008.py', '86e269e088fbc422db418708282a38846c1051f65cb64f8bb824fc8f161c7cf1'), 'checker': ('E:\\Git\\us_ratchet\\backtest\\ndx_multidecision_holdings_supplement_inspection_research.py', '994b933a33d2f35ada2dde71f7f05e42fe7da397e27bcc57f92455578cabf439')}
PURE = ROOT / 'backtest/ndx_multidecision_holdings_supplement_research.py'
PURE_SHA = '9c06de5f6bfed3b8703f56dfca623521c2b212ec7b7c33e48daa61e6e0c5c4ed'
LINEAGE = ROOT / 'backtest/ndx_history_failed_lineage_guard_20261008.py'
LINEAGE_SHA = 'fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
BOUND = {'candidate_inputs': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_inputs_20261003_v1\\inputs.json', 'c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9'), 'candidate_inputs_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_inputs_20261003_v1\\publication.json', '64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940'), 'candidate_inputs_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_inputs_independent_readback_20261003_v1\\independent_readback.json', '8568bbe2ea6fa33d2aa9956a72a8b11d902f353b6078044a9a832384ec0886fb'), 'candidate_inputs_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_account_inputs_independent_readback_20261003.py', '85f3fd668a948bf9b3e68f1d4c013ee6def02d806f57373c41ef65698443576d'), 'candidate_execution': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_execution_20261003_v1\\result.json', 'c79aafa533d78be14f888cd109d9942702c829c39d5ce0d09904501b5c812870'), 'candidate_execution_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_execution_20261003_v1\\publication.json', 'e1b00c1c1f8e4b4d31893e77ba46bc12009ba3e5fd452fdca1b1b01266ab68c7'), 'candidate_execution_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_execution_independent_readback_20261003_v1\\independent_readback.json', '33ebcb571c81793f92070c8db789b409b98eca139778c0c192c80fa6abcc74bb'), 'candidate_execution_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_account_execution_independent_readback_20261003.py', '69c54a144ca582a8537a4c52b0fbb6fdf61a0f2ece0d4233206cc87f6f729ca2'), 'control_inputs': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_incumbent_inputs_20261003_v1\\inputs.json', '9705b1ed2e42351050a5e413dcbe73fdc5d42efc16a03a79b560fe0c69f68aa4'), 'control_inputs_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_incumbent_inputs_20261003_v1\\publication.json', '5b8da9d3440422ec8899d5ad73abf589ea43a1869aa4aa84b6227ce480958fe9'), 'control_inputs_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_incumbent_inputs_independent_readback_20261003_v1\\independent_readback.json', '48aac644a66b2832d48ff6ea7100e3aa720c68da2e6d1a3bc35e1f5ae95d02f1'), 'control_inputs_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_incumbent_inputs_independent_readback_20261003.py', 'de6b6a6da0c3aa327855e029e937a25d66069d98b01598b69818534984f8ffc9'), 'control_execution': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_incumbent_execution_20261003_v1\\result.json', 'f837b2a71c7a0d9a08610e211d2c7b1a799902aa38ae1e92d661906a806c2eb4'), 'control_execution_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_incumbent_execution_20261003_v1\\publication.json', 'c56230fca7cc7de0c7ef79604a4588eb7afa3202f61c0baaeae8b5609d5c4afd'), 'control_execution_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_incumbent_execution_independent_readback_20261003_v1\\independent_readback.json', '8b8e318426c94b6a70389a724f50c30df68c807204ad789f2159185cd943e975'), 'control_execution_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_incumbent_execution_independent_readback_20261003.py', '35cd3824d935f75eb00c05161f89291f287587122fce0b63f7dd8a8fa1fff730')}
FLAGS = dict.fromkeys(('account_executed', 'risk_recomputed', 'chain_aggregates_computed',
    'financial_recomputation_performed', 'source_bytes_authenticated', 'point_in_time_verified',
    'promotion_allowed', 'full_h_delivery_complete', 'independent_readback_passed', 'automatic_retry_allowed'), False)


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

def save(path, value):
    blob = encode(value)
    with path.open('xb') as stream:
        stream.write(blob)
        stream.flush()
        os.fsync(stream.fileno())
    require(path.read_bytes() == blob, 'Durable output bytes')
    return reference(str(path), sha(blob))


def prepare():
    refs = {key: reference(*value) for key, value in BOUND.items()}
    pure_ref = reference(str(PURE), PURE_SHA)
    sources = {str(SOURCE): LOADED}
    helper = private_module(LINEAGE, load(reference(str(LINEAGE), LINEAGE_SHA), sources, body=False))
    pure_blob = load(pure_ref, sources, body=False)
    docs = {}
    for key, ref in refs.items():
        value = load(ref, sources, body=not key.endswith('_reader'))
        if not key.endswith('_reader'): docs[key] = value
    inventories = {}
    observed_starts = []
    raws = {}
    for role, prefix in (('candidate', 'MULTIDECISION_STATEFUL_ACCOUNT'), ('control', 'MULTIDECISION_ORIGINAL_EIGHT')):
        for stage in ('inputs', 'execution'):
            key = role + '_' + stage
            doc, pub, audit = (docs[name] for name in (key, key + '_publication', key + '_audit'))
            reference_key = 'inputs_reference' if stage == 'inputs' else 'result_reference'
            schema = prefix + '_INPUTS' if stage == 'inputs' else ('MULTIDECISION_ACCOUNT_EXECUTION' if role == 'candidate' else 'MULTIDECISION_INCUMBENT_ACCOUNT_EXECUTION')
            require(pub['schema'] == schema + '_PUBLICATION_V1' and audit['schema'] == schema + '_INDEPENDENT_READBACK_V1', 'Parent schema roles')
            require(audit['status'] == 'PASS' and audit['reader_sha256'] == refs[key + '_reader']['sha256'], 'Original independent PASS')
            exact(pub[reference_key], refs[key]);exact(audit[reference_key], refs[key]);exact(audit['publication_reference'], refs[key + '_publication'])
            exact(pub['source_hashes'], doc['source_hashes'])
            expected_status = 'PUBLISHED_CONDITIONAL_ACCOUNT_RETURNS_PENDING_INDEPENDENT_READBACK' if stage == 'execution' else ('PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS' if role == 'candidate' else 'PUBLISHED_CONTROL_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS')
            require(pub['status'] == expected_status, 'Published role status')
            for item in (doc, pub, audit):
                require(item['point_in_time_verified'] is False and item['promotion_allowed'] is False, 'Conditional parent authority')
                for path, digest in item['source_hashes'].items(): merge(sources, reference(path, digest))
                for directory, names in item.get('source_inventories', {}).items():
                    require(directory not in inventories or set(inventories[directory]) == set(names), 'Conflicting original inventory')
                    inventories[directory] = names
            for item in (refs[key], refs[key + '_publication'], refs[key + '_reader']):
                require(audit['source_hashes'].get(item['path']) == item['sha256'], 'Audit direct source role')
            parent = Path(refs[key]['path']).parent
            expected = {str(parent / name) for name in (Path(refs[key]['path']).name, 'publication.json', 'started.json')}
            startref = pub['started_reference'];exact(startref['path'], str(parent / 'started.json'));start = load(startref, sources)
            exact(start['source_hashes'], doc['source_hashes'])
            audit_root = Path(refs[key + '_audit']['path']).parent
            audit_start = audit_root / 'started.json'
            observed = reference(str(audit_start), sha(audit_start.read_bytes()))
            saved_start = load(observed, sources);observed_starts.append(observed)
            exact(saved_start[reference_key], refs[key]);exact(saved_start['publication_reference'], refs[key + '_publication'])
            inventories[str(audit_root)] = sorted(str(audit_root / name) for name in ('started.json', 'independent_readback.json'))
            if stage == 'execution':
                expected_input_refs = dict(inputs=refs[role + '_inputs'], publication=refs[role + '_inputs_publication'], readback=refs[role + '_inputs_audit'], reader=refs[role + '_inputs_reader'])
                exact(doc['input_references'], expected_input_refs);exact(pub['input_references'], expected_input_refs)
                require(doc['failure'] is None and len(doc['rows']) == len(audit['rows']) == 16, 'Complete 16 execution slots')
                raws[role] = []
                for index, (row, checked) in enumerate(zip(doc['rows'], audit['rows'])):
                    exact(checked['track_index'], index);exact(checked['coordinate'], [row['fx_mode'], row['lane'], row['track']]);exact(checked['outcome'], row['outcome'])
                    folder = parent / 'tracks' / f'{index:02d}'
                    for name, filename in (('started_reference', 'started.json'), ('postcheck_reference', 'postcheck.json'), ('raw_reference', 'raw_result.json')):
                        item = row[name]
                        exact(checked['saved_references'][name], item)
                        if item is None:
                            require(name == 'raw_reference' and row['outcome'] == 'BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT', 'Only blocked RAW absence')
                            continue
                        exact(item['path'], str(folder / filename))
                        require(audit['source_hashes'].get(item['path']) == item['sha256'], 'Audited track source bytes')
                        value = load(item, sources);expected.add(item['path'])
                        if name == 'raw_reference':
                            require(checked['inspection']['status'] == 'PASS', 'Original ledger inspection PASS')
                            raws[role].append(dict(reference=item, document=value))
                    if row['raw_reference'] is None: raws[role].append(None)
                require(len(raws[role]) == 16, 'Full raw positions')
            inventories[str(parent)] = sorted(expected)
    guard(sources, inventories, helper)
    arguments = {key: docs[key] for key in ('candidate_inputs', 'control_inputs', 'candidate_execution', 'control_execution')}
    arguments.update(raw_documents=raws, references={key: refs[key] for key in arguments})
    return refs, sources, inventories, helper, pure_blob, arguments, observed_starts


def flags(document):
    for key in FLAGS: require(document[key] is False, 'Original scope flag: ' + key)


def readback(*, execute=False):
    require(execute is True, 'Explicit independent supplement readback')
    require(not OUTPUT.exists(), 'Create-only, no retry')
    artifacts = {key: reference(*value) for key, value in ARTIFACT_BOUND.items()}
    refs, sources, inventories, helper, unused_projection_bytes, arguments, observed_starts = prepare()
    expected = dict(sources);del expected[str(SOURCE)];merge(expected, artifacts['publisher'])
    load(artifacts['publisher'], sources, body=False)
    checker_blob = load(artifacts['checker'], sources, body=False)
    document = load(artifacts['supplement'], sources);pub = load(artifacts['publication'], sources)
    exact(artifacts['supplement']['path'], str(PARENT / 'supplement.json'))
    exact(artifacts['publication']['path'], str(PARENT / 'publication.json'))
    require(document['schema'] == 'MULTIDECISION_HOLDINGS_SUPPLEMENT_DOCUMENT_V1' and pub['schema'] == 'MULTIDECISION_HOLDINGS_SUPPLEMENT_PUBLICATION_V1', 'Supplement document roles')
    require(pub['status'] == 'PUBLISHED_SAVED_HOLDINGS_PENDING_INDEPENDENT_READBACK', 'Successful saved publication')
    exact(pub['supplement_reference'], artifacts['supplement']);exact(pub['started_reference'], document['started_reference'])
    exact(document['started_reference']['path'], str(PARENT / 'started.json'))
    start = load(document['started_reference'], sources)
    require(start['schema'] == 'MULTIDECISION_HOLDINGS_SUPPLEMENT_STARTED_V1', 'Supplement start role')
    for value in (document, pub, start):
        exact(value['input_references'], refs);exact(value['source_hashes'], expected);flags(value)
    exact(document['source_inventories'], inventories)
    exact(document['original_audit_started_references'], observed_starts)
    require(document['original_audit_starts_externally_anchored'] is False and document['independent_readback_status'] == 'PENDING', 'Original limits preserved')
    inventories[str(PARENT)] = sorted(str(PARENT / name) for name in ('started.json', 'supplement.json', 'publication.json'))
    guard(sources, inventories, helper)
    checker = private_module(artifacts['checker']['path'], checker_blob)
    OUTPUT.mkdir(parents=True, exist_ok=False)
    try:
        startref = save(OUTPUT / 'started.json', dict(schema='MULTIDECISION_HOLDINGS_SUPPLEMENT_INDEPENDENT_STARTED_V1', input_references=refs, artifact_references=artifacts, source_hashes=sources, **FLAGS))
        inspection = checker.inspect_supplement(supplement=document['supplement'], **arguments)
        guard(sources, inventories, helper)
        result = save(OUTPUT / 'independent_readback.json', dict(schema='MULTIDECISION_HOLDINGS_SUPPLEMENT_INDEPENDENT_READBACK_V1',
            status='PASS_SAVED_HOLDINGS_PROJECTION', supplement_reference=artifacts['supplement'], publication_reference=artifacts['publication'],
            input_references=refs, artifact_references=artifacts, reader_sha256=LOADED, source_hashes=sources, source_inventories=inventories,
            inspection=inspection, publisher_called=False, projection_core_called=False, account_engine_called=False, **FLAGS))
        guard(sources, inventories, helper)
        require({p.name for p in OUTPUT.iterdir()} == {'started.json', 'independent_readback.json'}, 'Exact independent output namespace')
        for item in (startref, result): require(sha(Path(item['path']).read_bytes()) == item['sha256'], 'Final report bytes')
        return result
    except BaseException as error:
        save(OUTPUT / 'failure.json', dict(status='FAILED_DO_NOT_CONSUME', error_type=type(error).__name__, error=str(error), retry_allowed=False, **FLAGS))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser();parser.add_argument('--execute', action='store_true')
    print(json.dumps(readback(execute=parser.parse_args().execute)))
