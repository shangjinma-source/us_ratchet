"""Potential one-share exposure only; not actual account admission."""
import json
from pathlib import Path
from copy import deepcopy
from scripts.research import run_momentum_account_20261105 as r
from scripts.research import inventory_momentum_actions_20261105 as inv
ROOT=Path(__file__).resolve().parents[2]
freeze=json.loads((ROOT/'research_contracts/momentum_account_execution_20261105/freeze.json').read_bytes())
rosters=json.loads((ROOT/'tmp/residual_momentum_feasibility_20261106.json').read_bytes())['rows'];results=[]
for window in ['2021_2023','2024_2026']:
 document,prices,review,legacy,proof=inv.inputs(window,r.read(freeze['inventory_base_freeze']))
 document,review=r.prepare_actions(window=window,document=document,prices=prices,review=review,pins={},freeze=freeze)
 rows=[x for x in rosters if x['window']==window];dates=document['assembled']['session_dates'];prior=[]
 for i,row in enumerate(rows):
  day=row['date'];until=rows[i+1]['date'] if i+1<len(rows) else dates[-1];selected=[s['security_id'] for s in row['selected']] if row['risk_on'] else []
  try:gate=r.action_gate(window=window,arguments={'decision_date':day,'account_state':{'shares':{s:1 for s in prior}}},selected={'target_quantities':{s:1 for s in selected}},until=until,active=dates[dates.index(day)+1],document=document,prices=prices,review=review,legacy=legacy,proof=proof)
  except ValueError as error:gate={'admitted':False,'exception':str(error)}
  results.append({'window':window,'day':day,'gate':gate});prior=selected
out=ROOT/'tmp/residual_momentum_action_coverage_20261106.json';out.write_text(json.dumps(results,indent=2),encoding='utf-8')
print('rows',len(results),'blocked',sum(not x['gate']['admitted'] for x in results),flush=True)
