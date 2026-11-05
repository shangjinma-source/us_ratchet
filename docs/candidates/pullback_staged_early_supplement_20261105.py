"""Five bounded staged-holding dividend pairs, exact issuer gross amounts."""
from pathlib import Path
import json
from fractions import Fraction as F
from hashlib import sha256
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
ROWS=[('FAST','2021-07-26','2021-08-24','0.28','fast_cost_nominal'),('XEL','2022-12-28','2023-01-20','0.4875','xel_20221228'),('ROST','2023-09-01','2023-09-29','0.335','rost_20230901'),('COST','2023-12-27','2024-01-12','15','fast_cost_nominal')]
def need(ok,why):
 if not ok:raise ValueError(why)
def append_review(document,review):
 path='tmp/pullback_account_20261105/early_price_v2/potential_action_inventory.json';raw=(ROOT/path).read_bytes();inventory=loads(raw);pins={path:sha256(raw).hexdigest()};events=[];rows=[]
 for ticker,ex,pay,amount,stem in ROWS:
  path='tmp/pullback_action_sources_20261105/'+stem+('_observations.json' if stem=='fast_cost_nominal' else '_observation.json');raw=(ROOT/path).read_bytes();ob=json.loads(raw);pins[path]=sha256(raw).hexdigest();facts=next((e for e in ob.get('events',[]) if e['ticker']==ticker),ob.get('event',ob));need(facts['ex_date']==ex and facts['payment_date']==pay and F(facts.get('nominal_amount',facts.get('gross_amount','-1')))==F(amount),'OFFICIAL_EVENT_MISMATCH')
  for source,digest in ob.get('local_evidence_hashes',{}).items():need(sha256((ROOT/source).read_bytes()).hexdigest()==digest,'OFFICIAL_LOCAL_PIN');pins[source]=digest
  found=[e for r in inventory['rows'] for e in r['gate']['unmapped_events'] if e.get('ticker')==ticker and e['date']==ex and e['kind']=='dividends'];need(found and len({e['security_id'] for e in found})==1,'EXACT_PROVIDER_EVENT');sid=found[0]['security_id'];need(not any(e['security_id']==sid and e['ex_date']==ex for e in document['dividend_events']),'DUPLICATE_EVENT')
  for e in found:
   source=e['source'];digest=sha256((ROOT/source).read_bytes()).hexdigest();need(document['source_hashes'][source]==digest,'SOURCE_PIN');pins[source]=digest
  row=dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=str(F(amount)),currency='USD',source_references=[path]+sorted({e['source'] for e in found}),observed_provider_events=found,limitation='GROSS_RETROSPECTIVE; issuer payment close not actual broker net; FAST nominal.28 versus provider.14; XEL nominal.4875 versus rounded.488; COST special15 payable after window stays receivable')
  event=dict(event_id='pullback-staged-gross:'+sid+':'+ex,security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=str(F(amount)),currency='USD',withholding_rate='0',assumption=row['limitation']);rows.append(row);events.append(event)
 document['dividend_events'].extend(events);review['rows'].extend(rows)
 approval_path='tmp/pullback_action_sources_20261105/atvi_staged_root_review.json';raw=(ROOT/approval_path).read_bytes();approval=json.loads(raw);pins[approval_path]=sha256(raw).hexdigest();path=approval['evidence_path'];raw=(ROOT/path).read_bytes();need(sha256(raw).hexdigest()==approval['evidence_sha256'],'ATVI_LONG_EVIDENCE_PIN');ob=json.loads(raw);pins[path]=approval['evidence_sha256']
 need(approval['from_exclusive']=='2022-07-29' and approval['through_inclusive']=='2022-08-25' and approval['security_id']=='research:security:atvi','EXACT_APPROVED_SCOPE')
 for source,digest in ob['local_evidence_hashes'].items():need(sha256((ROOT/source).read_bytes()).hexdigest()==digest,'ATVI_SOURCE_PIN');pins[source]=digest
 source=ob['price_source_path'];need(document['source_hashes'][source]==pins[source] and document['assembled']['price_source_references']['research:security:atvi']==[source],'ATVI_PRICE_IDENTITY')
 review['rows']=[r for r in review['rows'] if not (r['status']=='REVIEWED_NO_ACTION_FOR_PERIOD' and r.get('security_id')=='research:security:atvi' and '2022-07-29'<=r['start_exclusive']<='2022-08-25')]
 period_rows=[]
 for day in document['assembled']['session_dates']:
  if '2022-07-29'<=day<'2022-08-25':period_rows.append(dict(status='REVIEWED_NO_ACTION_FOR_PERIOD',security_id='research:security:atvi',ticker='ATVI',start_exclusive=day,end_inclusive='2022-08-25',selected_price_sources=[source],source_references=[approval_path,path,source],limitation='Root-reviewed conditional retrospective annual-dividend and nominal-price inference, not exhaustive feed; no extension outside scope.'))
 review['rows'].extend(period_rows);review['source_hashes'].update(pins);return dict(review_rows=rows,dividend_events=events,period_rows=period_rows,source_hashes=pins)

