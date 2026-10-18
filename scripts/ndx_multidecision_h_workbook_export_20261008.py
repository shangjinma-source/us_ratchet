"""Create-only literal workbook publication from two independently read projections."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import types

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT = ROOT / 'data/cache/research/multidecision_h_workbook_20261008_v1'
BOUND = {}
for _role, _stem, _body in [('presentation', 'multidecision_path_presentation', 'presentation'), ('supplement', 'multidecision_holdings_supplement', 'supplement')]:
    BOUND[_role] = (str(ROOT / f'data/cache/research/{_stem}_20261008_v1/{_body}.json'), None)
    BOUND[_role + '_publication'] = (str(ROOT / f'data/cache/research/{_stem}_20261008_v1/publication.json'), None)
    BOUND[_role + '_audit'] = (str(ROOT / f'data/cache/research/{_stem}_independent_readback_20261008_v1/independent_readback.json'), None)
    BOUND[_role + '_reader'] = (str(ROOT / f'scripts/ndx_{_stem}_independent_readback_20261008.py'), None)
BUILDER = ROOT / 'scripts/ndx_multidecision_h_workbook_20261008.mjs'
BUILDER_SHA = None
CHECKER = ROOT / 'scripts/ndx_multidecision_h_workbook_inspection_20261008.py'
CHECKER_SHA = None
LINEAGE = ROOT / 'backtest/ndx_history_failed_lineage_guard_20261008.py'
LINEAGE_SHA = 'fb72662a3739a1322afe5138856bd31f85328ae5e02bef02301756012f3ed77c'
RUNTIME = Path(r'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node')
NODE = RUNTIME / 'bin/node.exe'
MODULES = RUNTIME / 'node_modules'
FLAGS = dict(full_h_delivery_complete=False, financial_recomputation_performed=False, account_executed=False,
             point_in_time_verified=False, promotion_allowed=False, formal_comparison_passed=False,
             runtime_binary_closure_verified=False, automatic_retry_allowed=False)


def require(value, message):
    if not value: raise ValueError(message)


def sha(blob): return hashlib.sha256(blob).hexdigest()


def encode(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def ref(path, digest):
    require(type(path) is str and Path(path).is_absolute(), 'Absolute source path')
    require(type(digest) is str and re.fullmatch('[a-f0-9]{64}', digest), 'Pending source binding')
    return dict(path=path, sha256=digest)


def merge(sources, reference):
    require(set(reference) == {'path','sha256'}, 'Exact reference')
    ref(**{'path': reference['path'], 'digest': reference['sha256']})
    require(reference['path'] not in sources or sources[reference['path']] == reference['sha256'], 'Conflicting SHA')
    sources[reference['path']] = reference['sha256']


def decode(blob):
    def pairs(items):
        out = {}
        for key, value in items:
            require(key not in out, 'Duplicate JSON key');out[key] = value
        return out
    return json.loads(blob, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def load(reference, sources, body=True):
    merge(sources, reference);p = Path(reference['path'])
    require(not (p.parent / 'failure.json').exists(), 'Failed successful input')
    blob = p.read_bytes();require(sha(blob) == reference['sha256'], 'Source SHA')
    return decode(blob) if body else blob


def module(path, blob):
    value = types.ModuleType('_private_workbook_' + Path(path).stem);value.__file__ = str(path)
    exec(compile(blob, str(path), 'exec'), value.__dict__);return value


def guard(sources, inventories, helper):
    require(sha(SOURCE.read_bytes()) == LOADED, 'Loaded source drift')
    allowed = helper.diagnostic_members(sources)
    for name, digest in sources.items():
        p = Path(name);require(name in allowed or not (p.parent / 'failure.json').exists(), 'Failed source closure')
        with p.open('rb') as f:
            h = hashlib.file_digest(f, 'sha256').hexdigest()
        require(h == digest, 'Source closure drift: ' + name)
    for directory, expected in inventories.items():
        require({str(p.resolve()) for p in Path(directory).rglob('*') if p.is_file()} == set(expected), 'Source inventory drift')


def prepare():
    references = {k: ref(*v) for k,v in BOUND.items()}
    require(set(references) == {r+s for r in ('presentation','supplement') for s in ('','_publication','_audit','_reader')}, 'Exact eight roles')
    builder = ref(str(BUILDER), BUILDER_SHA);checker = ref(str(CHECKER), CHECKER_SHA)
    sources = {str(SOURCE): LOADED};inventories = {}
    helper = module(LINEAGE, load(ref(str(LINEAGE), LINEAGE_SHA), sources, False))
    load(builder, sources, False);checker_blob = load(checker, sources, False)
    documents = {}
    for role, prefix, status in [('presentation','MULTIDECISION_PATH_PRESENTATION','PASS_SAVED_EVIDENCE_PROJECTION'), ('supplement','MULTIDECISION_HOLDINGS_SUPPLEMENT','PASS_SAVED_HOLDINGS_PROJECTION')]:
        doc = load(references[role], sources);pub = load(references[role+'_publication'], sources);audit = load(references[role+'_audit'], sources)
        load(references[role+'_reader'], sources, False)
        require(doc['schema'] == prefix+'_DOCUMENT_V1' and pub['schema'] == prefix+'_PUBLICATION_V1', 'Projection roles')
        require(audit['schema'] == prefix+'_INDEPENDENT_READBACK_V1' and audit['status'] == status, 'Independent projection PASS')
        for value in (pub,audit):
            require(value[role+'_reference'] == references[role], 'Audited projection exact reference')
        require(audit['publication_reference'] == references[role+'_publication'] and audit['reader_sha256'] == references[role+'_reader']['sha256'], 'Audit publication/reader')
        require(doc[role]['full_h_delivery_complete'] is False, 'Partial H preserved')
        for value in (doc,pub,audit):
            require(value['point_in_time_verified'] is False and value['promotion_allowed'] is False, 'No source authority escalation')
            for name,digest in value['source_hashes'].items(): merge(sources,ref(name,digest))
            for directory,names in value.get('source_inventories',{}).items():
                require(directory not in inventories or set(inventories[directory]) == set(names), 'Inventory conflict');inventories[directory]=names
        for key in (role,role+'_publication',role+'_reader'):
            require(audit['source_hashes'].get(references[key]['path']) == references[key]['sha256'], 'Audit source binding')
        parent = Path(references[role]['path']).parent
        require(doc['started_reference'] == pub['started_reference'] and doc['started_reference']['path'] == str(parent/'started.json'), 'Projection start reference')
        load(doc['started_reference'], sources)
        inventories[str(parent)] = [str(parent/name) for name in ('started.json',role+'.json','publication.json')]
        audit_parent = Path(references[role+'_audit']['path']).parent
        start = audit_parent/'started.json';startref = ref(str(start),sha(start.read_bytes()));started = load(startref,sources)
        require(started['artifact_references'][role] == references[role] and started['artifact_references']['publication'] == references[role+'_publication'], 'Audit started inputs')
        inventories[str(audit_parent)] = [str(audit_parent/name) for name in ('started.json','independent_readback.json')]
        documents[role] = doc[role]
    require(len(documents['presentation']['tables']) == 11 and len(documents['supplement']['tables']) == 6, 'Complete 11 plus 6 tables')
    guard(sources,inventories,helper)
    payload = dict(schema='MULTIDECISION_H_WORKBOOK_INPUT_V1', full_h_delivery_complete=False,
                   tables=documents['presentation']['tables']+documents['supplement']['tables'], references=references)
    return payload,sources,inventories,helper,module(CHECKER,checker_blob)


def save(path,value):
    with path.open('xb') as stream: stream.write(encode(value));stream.flush();os.fsync(stream.fileno())
    return ref(str(path),sha(path.read_bytes()))


def run(*, execute=False):
    require(execute is True, 'Explicit workbook publication');require(not OUTPUT.exists(), 'Create-only no retry')
    payload,sources,inventories,helper,checker = prepare()
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started=save(OUTPUT/'started.json',dict(schema='MULTIDECISION_H_WORKBOOK_STARTED_V1',source_hashes=sources,source_inventories=inventories,**FLAGS))
        inputref=save(OUTPUT/'workbook_input.json',payload)
        subprocess.run([str(NODE),str(BUILDER),str(OUTPUT/'workbook_input.json'),str(OUTPUT),str(MODULES)],check=True)
        inspection=checker.inspect_workbook(OUTPUT/'workbook.xlsx',payload)
        guard(sources,inventories,helper)
        result=save(OUTPUT/'cell_readback.json',inspection)
        files={p.name:sha(p.read_bytes()) for p in OUTPUT.iterdir() if p.is_file()}
        expected={'started.json','workbook_input.json','workbook.xlsx','workbook.xlsx.inspect.ndjson','cell_readback.json'}|{f'preview-{i:02d}.png' for i in range(20)}
        require(set(files)==expected,'Exact generated file inventory')
        publication=save(OUTPUT/'publication.json',dict(schema='MULTIDECISION_H_WORKBOOK_PUBLICATION_V1', status='CELL_READBACK_PASS_VISUAL_REVIEW_PENDING',
            started_reference=started,input_reference=inputref,cell_readback_reference=result,input_references=payload['references'],
            source_hashes=sources,source_inventories=inventories,files=files,visual_acceptance_passed=False,**FLAGS))
        guard(sources,inventories,helper)
        require({p.name for p in OUTPUT.iterdir()} == expected|{'publication.json'},'Final output inventory')
        for name,digest in files.items(): require(sha((OUTPUT/name).read_bytes())==digest,'Output bytes drift')
        require(sha(Path(publication['path']).read_bytes())==publication['sha256'],'Publication drift')
        return publication
    except BaseException as error:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),**FLAGS));raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    print(json.dumps(run(execute=parser.parse_args().execute)))
