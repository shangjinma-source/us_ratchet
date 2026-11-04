"""Read-only actual BUY / prior seven-calendar-day SEC metadata intersection."""
import json
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2]
def run():
    source=ROOT/'tmp/historical_news_coverage_20261027/sec_event_inventory_fiscal_identity_v5.json'
    inventory=json.loads(source.read_bytes());results=[];counts={};pins={str(source.relative_to(ROOT)):sha256(source.read_bytes()).hexdigest()}
    for window in inventory['windows']:
        name=window['window'];path=ROOT/window['frozen_book']['path'];raw=path.read_bytes()
        assert sha256(raw).hexdigest()==window['frozen_book']['sha256']
        book=json.loads(raw);pins[str(path.relative_to(ROOT))]=sha256(raw).hexdigest()
        identities={r['security_id']:r for r in window['rows']};ledger={r['date']:r for r in book['daily_ledger']}
        freeze={oid:r for r in book['order_log'] if r['event']=='FROZEN_TARGET_FOR_NEXT_OPEN' for oid in r['order_ids']}
        buys=[r for r in book['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED' and r['side']=='BUY'];counts[name]=len(buys)
        for buy in buys:
            sid=buy['security_id'];identity=identities.get(sid)
            if not identity:continue
            order=freeze[buy['id']];decision=order['date'];opening=datetime.fromisoformat(buy['date']+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York'))
            unique={}
            for idx in identity['candidate_event_indices']:
                event=inventory['issuers'][identity['cik']]['events'][idx];accepted=datetime.fromisoformat(event['acceptance'])
                if opening-timedelta(days=7)<=accepted<opening:unique[event['accession']]=event
            for event in unique.values():
                results.append(dict(window=name,execution_date=buy['date'],decision_date=decision,security_id=sid,tickers=identity['tickers'],held_at_decision=ledger.get(decision,{}).get('shares',{}).get(sid,0),buy_quantity=buy['quantity'],accession=event['accession'],acceptance=event['acceptance'],official_directory='https://www.sec.gov/Archives/edgar/data/'+str(int(identity['cik']))+'/'+event['accession'].replace('-','')+'/',identity_status=identity['identity_status'],body_verified=False,earliest_publication_verified=False,model_cache_verified=False,prior_outcome_seen='BASELINE_ALREADY_REVIEWED_EVENT_RETURN_NOT_RANKED',missing=['Full text','Actual release timestamp and before-open processing','Historical identity admission','Event-specific prior research inventory']))
    results.sort(key=lambda r:(r['execution_date'],r['security_id'],r['acceptance']))
    output=ROOT/'tmp/news_actual_buy_intersection_20261104';output.mkdir(exist_ok=False)
    result=dict(rule='All actual baseline BUY fills intersect prior 7 calendar days of existing SEC acceptance metadata; not performance-ranked',buy_counts=counts,intersection_count=len(results),first_five=results[:5],source_hashes=pins)
    (output/'inventory.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':run()
