"""Observe every indexed training date without silently discarding failures."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ndx_dynamic_training_date import INDEX,INDEX_SHA,prepare_date
from scripts.ndx_dynamic_frozen_replay_probe import save_new


def inspect_dates():
    raw=INDEX.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=INDEX_SHA:
        raise ValueError('Index identity differs')
    index=json.loads(raw)
    dates=sorted({(row['source_batch'],row['universe_track'],row['selection_date']) for row in index['coordinates']})
    rows=[];sources={str(INDEX):INDEX_SHA}
    for batch,track,day in dates:
        row=dict(source_batch=batch,universe_track=track,selection_date=day)
        try:
            prepared=prepare_date(source_batch=batch,universe_track=track,selection_date=day)
            row.update(status='COHORT_RESTORED_CURRENT_SCOPE_UNRESOLVED',
                planned=prepared['expected_date']['expected_task_count'],
                restored=len(prepared['records']),context_count=len(prepared['context_sha256s']),
                historical_risk_liquidity_passed=sum(record['eligibility'].get('fractional_risk_passed') is True
                    and record['eligibility'].get('liquidity_passed') is True for record in prepared['records']),
                target_cardinalities=sorted({record['task']['holding_count'] for record in prepared['records']}),
                selection_status=prepared['selection']['rows'][0]['status'],
                training_semantics_sha256=prepared['expected_date']['training_semantics_sha256'])
            for path,digest in prepared['source_hashes'].items():
                if path in sources and sources[path]!=digest:
                    raise ValueError('Cross-date source identity conflict')
                sources[path]=digest
        except (ValueError,KeyError,FileNotFoundError) as error:
            row.update(status='INPUT_INVALID',error=str(error))
        rows.append(row)
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise ValueError('Readiness source changed')
    own=Path(__file__).resolve();sources[str(own)]=hashlib.sha256(own.read_bytes()).hexdigest()
    return dict(schema='ndx_dynamic_date_readiness_v1',dates=rows,
        summary=dict(expected_date_count=len(dates),observed_date_count=len(rows),
                     statuses=dict(Counter(row['status'] for row in rows)),
                     restored_tasks=sum(row.get('restored',0) for row in rows)),
        source_hashes=sources,all_base_candidates_included=False,
        scope_definition_approved=False,execution_prices_ready_for_all_dates=False,promotion_allowed=False)


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-path',required=True)
    args=parser.parse_args()
    if Path(args.output_path).exists(): raise ValueError('Output already exists')
    report=inspect_dates()
    print(save_new(report,args.output_path))
    print(report['summary'])
