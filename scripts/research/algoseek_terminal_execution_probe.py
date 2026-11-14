"""Fixed event comparison including non-fills; no portfolio performance claim."""
import argparse
import json
from pathlib import Path
from scripts.research.probe_aapl_historical_execution_events import inspect
from scripts.research.aapl_execution_terminal_comparison import terminal_value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    validation = json.loads((args.directory/'event_validation.json').read_text())
    rows = []
    for result in validation['results']:
        if not result['status'].startswith('VALID'):
            continue
        event = result['event']
        path = args.directory/'normalized'/(event['date'].replace('-','')+'_'+result['symbol']+'.json')
        raw = path.read_bytes()
        checked = inspect(raw, event, allow_no_trade=True)
        close = json.loads(raw)['c'][-1]
        quantity = float(event['quantity'])
        for fee in (0,18):
            baseline = terminal_value(event['side'],quantity,close,checked['arms'][0]['fill'],fee)
            for arm in checked['arms']:
                value = terminal_value(event['side'],quantity,close,arm['fill'],fee)
                rows.append(dict(date=event['date'],symbol=result['symbol'],side=event['side'],rule=arm['name'],
                    fee=fee,filled=arm['fill'] is not None,advantage_bps=(value-baseline)/(quantity*checked['reference'])*10000))
    summaries = []
    for period in ('ALL','H1','H2'):
        for side in ('BUY','SELL'):
            for rule in sorted({row['rule'] for row in rows if row['side']==side}):
                subset = [r for r in rows if r['side']==side and r['rule']==rule and r['fee']==18
                    and (period=='ALL' or (r['date'][5:7]<='06')==(period=='H1'))]
                summaries.append(dict(period=period,side=side,rule=rule,events=len(subset),fills=sum(r['filled'] for r in subset),
                    mean_bps=sum(r['advantage_bps'] for r in subset)/len(subset),
                    better=sum(r['advantage_bps']>1e-6 for r in subset),worse=sum(r['advantage_bps']< -1e-6 for r in subset)))
    output = dict(scope='Independent 2021 events, same-day close valuation; not portfolio return.',
        limitations=['No cross-event holdings/cash or opportunity path.', 'Strict-cross fill proxy; no queue or partial fills.',
                    '18 USD flat fee sensitivity, not monthly Trade25 model.', 'Missing CPRT events excluded for every arm.'],
        rows=rows,summary=summaries)
    (args.directory/'terminal_execution.json').write_text(json.dumps(output,indent=2),encoding='utf-8')
    print(json.dumps([s for s in summaries if s['rule'] in ('1030','1200')],indent=2))


if __name__=='__main__':
    main()
