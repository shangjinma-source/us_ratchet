"""Loaded-code binding and explicit no-delta state for date-cohort restoration."""
import hashlib
import json
from pathlib import Path

from scripts import ndx_dynamic_training_date as original

_LOADED={str(original.ROOT/name):hashlib.sha256((original.ROOT/name).read_bytes()).hexdigest()
         for name in ('scripts/ndx_dynamic_training_date_v2.py','scripts/ndx_dynamic_training_date.py',
                      'backtest/ndx_dynamic_training_semantics.py','backtest/ndx_dynamic_historical_gates.py',
                      'backtest/ndx_dynamic_research_selector.py')}


def prepare_date_v2(*,source_batch,universe_track,selection_date):
    original._check_sources(_LOADED)
    raw=original.INDEX.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=original.INDEX_SHA:
        raise ValueError('Training index identity differs')
    index=json.loads(raw)
    matching=[row for row in index['coordinates'] if
        (row['source_batch'],row['universe_track'],row['selection_date'])==
        (source_batch,universe_track,selection_date)]
    if matching and all(row['status']=='NO_DELTA' and row['planned']==0 and not row['tasks'] for row in matching):
        sources={**index['source_hashes'],str(original.INDEX):original.INDEX_SHA,**_LOADED}
        original._check_sources(sources)
        return dict(schema='ndx_dynamic_training_date_v2',
            expected_date=dict(source_batch=source_batch,universe_track=universe_track,
                               selection_date=selection_date,expected_task_count=0),
            records=[],context_sha256s=[],coordinate_count=len(matching),no_delta_count=len(matching),
            status='DELTA_ONLY_NO_TASKS',source_hashes=sources,
            selection=dict(rows=[dict(status='NO_DELTA',selected=None)],promotion_allowed=False),
            all_base_candidates_included=False,promotion_allowed=False)
    result=original.prepare_date(source_batch=source_batch,universe_track=universe_track,selection_date=selection_date)
    original._check_sources(_LOADED)
    result['source_hashes'].update(_LOADED)
    result['schema']='ndx_dynamic_training_date_v2'
    return result
