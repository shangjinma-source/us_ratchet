"""Four issuer-confirmed remaining-window dividends, accounting only."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from scripts.research.review_downside_account_20261105 import read
ROOT=Path(__file__).resolve().parents[2]
TABLE=[('GEHC','security:0001932393:36266G107','2026-07-24','2026-08-14','7/200','https://investor.gehealthcare.com/news-releases/news-release-details/ge-healthcare-announces-cash-dividend-second-quarter-2026')]


def main():
    directory=ROOT/'tmp/gehc_dividend_evidence_20261105';directory.mkdir(exist_ok=True)
    evidence=directory/'official_observations.json'
    evidence.write_text(json.dumps(dict(retrieval='2026-11-05 official GEHC June30 issuer release parsed web observation, not raw HTTP bytes',
        rows=[dict(ticker=t,security_id=s,ex_date=ex,record_date=ex,payment_date=pay,amount_per_share=a,url=url,nominal_unit='GEHC_COMMON',scope='Issuer June30 declaration confirms commonshare amount, recordJuly24 andpayAugust14. Exdate independently matched frozen provider; not record-date substitution.') for t,s,ex,pay,a,url in TABLE]),indent=2),encoding='utf8')
    source='tmp/old_continuous_baseline_20261026_v9/execution_inputs.json';doc=read(ROOT/source)
    parent=read(ROOT/'tmp/downside_max10_20261105_late_v8/contract.json',True)
    pins={n:sha256((ROOT/n).read_bytes()).hexdigest() for n in [source,evidence.relative_to(ROOT).as_posix(),Path(__file__).relative_to(ROOT).as_posix()]}
    assert pins[source]==parent['source_hashes'][source]
    remaining=[e for e in doc['provider_event_inventory'] if e['ticker'] in ('GEHC',) and '2026-06-30'<e['date']<='2026-07-30']
    assert {(e['ticker'],e['date'],e['kind']) for e in remaining}=={(t,ex,'dividends') for t,s,ex,pay,a,u in TABLE}
    existing=doc['dividend_events']+read(ROOT/'tmp/downside_max10_20261105_late_v8/bounded_execution_evidence.json',True)['events']
    rows=[];events=[]
    for ticker,sid,ex,pay,amount,url in TABLE:
        assert doc['prepared_input_candidate']['metadata'][sid]['ticker']==ticker
        observed=[e for e in remaining if e['ticker']==ticker and e['date']==ex]
        assert observed and all(F(e['provider_payload']['amount'])==F(amount) for e in observed)
        assert not any(e['security_id']==sid and e['ex_date']==ex for e in existing)
        for e in observed:
            name=e['source'];digest=sha256((ROOT/name).read_bytes()).hexdigest();assert digest==parent['source_hashes'][name];pins[name]=digest
        refs=[evidence.relative_to(ROOT).as_posix(),*sorted({e['source'] for e in observed})]
        rows.append(dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=amount,currency='USD',source_references=refs,observed_provider_events=observed,official_url=url,nominal_unit='GEHC_COMMON'))
        events.append(dict(event_id='gehc-gross:'+sid+':'+ex,security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=amount,withholding_rate='0',currency='USD',assumption='GROSS_RESEARCH_NO_WITHHOLDING; ISSUER_PAYMENT_SESSION_CLOSE_NOT_HSBC_CREDIT_CONFIRMATION'))
    result=dict(status='REVIEWED_ONE_GEHC_REMAINING_DIVIDEND',source_hashes=pins,review_rows=rows,dividend_events=events,window='2026-06-30_EXCLUSIVE_TO_2026-07-30',scope='No prior events duplicated. Payment August14 beyond July30 cutoff: only nonspendable receivable, never early cash. No split, spin-off or identity admission. Accounting evidence only, not news signal.')
    out=directory/'supplement.json';out.write_text(json.dumps(result,indent=2),encoding='utf8');print(out.relative_to(ROOT),sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':main()
