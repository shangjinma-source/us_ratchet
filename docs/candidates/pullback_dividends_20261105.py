"""Seven specifically reviewed gross cash distributions; no signal changes."""
from pathlib import Path
from fractions import Fraction as F
from hashlib import sha256
import json
from copy import deepcopy
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
RECORDS={
 '2021_2023':[('mdlz','2021-03-30','2021-04-14','0.315'),('adp','2021-06-10','2021-07-01','0.93'),('aapl','2021-11-05','2021-11-11','0.22'),('gild','2022-12-14','2022-12-29','0.73'),('asml','2023-02-06','2023-02-15','1.471928')],
 '2024_2026':[('aep','2025-02-10','2025-03-10','0.93'),('bkr','2026-02-17','2026-02-27','0.23')]}
def need(ok,why):
 if not ok:raise ValueError(why)
def append_review(document,review,window):
 base='early_price_v2' if window=='2021_2023' else 'late_price_v4';inventory='tmp/pullback_account_20261105/'+base+'/potential_action_inventory.json';raw=(ROOT/inventory).read_bytes();captured=loads(raw);pins={inventory:sha256(raw).hexdigest()};rows=[];events=[]
 for ticker,ex,pay,amount in RECORDS[window]:
  source='tmp/pullback_action_sources_20261105/'+ticker+'_'+ex.replace('-','')+'_observation.json';raw=(ROOT/source).read_bytes();observation=json.loads(raw);pins[source]=sha256(raw).hexdigest()
  facts=observation.get('event',observation);need(facts.get('payment_date')==pay and facts.get('ex_date')==ex,'OFFICIAL_DATES')
  observedamount=facts.get('nominal_amount',facts.get('gross_per_us_share',facts.get('amount_per_share')))
  need(observedamount is not None and F(observedamount)==F(amount),'OFFICIAL_AMOUNT')
  for path,digest in observation.get('source_paths',{}).items():need(sha256((ROOT/path).read_bytes()).hexdigest()==digest,'UPSTREAM_CHANGED');pins[path]=digest
  if observation.get('pdf_path'):need(sha256((ROOT/observation['pdf_path']).read_bytes()).hexdigest()==observation['pdf_sha256'],'PDF_CHANGED');pins[observation['pdf_path']]=observation['pdf_sha256']
  found=[e for r in captured['rows'] for e in r['gate']['unmapped_events'] if e.get('ticker','').lower()==ticker and e['date']==ex and e['kind']=='dividends'];need(found,'PROVIDER_OBSERVATION_REQUIRED');sids={e['security_id'] for e in found};need(len(sids)==1,'EXACT_SECURITY');sid=sids.pop()
  for e in found:
   path=e['source'];digest=sha256((ROOT/path).read_bytes()).hexdigest();need(document['source_hashes'][path]==digest,'EXECUTION_SOURCE_PIN');pins[path]=digest
  need(not any(e['security_id']==sid and e['ex_date']==ex for e in document['dividend_events']),'DUPLICATE_DIVIDEND')
  refs=[source]+sorted({e['source'] for e in found});observed=found if window=='2021_2023' else [{k:v for k,v in e.items() if k!='security_id'} for e in found]
  row=dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=str(F(amount)),currency='USD',source_references=refs,observed_provider_events=observed,limitation='GROSS_RETROSPECTIVE; issuer payment session close, not actual broker net credit. ASML final announced after ex; not a predictive feature.')
  event=dict(event_id='pullback-gross:'+sid+':'+ex,security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=str(F(amount)),withholding_rate='0',currency='USD',assumption=row['limitation'])
  rows.append(row);events.append(event)
 review['rows'].extend(deepcopy(rows));review['source_hashes'].update(pins);document['dividend_events'].extend(deepcopy(events));return dict(review_rows=rows,dividend_events=events,source_hashes=pins)
