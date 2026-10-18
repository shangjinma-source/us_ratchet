"""All captured date-cohorts historical artifact lineage, without qualification."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ndx_dynamic_training_context import load_context
from scripts.ndx_dynamic_training_date import INDEX, INDEX_SHA
from backtest.ndx_dynamic_training_semantics import training_semantics
from backtest.ndx_historical_eligibility_lineage import verify_historical_eligibility

READINESS=ROOT/'data/cache/research/dynamic_frozen_v2/all_date_readiness_20260911.json'
READINESS_SHA='ac58c1ef900ebc8413931e521efa48e8f73db2f6fce2b55b5d22130d2ab5d506'
_SOURCE=Path(__file__).resolve()
_LOADED={str(ROOT/path):hashlib.sha256((ROOT/path).read_bytes()).hexdigest() for path in (
    'scripts/ndx_historical_lineage_all_dates.py','scripts/ndx_dynamic_training_context.py',
    'backtest/ndx_dynamic_training_semantics.py','backtest/ndx_historical_eligibility_lineage.py')}


def _read(path,expected,sources):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('Frozen report SHA mismatch')
    sources[str(Path(path).resolve())]=expected
    return json.loads(raw)


def _merge(sources,other):
    for path,digest in other.items():
        if path in sources and sources[path]!=digest: raise ValueError('Conflicting source binding')
        sources[path]=digest


def _verify_universe(universe,coordinate,sources,verifier=verify_historical_eligibility):
    records=universe.to_dict('records')
    identities=[row['security_id'] for row in records]; tickers=[row['ticker'] for row in records]
    if len(set(identities))!=len(identities) or len(set(tickers))!=len(tickers):
        raise ValueError('Universe security/ticker identities duplicated')
    output=[]
    for row in records:
        try:
            result=verifier(selection_date=coordinate['selection_date'],universe_track=coordinate['universe_track'],
                securities={row['security_id']:{'ticker':row['ticker'],'issuer_id':row['issuer_id']}})
            _merge(sources,result['source_hashes'])
            output.extend(result['securities'])
        except (ValueError,KeyError,OSError) as error:
            output.append(dict(security_id=row['security_id'],ticker=row['ticker'],issuer_id=row['issuer_id'],
                status='INPUT_INVALID',historical_artifact_verified=False,
                current_technology_qualification='UNKNOWN',error_type=type(error).__name__,error=str(error)))
    return output


def run():
    sources=dict(_LOADED)
    index=_read(INDEX,INDEX_SHA,sources); readiness=_read(READINESS,READINESS_SHA,sources)
    _merge(sources,index['source_hashes']); _merge(sources,readiness['source_hashes'])
    key=lambda row:(row['source_batch'],row['universe_track'],row['selection_date'])
    grouped={}
    for row in index['coordinates']:grouped.setdefault(key(row),[]).append(row)
    ready={key(row):row for row in readiness['dates']}
    if len(ready)!=len(readiness['dates']) or set(grouped)!=set(ready):
        raise ValueError('Frozen all-date denominator mismatch')
    output=[]
    for group,coordinates in sorted(grouped.items()):
        base=dict(source_batch=group[0],universe_track=group[1],selection_date=group[2],
                  coordinate_count=len(coordinates))
        try:
            candidates=[row for row in coordinates if row['status']!='NO_DELTA']
            if not candidates or not all(row['context_sha256'] for row in candidates):
                raise ValueError('Missing context in date cohort')
            if ready[group]['context_count']!=len(candidates):raise ValueError('Readiness context denominator differs')
            chosen=candidates[0]; context=load_context(chosen['context_sha256'])
            _merge(sources,context['source_hashes'])
            if [row['task'] for row in context['records']] != [row['task'] for row in chosen['tasks']]:
                raise ValueError('Chosen context task identities differ from frozen plan')
            for row in context['records']:
                if key(row['task'])!=group:raise ValueError('Chosen context date/source identity differs')
            semantics=training_semantics(inputs=context['inputs'],decision_data_end=context['summary']['training_cutoff'],
                source_batch=group[0],universe_track=group[1])
            if semantics['training_semantics_sha256']!=ready[group]['training_semantics_sha256']:
                raise ValueError('Chosen universe differs from verified all-context semantics')
            securities=_verify_universe(context['inputs']['universe'],base,sources)
            invalid=sum(row['status']=='INPUT_INVALID' for row in securities)
            output.append(dict(**base,status='INPUT_INVALID' if invalid else 'HISTORICAL_LINEAGE_OBSERVED',
                context_sha256=chosen['context_sha256'],training_semantics_sha256=semantics['training_semantics_sha256'],
                securities=securities,security_count=len(securities),input_invalid_count=invalid,
                historical_artifact_verified_count=sum(row['historical_artifact_verified'] for row in securities)))
        except (ValueError,KeyError,OSError) as error:
            output.append(dict(**base,status='INPUT_INVALID',securities=[],error_type=type(error).__name__,error=str(error)))
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise ValueError('Lineage source changed during observation')
    return dict(schema='ndx_historical_lineage_all_dates_v1',dates=output,source_hashes=sources,
        summary=dict(date_count=len(output),status_counts=dict(Counter(row['status'] for row in output)),
            securities_total=sum(row.get('security_count',0) for row in output),
            historical_artifact_verified_total=sum(row.get('historical_artifact_verified_count',0) for row in output)),
        current_technology_qualification='UNKNOWN',historical_rule_reconstruction_verified=False,
        all_base_candidates_included=False,economic_recomputation_performed=False,promotion_allowed=False)


def save_new(report,path):
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)
    if path.read_bytes()!=raw:raise ValueError('Saved lineage differs')
    return hashlib.sha256(raw).hexdigest()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--output-path',required=True);args=parser.parse_args()
    if Path(args.output_path).exists():raise ValueError('Output exists; do not rerun')
    report=run();digest=save_new(report,args.output_path)
    print(json.dumps(dict(summary=report['summary'],sha256=digest,path=args.output_path),indent=2))
