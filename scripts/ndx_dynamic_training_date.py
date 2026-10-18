"""Source-bound cross-k date cohort; unknown technology eligibility stays unknown."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ndx_dynamic_training_context import load_context
from scripts.ndx_dynamic_frozen_input_probe import _check_sources
from backtest.ndx_dynamic_training_semantics import training_semantics
from backtest.ndx_dynamic_historical_gates import historical_gates
from backtest.ndx_dynamic_research_selector import select_research_lane

INDEX=ROOT/'data/cache/research/dynamic_frozen_v2/training_plan_index_20260911.json'
INDEX_SHA='afaccee2fedb481747bb5b0c5ef1d483dfa852980c79dcd34a7091a8e2f970b0'


def prepare_date(*,source_batch,universe_track,selection_date):
    raw=INDEX.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=INDEX_SHA:
        raise ValueError('Training index identity differs')
    index=json.loads(raw)
    sources={str(INDEX):INDEX_SHA,**index['source_hashes']}
    coordinates=[row for row in index['coordinates'] if
                 (row['source_batch'],row['universe_track'],row['selection_date'])==
                 (source_batch,universe_track,selection_date)]
    if not coordinates:
        raise ValueError('Requested date absent from complete index')
    records=[]; signatures=set(); cutoffs=set(); contexts=[]
    for coordinate in coordinates:
        if coordinate['status']=='NO_DELTA':
            continue
        if not coordinate['context_sha256']:
            raise ValueError('Date has unavailable context; no implicit partial selection')
        restored=load_context(coordinate['context_sha256'])
        if [row['task'] for row in restored['records']] != [row['task'] for row in coordinate['tasks']]:
            raise ValueError('Context tasks differ from full index')
        contexts.append(coordinate['context_sha256'])
        for path,digest in restored['source_hashes'].items():
            if path in sources and sources[path]!=digest:
                raise ValueError('Conflicting source binding')
            sources[path]=digest
        for row in restored['records']:
            task=row['task']; cutoffs.add(task['decision_data_end'])
        semantics=training_semantics(inputs=restored['inputs'],decision_data_end=restored['summary']['training_cutoff'],
                                     source_batch=source_batch,universe_track=universe_track)
        signature=semantics['training_semantics_sha256']; signatures.add(signature)
        for row in restored['records']:
            eligibility=(historical_gates(result=row['result'],contract=restored['inputs']['contract'],
                         holding_count=row['task']['holding_count']) if row['result'] is not None else {})
            records.append(dict(**row,eligibility=eligibility,training_semantics_sha256=signature))
    if len(signatures)!=1 or len(cutoffs)!=1:
        raise ValueError('Date has no comparable nonempty training cohort')
    expected=dict(source_batch=source_batch,universe_track=universe_track,selection_date=selection_date,
        decision_data_end=next(iter(cutoffs)),training_semantics_sha256=next(iter(signatures)),
        expected_task_count=sum(row['planned'] for row in coordinates))
    result=select_research_lane(expected_dates=[expected],records=records,policy_role='RETURN')
    for relative in ('scripts/ndx_dynamic_training_date.py','backtest/ndx_dynamic_training_semantics.py',
                     'backtest/ndx_dynamic_historical_gates.py','backtest/ndx_dynamic_research_selector.py'):
        path=ROOT/relative;sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    _check_sources(sources)
    return dict(expected_date=expected,context_sha256s=contexts,records=records,
        coordinate_count=len(coordinates),no_delta_count=sum(row['status']=='NO_DELTA' for row in coordinates),
        source_hashes=sources,selection=result,technology_scope_status='UNRESOLVED_CURRENT_PURE_TECH_DEFINITION',
        all_base_candidates_included=False,promotion_allowed=False)
