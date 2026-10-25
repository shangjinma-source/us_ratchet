"""Compare all saved arms over the same baseline drawdown/recovery windows."""
import json
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from scripts.compare_saved_risk_recovery_20261023 import ARMS
from scripts.diagnose_saved_drawdown_episodes_20261023 import episodes
ROOT=Path(__file__).resolve().parents[1]

def returns(rows,begin,end):
    return F(rows[end]['equity'])/F(rows[begin]['equity'])-1

def run():
    output=ROOT/'tmp/paired_decline_recovery_20261023_v1';output.mkdir(exist_ok=False)
    source=ROOT/'tmp/saved_risk_recovery_comparison_20261023_v1/report.json';raw=source.read_bytes();prior=json.loads(raw)
    pins={str(source.relative_to(ROOT)).replace('\\','/'):sha256(raw).hexdigest()};ledgers={}
    for key,(experiment,arm,label) in ARMS.items():
        version='v2' if experiment=='weak5_exit' else 'v1'
        name=f'tmp/fixed_monthly_{experiment}_20261023_{version}/{arm}_10bp.json'
        content=(ROOT/name).read_bytes();digest=sha256(content).hexdigest()
        if prior['source_hashes'].get(name)!=digest:raise ValueError('SAVED_SOURCE_CHANGED:'+name)
        pins[name]=digest;data=json.loads(content)
        rows=[dict(date=data['summary']['begin'],equity='20000',cash='20000')]+data['daily_ledger']
        if any(F(r.get('external_flow','0')) for r in rows):raise ValueError('EXTERNAL_FLOW_UNSUPPORTED')
        ledgers[key]={r['date']:r for r in rows}
        if len(ledgers[key])!=len(rows):raise ValueError('DUPLICATE_DATE')
    dates=list(ledgers['baseline'])
    if any(list(rows)!=dates for rows in ledgers.values()):raise ValueError('DATE_DOMAIN_CHANGED')
    windows=sorted(episodes(list(ledgers['baseline'].values())),key=lambda p:1-F(p[1]['equity'])/F(p[0]['equity']),reverse=True)[:3]
    results=[]
    for peak,trough,recovery,duration in windows:
        start,bottom=peak['date'],trough['date'];end=recovery['date'] if recovery else dates[-1]
        for key,rows in ledgers.items():
            fall=returns(rows,start,bottom);rebound=returns(rows,bottom,end);whole=returns(rows,start,end)
            assert (1+fall)*(1+rebound)==1+whole
            baseline_fall=returns(ledgers['baseline'],start,bottom)
            baseline_rebound=returns(ledgers['baseline'],bottom,end)
            results.append(dict(arm=key,name=ARMS[key][2],peak=start,trough=bottom,end=end,baseline_recovered=recovery is not None,
                decline_window_return=str(fall),decline_percent=float(fall*100),decline_advantage_pp=float((fall-baseline_fall)*100),
                rebound_window_return=str(rebound),rebound_percent=float(rebound*100),rebound_difference_pp=float((rebound-baseline_rebound)*100),
                full_window_return=str(whole),full_window_percent=float(whole*100),
                starting_cash_weight=float(F(rows[start]['cash'])/F(rows[start]['equity'])),trough_cash_weight=float(F(rows[bottom]['cash'])/F(rows[bottom]['equity']))))
    for name,digest in pins.items():
        if sha256((ROOT/name).read_bytes()).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED_AFTER_READ')
    report=dict(status='PAIRED_SAVED_WINDOWS_REVIEWED',source_hashes=pins,rows=results,selection_calls=0,economic_runs=0,production_changed=False,
        limitations=['Top three baseline episodes selected retrospectively for diagnosis, not an independent evaluation.',
                     'Same dates and cost assumptions, fixed saved monthly quantities; not PIT/OOS.',
                     'Normalized returns have differing starting wealth and exposure; not an isolated causal attribution.',
                     'Rebound ending at a baseline recovery does not imply each candidate recovered its own peak.'])
    (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps([r for r in results if r['arm'] in ('baseline','weak5','staged3')],ensure_ascii=False))
if __name__=='__main__':run()
