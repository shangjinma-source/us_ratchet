"""Single-publication saved-evidence inventory and deduplicated raw extraction."""
import argparse
from copy import deepcopy
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/full_pool_saved_evidence_batch_20261002_v1'
PINS={
    'helper':('scripts/ndx_full_pool_saved_evidence_inventory_20261002.py','71dc0bd7a2c97179686246a82a6de427186a22477c151745c4d9351439e9c481'),
    'extractor':('backtest/ndx_saved_sec_cover_evidence_research.py','b20de9c133a5decf89ff4a63e9d926a17880788c1806dfcdd3b830823ad06ce2')}
FLAGS=dict.fromkeys(('point_in_time_verified','identity_interval_verified','provider_binding_verified',
    'risk_interval_verified','legal_training_input_admitted','promotion_allowed','execution_authorized',
    'fit_performed','http_performed','old_audit_called','prices_recomputed','source_assertions_authenticated',
    'full_transitive_source_closure_reverified','claimed_section_hashes_reverified'),False)


def require(ok,message):
    if not ok: raise ValueError(message)


def sha(raw): return hashlib.sha256(raw).hexdigest()


def assemble_batch(inventory,raw_outcomes,extractor):
    """Only hash-matching input bytes reach the passed extractor, once per SHA."""
    require(inventory['schema']=='FULL_POOL_SAVED_EVIDENCE_INVENTORY_V1','Inventory schema')
    require(len(inventory['rows'])==101 and len({row['ticker'] for row in inventory['rows']})==101
            and len(inventory['historical_denominators'])==15,'Full current/historical denominator')
    queue=inventory['extraction_queue']
    require(type(queue) is list and len(queue)==53,'Complete extraction queue required')
    require(len({item['inventory_row_index'] for item in queue})==len(queue),'Duplicate queue row')
    for flag in FLAGS:
        if flag in inventory: require(inventory[flag] is False,'Inventory authority changed')
    grouped={}; rows=[]
    require(set(raw_outcomes)=={item['raw_reference']['path'] for item in queue},'Raw outcome paths differ')
    for index,item in enumerate(queue):
        row_index=item['inventory_row_index']
        require(type(row_index) is int and 0<=row_index<101 and inventory['rows'][row_index]['ticker']==item['ticker'],'Queue row binding')
        ref=item['raw_reference']; review=item['review_match']['decision']
        require(ref==item['review_match']['raw_reference'] and review['raw_sha256']==ref['sha256'],'Review/raw binding')
        outcome=raw_outcomes[ref['path']]
        status=outcome['status']
        require(status in {'MISSING_SOURCE','RAW_SHA_MISMATCH','HASH_MATCHED'},'Unknown raw status')
        row={'queue_index':index,'inventory_row_index':row_index,'ticker':item['ticker'],
             'original_queue_item':deepcopy(item),'status':status,'document_sha256':None,**FLAGS}
        if status=='HASH_MATCHED':
            raw=outcome['raw_bytes']; require(type(raw) is bytes and sha(raw)==ref['sha256'],'Hash-matching bytes required')
            group=grouped.setdefault(ref['sha256'],{'raw_bytes':raw,'references':[],'reviews':[],'row_indexes':[]})
            require(group['raw_bytes']==raw,'SHA group byte disagreement')
            group['references'].append(deepcopy(ref)); group['reviews'].append(deepcopy(item['review_match']))
            group['row_indexes'].append(index); row['document_sha256']=ref['sha256']
        elif status=='RAW_SHA_MISMATCH':
            require(type(outcome['actual_sha256']) is str and outcome['actual_sha256']!=ref['sha256'],'Mismatch evidence')
            row['actual_sha256']=outcome['actual_sha256']
        rows.append(row)
    documents={}; call_count=0
    for digest,group in grouped.items():
        queries=[]
        for review in group['reviews']:
            phrase=review['decision'].get('source_phrase')
            if type(phrase) is str and phrase.strip() and phrase not in queries: queries.append(phrase)
        envelope={'expected_raw_sha256':digest,'phrase_queries':queries,
            'original_review_decisions':deepcopy(group['reviews'])}
        call_count+=1
        try:
            extraction=extractor(group['raw_bytes'],group['references'][0],envelope)
            require(extraction['raw_sha256']==digest,'Extractor raw identity changed')
            document={'status':'EXTRACTED_SAVED_FACTS_NOT_IDENTITY_ADMISSION','extraction':extraction}
        except Exception as error:
            document={'status':'EXTRACTION_ERROR_NOT_ELIGIBLE','error_type':type(error).__name__,'error':str(error)}
        document.update(raw_sha256=digest,raw_references=group['references'],
            original_review_matches=group['reviews'],review_envelope=envelope,**FLAGS)
        documents[digest]=document
        for row_index in group['row_indexes']: rows[row_index]['status']=document['status']
    return {'schema':'FULL_POOL_SAVED_EVIDENCE_BATCH_V1','inventory_preserved':deepcopy(inventory),
        'extraction_rows':rows,'observed_denominator':101,'historical_denominator':15,
        'requested_extraction_row_count':53,'unique_raw_extractor_call_count':call_count,
        'status_counts':{status:sum(row['status']==status for row in rows) for status in
            ('MISSING_SOURCE','RAW_SHA_MISMATCH','EXTRACTED_SAVED_FACTS_NOT_IDENTITY_ADMISSION','EXTRACTION_ERROR_NOT_ELIGIBLE')},
        'document_references':{},'original_review_risk_reclassified':False,**FLAGS},documents


