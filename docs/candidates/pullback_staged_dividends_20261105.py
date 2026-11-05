"""Five bounded staged-holding dividend pairs, exact issuer gross amounts."""
from pathlib import Path
import json
from fractions import Fraction as F
from hashlib import sha256
from backtest.research_exact_fraction_json import loads
ROOT=Path(__file__).resolve().parents[2]
ROWS=[('CDW','2024-02-23','2024-03-12','0.62','cdw_20240223'),('ROST','2024-03-14','2024-03-29','0.3675','rost_20240314'),('GOOG','2024-06-10','2024-06-17','0.20','goog_googl_20240610'),('GOOGL','2024-06-10','2024-06-17','0.20','goog_googl_20240610'),('EXC','2025-02-24','2025-03-14','0.40','exc_20250224')]
def need(ok,why):
 if not ok:raise ValueError(why)
def append_review(document,review):
 path='tmp/pullback_account_20261105/late_price_v4/potential_action_inventory.json';raw=(ROOT/path).read_bytes();inventory=loads(raw);pins={path:sha256(raw).hexdigest()};events=[];rows=[]
 for ticker,ex,pay,amount,stem in ROWS:
  path='tmp/pullback_action_sources_20261105/'+stem+'_observation.json';raw=(ROOT/path).read_bytes();ob=json.loads(raw);pins[path]=sha256(raw).hexdigest();facts=next((e for e in ob.get('events',[]) if e['ticker']==ticker),ob.get('event',ob));need(facts['ex_date']==ex and facts['payment_date']==pay and F(facts.get('nominal_amount',facts.get('gross_amount','-1')))==F(amount),'OFFICIAL_EVENT_MISMATCH')
  found=[e for r in inventory['rows'] for e in r['gate']['unmapped_events'] if e.get('ticker')==ticker and e['date']==ex and e['kind']=='dividends'];need(found and len({e['security_id'] for e in found})==1,'EXACT_PROVIDER_EVENT');sid=found[0]['security_id'];need(not any(e['security_id']==sid and e['ex_date']==ex for e in document['dividend_events']),'DUPLICATE_EVENT')
  for e in found:
   source=e['source'];digest=sha256((ROOT/source).read_bytes()).hexdigest();need(document['source_hashes'][source]==digest,'SOURCE_PIN');pins[source]=digest
  row=dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=str(F(amount)),currency='USD',source_references=[path]+sorted({e['source'] for e in found}),observed_provider_events=[{k:v for k,v in e.items() if k!='security_id'} for e in found],limitation='GROSS_RETROSPECTIVE; issuer payment close not actual broker net; ROST explicit0.3675 rather than rounded0.368')
  event=dict(event_id='pullback-staged-gross:'+sid+':'+ex,security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=str(F(amount)),currency='USD',withholding_rate='0',assumption=row['limitation']);rows.append(row);events.append(event)
 document['dividend_events'].extend(events);review['rows'].extend(rows);review['source_hashes'].update(pins);return dict(review_rows=rows,dividend_events=events,source_hashes=pins)

