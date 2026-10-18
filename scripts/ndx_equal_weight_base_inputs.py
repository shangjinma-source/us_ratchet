"""Bind explicit saved equal-weight definitions to one revised training cohort."""
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ndx_dynamic_base_candidate_inventory import inventory_date
from scripts.ndx_dynamic_training_context import load_context
from scripts.ndx_dynamic_training_date import INDEX,INDEX_SHA
from backtest.ndx_dynamic_training_semantics import training_semantics

READINESS=ROOT/'data/cache/research/dynamic_frozen_v2/all_date_readiness_20260911.json'
READINESS_SHA='ac58c1ef900ebc8413931e521efa48e8f73db2f6fce2b55b5d22130d2ab5d506'
_FILES=('scripts/ndx_equal_weight_base_inputs.py','scripts/ndx_dynamic_base_candidate_inventory.py',
        'scripts/ndx_dynamic_training_context.py','backtest/ndx_dynamic_training_semantics.py')
_LOADED={str(ROOT/name):hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in _FILES}


def prepare_equal_base_date(*,source_batch,universe_track,selection_date):
    inventory=inventory_date(source_batch=source_batch,universe_track=universe_track,selection_date=selection_date)
    raw=INDEX.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=INDEX_SHA: raise ValueError('Index differs')
    indexed=json.loads(raw)
    same=lambda row:(row['source_batch'],row['universe_track'],row['selection_date'])==(source_batch,universe_track,selection_date)
    coordinates=[row for row in indexed['coordinates'] if same(row)]
    available=[row for row in coordinates if row['context_sha256']]
    if not available: raise ValueError('No revised training context for base definitions')
    context=load_context(available[0]['context_sha256'])
    if [row['task'] for row in context['records']] != [row['task'] for row in available[0]['tasks']]:
        raise ValueError('Index/context task mismatch')
    raw=READINESS.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=READINESS_SHA: raise ValueError('Readiness identity differs')
    readiness=json.loads(raw)
    matched=[row for row in readiness['dates'] if same(row)]
    semantics=training_semantics(inputs=context['inputs'],decision_data_end=context['summary']['training_cutoff'],
                                 source_batch=source_batch,universe_track=universe_track)
    if len(matched)!=1 or matched[0]['training_semantics_sha256']!=semantics['training_semantics_sha256']:
        raise ValueError('Base evaluation cohort differs from revised training cohort')
    combinations=[]
    for path,digest in inventory['source_hashes'].items():
        if Path(path).name!='training_candidates.csv': continue
        raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest: raise ValueError('Base definitions changed')
        for row in csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))):
            if row['weight_spec']=='equal_weight': combinations.append(tuple(row['tickers'].split(';')))
    if not combinations or len(set(combinations))!=len(combinations):
        raise ValueError('Missing/duplicate equal-weight definitions')
    sources=dict(_LOADED)
    for mapping in (inventory['source_hashes'],context['source_hashes'],readiness['source_hashes'],{str(READINESS):READINESS_SHA}):
        for path,digest in mapping.items():
            if path in sources and sources[path]!=digest: raise ValueError('Source conflict')
            sources[path]=digest
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest: raise ValueError('Loaded/input source drift')
    return dict(inputs=context['inputs'],combinations=sorted(combinations),source_hashes=sources,
        training_semantics=semantics,summary=dict(equal_weight_base_count=len(combinations),
            all_base_count=inventory['base_count'],delta_count=inventory['delta_count'],
            cardinalities=sorted({len(combo) for combo in combinations}),
            saved_economic_metrics_used=False,new_evaluation_performed=False,promotion_allowed=False))