def guard(sources,missing):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded batch source drift')
    for path,digest in sources.items(): require(sha(Path(path).read_bytes())==digest,'Source drift: '+path)
    require(all(not Path(path).exists() for path in missing),'Previously missing source appeared')


def write_new(path,value):
    raw=(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    with path.open('xb') as stream:
        stream.write(raw);stream.flush();os.fsync(stream.fileno())
    require(path.read_bytes()==raw,'Output readback differs')
    return {'path':str(path),'sha256':sha(raw)}


def run():
    require(not OUTPUT.exists(),'Fixed namespace exists; no retry')
    sources={str(SOURCE):LOADED_SHA}; refs={}; modules={}
    for role,(relative,digest) in PINS.items():
        require(type(digest) is str and len(digest)==64,'Pending source pin')
        path=ROOT/relative;require(sha(path.read_bytes())==digest,'Pinned source drift')
        sources[str(path)]=digest;refs[role]={'path':str(path),'sha256':digest}
        name=relative[:-3].replace('/','.')
        require(name not in sys.modules,'Fresh CLI required')
        modules[role]=importlib.import_module(name)
        require(Path(modules[role].__file__).resolve()==path.resolve(),'Loaded module path mismatch')
    helper=modules['helper'];docs,parent_refs,parent_sources=helper.read_inputs()
    for path,digest in parent_sources.items():
        require(path not in sources or sources[path]==digest,'Source hash conflict'); sources[path]=digest
    inventory=helper.assemble_inventory(docs,parent_refs)
    missing=[];outcomes={}
    for item in inventory['extraction_queue']:
        ref=item['raw_reference'];path=Path(ref['path'])
        if str(path) in outcomes: continue
        if not path.exists():
            missing.append(str(path));outcomes[str(path)]={'status':'MISSING_SOURCE'};continue
        raw=path.read_bytes();digest=sha(raw);sources[str(path)]=digest
        outcomes[str(path)]=({'status':'HASH_MATCHED','raw_bytes':raw} if digest==ref['sha256'] else
                             {'status':'RAW_SHA_MISMATCH','actual_sha256':digest})
    guard(sources,missing);OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        write_new(OUTPUT/'started.json',{'source_hashes':sources,'missing_source_paths':missing,'retry_allowed':False,**FLAGS})
        batch,documents=assemble_batch(inventory,outcomes,modules['extractor'].extract_saved_sec_evidence)
        (OUTPUT/'documents').mkdir(exist_ok=False)
        for digest,document in documents.items():
            batch['document_references'][digest]=write_new(OUTPUT/'documents'/f'{digest}.json',document)
        batch.update(input_references=refs,source_hashes=sources,missing_source_paths=missing)
        guard(sources,missing);result_ref=write_new(OUTPUT/'batch.json',batch);guard(sources,missing)
        receipt=write_new(OUTPUT/'publication.json',{'schema':'FULL_POOL_SAVED_EVIDENCE_BATCH_PUBLICATION_V1',
            'status':'PUBLISHED_EVIDENCE_ONLY_NOT_ADMISSION','batch_reference':result_ref,'source_hashes':sources,**FLAGS})
        guard(sources,missing)
        for ref in [result_ref,receipt]+list(batch['document_references'].values()):
            require(sha(Path(ref['path']).read_bytes())==ref['sha256'],'Published bytes changed')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','documents','batch.json','publication.json'},'Unexpected namespace entries')
        require({p.name for p in (OUTPUT/'documents').iterdir()}=={digest+'.json' for digest in documents},'Unexpected document entries')
        return {'batch_reference':result_ref,'publication_reference':receipt,'status_counts':batch['status_counts']}
    except Exception as error:
        write_new(OUTPUT/'failure.json',{'status':'FAILED_DO_NOT_CONSUME','error':str(error),'retry_allowed':False})
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--execute',action='store_true')
    if not parser.parse_args().execute: parser.error('Explicit --execute required')
    print(json.dumps(run(),indent=2))
