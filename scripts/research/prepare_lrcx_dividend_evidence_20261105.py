"""Bounded ten LRCX ordinary dividend mappings; no account execution."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from scripts.research.review_downside_account_20261105 import read

ROOT=Path(__file__).resolve().parents[2]
SID='security:0000707549:512807306'
OFFICIAL='https://www.prnewswire.com/news-releases/lam-research-corporation-announces-a-13-increase-in-quarterly-dividend-302541354.html'
Q2='https://newsroom.lamresearch.com/2026-05-21-Lam-Research-Corporation-Declares-Quarterly-Dividend'
TABLE=[('2025-09-24','2025-09-24','2025-10-15','13/50',OFFICIAL),('2026-06-17','2026-06-17','2026-07-08','13/50',Q2)]



def main():
    directory=ROOT/'tmp/lrcx_dividend_evidence_20261105';directory.mkdir(exist_ok=True)
    evidence=directory/'official_web_observations.json'
    document_path=ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'
    document=json.loads(document_path.read_bytes())
    parent=read(ROOT/'tmp/downside_max10_20261105_late_v4/contract.json',True)
    assert document['prepared_input_candidate']['metadata'][SID]==dict(ticker='LRCX',issuer_id='issuer:0000707549')
    remaining=[e for e in document['provider_event_inventory'] if e['ticker']=='LRCX' and '2025-08-29'<=e['date']<='2026-07-30']
    assert all(e['kind']=='dividends' for e in remaining)
    assert {e['date'] for e in remaining}=={'2025-09-24','2025-12-03','2026-03-04','2026-06-17'}
    existing=read(ROOT/'tmp/downside_max10_20261105_late_v4/bounded_execution_evidence.json',True)
    previous=[e for e in existing['events'] if e['security_id']==SID]
    assert {(e['ex_date'],e['payment_date'],e['amount_per_share']) for e in previous}=={('2025-12-03','2026-01-07','13/50'),('2026-03-04','2026-04-08','13/50')}
    hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in [evidence,document_path,Path(__file__)]}
    assert hashes[document_path.relative_to(ROOT).as_posix()]==parent['source_hashes'][document_path.relative_to(ROOT).as_posix()]
    inventory=[e for e in document['provider_event_inventory'] if e['ticker']=='LRCX' and e['kind']=='dividends' and e['date'] in {r[0] for r in TABLE}]
    assert {e['date'] for e in inventory}=={r[0] for r in TABLE}
    rows=[];events=[];mapping=[]
    for ex,record,pay,amount,url in TABLE:
        observed=[e for e in inventory if e['date']==ex]
        assert observed and all(F(e['provider_payload']['amount'])==F(amount) for e in observed)
        for event in observed:
            name=event['source'];digest=sha256((ROOT/name).read_bytes()).hexdigest()
            assert digest==parent['source_hashes'][name];hashes[name]=digest
        refs=[evidence.relative_to(ROOT).as_posix(),*sorted({e['source'] for e in observed})]
        rows.append(dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=SID,ex_date=ex,payment_date=pay,
            amount_per_share=amount,currency='USD',source_references=refs,observed_provider_events=observed,
            official_url=url,evidence_scope='PROVIDER_EX_DATE_PLUS_OFFICIAL_ISSUER_PAYMENT_RECORD',nominal_unit='LRCX_POST_OCTOBER_2024_SPLIT_COMMON_SHARE'))
        events.append(dict(event_id='lrcx-reviewed-gross:'+SID+':'+ex,security_id=SID,ex_date=ex,payment_date=pay,
            amount_per_share=amount,withholding_rate='0',currency='USD',
            assumption='EXPLICIT_GROSS_RESEARCH_NO_WITHHOLDING_MODELED_NOT_USER_TAX_RATE; PAYMENT_AT_SESSION_CLOSE'))
        mapping.append(dict(ex_date=ex,record_date=record,payment_date=pay,amount_per_share=amount,official_url=url,
            ex_date_evidence='FROZEN_PROVIDER_EVENT_DATE_NOT_SUBSTITUTED_WITH_RECORD_DATE',
            publication_scope='Issuer declarations; accounting only, not a contemporaneous alpha input.'))
    result=dict(status='REVIEWED_BOUNDED_LRCX_ORDINARY_DIVIDENDS',window='2025-08-29/2026-07-30',security_id=SID,
        source_hashes=hashes,review_rows=rows,dividend_events=events,mapping=mapping,
        already_admitted=['2025-12-03','2026-03-04'],scope='Gross nominal per post-October2024 common share; no pre-split SID mapping or split entitlement admission. Ex-date rights; issuer payment at model session close, not HSBC actual credit confirmation. No stock dividend or other action admission.')
    output=directory/'supplement.json';output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(output.relative_to(ROOT),sha256(output.read_bytes()).hexdigest(),len(events))


if __name__=='__main__':main()
