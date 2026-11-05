"""Bound signal-only possible exposure until first exit or unresolved action; no account returns."""
from pathlib import Path
from fractions import Fraction as F
from backtest.research_exact_fraction_json import loads,dumps
ROOT=Path(__file__).resolve().parents[2]
def run(output="tmp/pullback_account_20261105/early_price_v2"):
 out=ROOT/output
 inp=loads((out/'execution_inputs.json').read_text());signals=loads((out/'signals.json').read_text());broad=loads((out/'potential_action_inventory.json').read_text());doc=inp['document'];days=doc['assembled']['session_dates'];bars=doc['ohlc'];by={r['security_id']:r['gate'] for r in broad['rows']};hits=[];paths=[]
 for day,sig in signals.items():
  for e in sig['entries']:
   sid=e['security_id'];start=days.index(day)+1;stop=F(e['stop']);opening=F(bars[sid][days[start]]['open'])
   if not 0<opening-stop<=opening*F(3,100):continue
   events=by[sid]['unmapped_events'];end=None;reason=None
   for i in range(start,len(days)):
    d=days[i];prev=days[i-1];event=[x for x in events if x['date']==d]
    if event:
     hits.extend(event);end=d;reason='UNRESOLVED_ACTION_POSSIBLY_EXPOSED';break
    if sid not in bars or d not in bars[sid]:end=d;reason='MISSING_OR_TERMINAL_QUOTE';break
    if i>start and sid in signals[prev]['ema9']:stop=max(stop,F(signals[prev]['ema9'][sid]))
    if sid not in signals[prev].get('effective_eligible',signals[prev]['eligible']) or F(bars[sid][d]['low'])<=stop:end=d;reason='FIXED_EXIT';break
   paths.append({'signal':day,'security_id':sid,'entry_date':days[start],'end':end or days[-1],'end_reason':reason or 'WINDOW_END','missing_streams':by[sid]['missing_action_streams']})
 unique={ (e['security_id'],e['date'],e['kind']):e for e in hits}
 result={'scope':'INDEPENDENT_SIGNAL_POTENTIAL_HOLDING_NOT_ACCOUNT_OR_PROFIT_TEST_FIRST_UNRESOLVED_ACTION_STOPS_PATH','paths':paths,'possible_unmapped_events':list(unique.values())}
 (out/'narrow_potential_actions.json').write_text(dumps(result));print([(k[0],k[1],k[2]) for k in unique]);print('valid signals',len(paths),'events',len(unique))
if __name__=='__main__':
 import sys
 run(*sys.argv[1:])
