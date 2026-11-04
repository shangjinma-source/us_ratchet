"""Independently audit saved synthetic-entry books; no replay or model calls."""
import json
from pathlib import Path
from fractions import Fraction as F
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT = Path(__file__).resolve().parents[2]

def run():
    root=ROOT/'tmp/news_synthetic_entry_20261104_v2'
    inputs=json.loads((ROOT/'tmp/recent_continuous_baseline_20261026_v7/execution_inputs.json').read_bytes())
    report=[]
    for name in ('DLTR_20220825_v2','PDD_20230320','PDD_20230526'):
        folder=root/name
        conv=json.loads((folder/'initial_conversion.json').read_bytes())
        spec=conv['synthetic'];old=conv['historical'];sid=spec['security_id'];day=spec['days'][1]
        assert spec['risk_state']==old['risk_state'] and spec['monthly_ceiling']==old['monthly_ceiling']
        assert F(spec['initial']['equity'])==F(old['initial']['equity'])
        assert F(spec['initial']['cash'])+F(spec['initial']['stock_value'])==F(spec['initial']['equity'])
        assert spec['initial']['shares'][sid]==0
        assert F(spec['initial']['cash'])-F(old['initial']['cash'])==F(conv['cash_added'])
        assert F(conv['cash_added'])==conv['converted_quantity']*F(conv['previous_close'])
        opening=datetime.fromisoformat(day+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York'))
        pub=datetime.fromisoformat(spec['publication']);close=F(conv['previous_close']);op=F(str(inputs['ohlc'][sid][day]['open']))
        paths=[folder/(cost+'bp_'+arm+'.json') for cost in ('0','5') for arm in ('BASELINE','MODEL_ACTION','PAUSE_ONLY')]
        for path in paths:
            saved=json.loads(path.read_bytes());book=saved['book'];cash=F(spec['initial']['cash']);shares=spec['initial']['shares'].copy()
            assert saved['trace'][-1]['news_active'] is False
            assert [r['date'] for r in book['daily_ledger']]==spec['days'][1:]
            for row in book['daily_ledger']:
                for fill in book['order_log']:
                    if fill['event']=='ASSUMED_NEXT_OPEN_FILLED' and fill['date']==row['date']:
                        assert fill['side'] in ('BUY','SELL')
                        sign=1 if fill['side']=='BUY' else -1;q=fill['quantity']
                        assert type(q) is int and q>0
                        cash-=sign*q*F(fill['price'])+F(fill['fee'])
                        shares[fill['security_id']]=shares.get(fill['security_id'],0)+sign*q
                        assert cash==F(fill['cash_after']) and cash>=0
                assert cash==F(row['cash']) and shares==row['shares']
                value=sum(q*F(inputs['assembled']['close_prices'][s][row['date']]) for s,q in shares.items() if q)
                assert cash+value==F(row['equity'])
        report.append(dict(case=spec['case_id'],start=spec['days'][0]+' close',end=spec['days'][-1]+' close',published=spec['publication'],first_open=opening.isoformat(),publication_to_open_minutes=(opening-pub).total_seconds()/60,unheld_common_gap_pct=float((op/close-1)*100),independent_ledger_pass=True,books_checked=len(paths)))
    (root/'independent_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':run()
