"""Independent executed-prefix accounting and fixed staging-rule review."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
def main():
    from scripts import review_old_continuous_identity_prefix_v1 as prefix
    from backtest.two_stage_execution_independent_review_v1 import review
    from scripts.research.two_stage_execution_activity_v1 import activity
    p=argparse.ArgumentParser();p.add_argument('--book',required=True);p.add_argument('--inputs',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    bp=Path(a.book);ip=Path(a.inputs);book=json.loads(bp.read_bytes());document=json.loads(ip.read_bytes())
    def staged(*args,**kwargs):
        if kwargs.pop('verify_selections',None) is not True or kwargs.pop('verify_risk_provider',None) is not True:raise ValueError('FULL_PROOF_REQUIRED')
        return review(*args,**kwargs)
    with patch.object(prefix,'review',staged):result=prefix.review_executed_prefix(book,document['assembled'],document['ohlc'],document['dividend_events'])
    result['activity']=activity(book,document['assembled'])
    paths=[bp,ip,Path(__file__),ROOT/'scripts/review_old_continuous_identity_prefix_v1.py',ROOT/'backtest/two_stage_execution_independent_review_v1.py',ROOT/'backtest/historical_dividend_identity_independent_review_v1.py',ROOT/'scripts/research/two_stage_execution_activity_v1.py']
    result['source_hashes']={str(x.resolve().relative_to(ROOT)).replace('\\','/'):sha256(x.read_bytes()).hexdigest() for x in paths}
    with Path(a.output).open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps({k:result[k] for k in ('status','start','end','executed_sessions')}))
if __name__=='__main__':main()
