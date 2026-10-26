"""Explicit bounded news refresh; never scheduled and never writes trading state."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from data.news_desk import collect,analyze,save_snapshot

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,default=ROOT/'data/cache/news')
    parser.add_argument('--analyze',action='store_true')
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--analysis-limit',type=int,default=4)
    parser.add_argument('--analysis-timeout',type=int,default=120)
    options=parser.parse_args()
    snapshot=collect(options.cache,limit=options.limit)
    if options.analyze:snapshot=analyze(snapshot,options.cache,limit=options.analysis_limit,timeout=options.analysis_timeout)
    path=save_snapshot(snapshot,options.cache)
    print(json.dumps(dict(path=str(path),events=len(snapshot['events']),fetch_errors=snapshot['fetch_errors'],analysis=snapshot['analysis_summary']),ensure_ascii=False))

if __name__=='__main__':main()
