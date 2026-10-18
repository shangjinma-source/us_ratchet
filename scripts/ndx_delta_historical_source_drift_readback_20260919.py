"""Inventory exact historical source drift without waiving any verifier."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'data/cache/research'


def digest(path):
    path=Path(path)
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main():
    refs={str(BASE/'delta_paired_snapshot_20260912_v1/tasks/index_a1a78475e53cb9b2339f839f72f3310ce4c4c1c871406ef384f183d0c599e1b4.json'):
          '6c27c7be1a31d94bbf6052d5c24f58b185abfff04ab0275fc485214dcd66da8c',
          str(BASE/'delta_selected_input_20260912_v1/first_probe.json'):
          '241ac517d78668761f32a25da68856cf396d28a1ef5591d9da993a0e2307607a'}
    docs={}
    for path,expected in refs.items():
        assert digest(path)==expected;docs[path]=json.loads(Path(path).read_bytes())
    index,probe=docs.values()
    maps={'paired_finalization':index['finalization']['source_hashes'],
          'paired_additional_provenance':index['finalization']['additional_provenance_hashes'],
          'paired_completed_checkpoints':{row['path']:row['sha256'] for row in index['completed']},
          'selected_first_probe':probe['result']['source_hashes']}
    expected_sources={}
    for values in maps.values():
        for path,expected in values.items():
            assert path not in expected_sources or expected_sources[path]==expected,path
            expected_sources[path]=expected
    print(json.dumps(dict(stage='hashing_complete_union',paths=len(expected_sources))),flush=True)
    paths=list(expected_sources)
    with ThreadPoolExecutor(max_workers=12) as pool:observed=dict(zip(paths,pool.map(digest,paths)))
    def category(path):
        p=Path(path)
        if p.parent==ROOT/'data/cache' and p.suffix=='.csv':return 'MUTABLE_ROOT_PRICE_CSV'
        if p.suffix=='.py':return 'NUMERICAL_OR_RESEARCH_SOURCE_CODE'
        if p.name=='context.json':return 'IMMUTABLE_TYPED_CONTEXT'
        if p.name.endswith('.csv.manifest.json'):return 'CSV_MANIFEST'
        return 'IMMUTABLE_CHECKPOINT_OR_RESEARCH_ARTIFACT'
    changes=[dict(path=path,expected_historical_sha256=expected_sources[path],observed_current_sha256=observed[path],
                  category=category(path),referenced_by=[name for name,m in maps.items() if path in m])
             for path in paths if observed[path]!=expected_sources[path]]
    directories=[BASE/'ndx_cardinality_execution_prices_20240603_v1/raw',
                 BASE/'ndx_cardinality_execution_prices_walkforward_v1/raw',
                 BASE/'ndx_cardinality_execution_prices_all_ready_v1/raw']
    archive_checks=[]
    for change in changes:
        if change['category']!='MUTABLE_ROOT_PRICE_CSV':continue
        for directory in directories:
            path=directory/Path(change['path']).name
            if path.is_file():
                sha=digest(path);archive_checks.append(dict(original_path=change['path'],archive_path=str(path),archive_sha256=sha,
                    matches_original_expected_bytes=sha==change['expected_historical_sha256']))
    for change in changes:assert digest(change['path'])==change['observed_current_sha256'],'Source changed again during diagnosis'
    for path,expected in refs.items():assert digest(path)==expected
    summary={name:dict(paths=len(values),matched=sum(observed[p]==h for p,h in values.items()),
                      changed=sum(observed[p]!=h for p,h in values.items())) for name,values in maps.items()}
    report=dict(schema='ndx_delta_historical_source_drift_diagnosis_20260919_v1',observed_at_utc=datetime.now(timezone.utc).isoformat(),
        source_hashes=refs|{str(Path(__file__).resolve()):digest(__file__)},original_expected_sources=expected_sources,
        counts_by_artifact=summary,unique_paths_checked=len(paths),changed_count=len(changes),changes=changes,
        archived_csv_checks=archive_checks,archive_search_scope=[str(p) for p in directories],
        archive_search_is_exhaustive=False,no_training_checkpoint_content_search_performed=True,
        source_closure_passed=not changes,historical_source_closure_verified=False,
        existing_complete_index_declared_tasks=len(index['completed']),complete_task_numerics_verified=False,
        cache_or_frozen_sources_modified=False,no_fitter_or_evaluator_called=True,point_in_time_verified=False,promotion_allowed=False)
    folder=BASE/'delta_source_drift_20260919_v1';folder.mkdir(parents=True,exist_ok=True)
    output=folder/'historical_source_drift.json'
    with output.open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    print(json.dumps(dict(path=str(output),sha256=digest(output),counts=summary,changed=len(changes),
                         archive_matches=sum(row['matches_original_expected_bytes'] for row in archive_checks))),flush=True)


if __name__=='__main__':main()
