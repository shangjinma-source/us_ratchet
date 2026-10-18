"""Inventory bound base candidates, without mixing old and v3 economic scores."""
from collections import Counter
import csv
import hashlib
import io
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ndx_dynamic_training_date import INDEX,INDEX_SHA

_SOURCE=Path(__file__).resolve()
_LOADED=hashlib.sha256(_SOURCE.read_bytes()).hexdigest()


def inventory_date(*,source_batch,universe_track,selection_date):
    sources={str(_SOURCE):_LOADED}
    def read(path,digest):
        path=Path(path); raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('Base candidate source mismatch')
        sources[str(path)]=digest
        return raw
    index=json.loads(read(INDEX,INDEX_SHA))
    coordinates=[row for row in index['coordinates'] if
        (row['source_batch'],row['universe_track'],row['selection_date'])==
        (source_batch,universe_track,selection_date)]
    if not coordinates: raise ValueError('Date absent from bound index')
    rows=[]
    for coordinate in coordinates:
        manifest=json.loads(read(coordinate['child_path'],coordinate['child_manifest_sha256']))
        descriptor=manifest['artifacts']['candidates']
        raw=read(descriptor['path'],descriptor['sha256'])
        parsed=list(csv.reader(io.StringIO(raw.decode('utf-8-sig'))))
        header=parsed[0]
        if len(header)!=len(set(header)) or any(len(row)!=len(header) for row in parsed[1:]):
            raise ValueError('Invalid base candidate CSV')
        candidates=[dict(zip(header,row)) for row in parsed[1:]]
        if len(candidates)!=descriptor['rows']: raise ValueError('Base denominator differs')
        seen=set(); preference=[]
        for row in candidates:
            if (row['selection_date']!=selection_date or row['universe_track']!=universe_track
                    or int(row['holding_count'])!=coordinate['holding_count']):
                raise ValueError('Base coordinate differs')
            key=(row['tickers'],row['weight_spec'])
            if key in seen: raise ValueError('Duplicate base candidate identity')
            seen.add(key)
            if key==('AMAT;AVGO;CDNS;GOOG','equal_weight'):
                preference.append(dict(portfolio_id=row['portfolio_id'],tickers=row['tickers'],
                    declared_constraints_passed=row['declared_constraints_passed']))
        overlap=sum((task['task']['tickers'],task['task']['weight_spec']) in seen for task in coordinate['tasks'])
        if overlap: raise ValueError('Delta task duplicates saved base candidate')
        rows.append(dict(holding_count=coordinate['holding_count'],base_count=len(candidates),
            base_weight_spec_counts=dict(Counter(row['weight_spec'] for row in candidates)),
            delta_count=coordinate['planned'],delta_status=coordinate['status'],
            preference_reference=preference,search_exhaustive_values=sorted({r['search_exhaustive'] for r in candidates}),
            child_manifest_sha256=coordinate['child_manifest_sha256']))
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest: raise ValueError('Base source drift')
    return dict(source_batch=source_batch,universe_track=universe_track,selection_date=selection_date,
        rows=rows,base_count=sum(row['base_count'] for row in rows),
        delta_count=sum(row['delta_count'] for row in rows),source_hashes=sources,
        old_and_v3_economic_scores_merged=False,full_current_pool_coverage_verified=False,promotion_allowed=False)
