"""Create-only historical lane dependency preparation; no fitting or execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_cutoff_lane_dependency_research as core

SOURCE=Path(__file__).resolve()
LOADED_SOURCES={str(SOURCE):hashlib.sha256(SOURCE.read_bytes()).hexdigest(),str(core.SOURCE):core.LOADED_SHA}


def verify_sources(sources):
    for path,digest in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:
            raise ValueError('Source changed during preparation: '+path)


def run(queue_paths,queue_sha256,output):
    verify_sources(LOADED_SOURCES)
    if not queue_paths or len(queue_paths)!=len(queue_sha256):
        raise ValueError('Matching ordered queue paths and external SHAs required')
    destination=Path(output).resolve()
    if destination.exists():
        raise FileExistsError('Create-only output; choose a new research version')
    references=[dict(path=str(Path(path).resolve()),sha256=digest) for path,digest in zip(queue_paths,queue_sha256)]
    sources=dict(LOADED_SOURCES)
    report=core.prepare_lanes(references)
    for decision in report['decisions']:
        for path,digest in decision['source_hashes'].items():
            if path in sources and sources[path]!=digest:
                raise ValueError('Conflicting source SHA')
            sources[path]=digest
    verify_sources(sources)
    report['prepare_source_hashes']=sources
    raw=(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
    destination.parent.mkdir(parents=True,exist_ok=True)
    with destination.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    verify_sources(sources)
    if destination.read_bytes()!=raw:
        raise ValueError('Published preparation bytes changed')
    return dict(path=str(destination),sha256=hashlib.sha256(raw).hexdigest(),
        decisions=len(report['decisions']),dependency_nodes=len(report['dependencies']),fit_performed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--queue-path',dest='queue_paths',required=True,action='append')
    parser.add_argument('--queue-sha256',required=True,action='append')
    parser.add_argument('--output',required=True)
    print(json.dumps(run(**vars(parser.parse_args()))))
