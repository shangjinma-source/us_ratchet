"""Bounded ten META ordinary dividend mappings; no account execution."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from scripts.research.review_downside_account_20261105 import read

ROOT=Path(__file__).resolve().parents[2]
SID='security:0001326801:30303M102'
OFFICIAL='https://www.sec.gov/Archives/edgar/data/1326801/000162828026025534/meta-12312025x10kars.htm'
Q1='https://s21.q4cdn.com/399680738/files/doc_news/Meta-Announces-Quarterly-Cash-Dividend-2026.pdf'
Q2='https://s21.q4cdn.com/399680738/files/doc_news/Meta-Announces-Quarterly-Cash-Dividend-3f2eb420d-2026.pdf'
TABLE=[
 ('2024-02-21','2024-02-22','2024-03-26','1/2',OFFICIAL),
 ('2024-06-14','2024-06-14','2024-06-26','1/2',OFFICIAL),
 ('2024-09-16','2024-09-16','2024-09-26','1/2',OFFICIAL),
 ('2024-12-16','2024-12-16','2024-12-27','1/2',OFFICIAL),
 ('2025-03-14','2025-03-14','2025-03-26','21/40',OFFICIAL),
 ('2025-06-16','2025-06-16','2025-06-26','21/40',OFFICIAL),
 ('2025-09-22','2025-09-22','2025-09-29','21/40',OFFICIAL),
 ('2025-12-15','2025-12-15','2025-12-23','21/40',OFFICIAL),
 ('2026-03-16','2026-03-16','2026-03-26','21/40',Q1),
 ('2026-06-15','2026-06-15','2026-06-25','21/40',Q2)]


def main():
    directory=ROOT/'tmp/meta_dividend_evidence_20261105'
    evidence=directory/'official_web_observations.json'
    document_path=ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'
    document=json.loads(document_path.read_bytes())
    parent=read(ROOT/'tmp/downside_max10_20261105_late_v1/contract.json',True)
    hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in [evidence,document_path,Path(__file__)]}
    assert hashes[document_path.relative_to(ROOT).as_posix()]==parent['source_hashes'][document_path.relative_to(ROOT).as_posix()]
    inventory=[e for e in document['provider_event_inventory'] if e['ticker']=='META' and e['kind']=='dividends' and '2024-01-01'<=e['date']<='2026-07-30']
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
            official_url=url,evidence_scope='PROVIDER_EX_DATE_PLUS_OFFICIAL_ISSUER_PAYMENT_RECORD',nominal_unit='META_CLASS_A_NOMINAL_COMMON_SHARE'))
        events.append(dict(event_id='meta-reviewed-gross:'+SID+':'+ex,security_id=SID,ex_date=ex,payment_date=pay,
            amount_per_share=amount,withholding_rate='0',currency='USD',
            assumption='EXPLICIT_GROSS_RESEARCH_NO_WITHHOLDING_MODELED_NOT_USER_TAX_RATE; PAYMENT_AT_SESSION_CLOSE'))
        mapping.append(dict(ex_date=ex,record_date=record,payment_date=pay,amount_per_share=amount,official_url=url,
            ex_date_evidence='FROZEN_PROVIDER_EVENT_DATE_NOT_SUBSTITUTED_WITH_RECORD_DATE',
            publication_scope='2024/2025 annual report retrospective accounting only; 2026 issuer declaration. Not a contemporaneous alpha input.'))
    result=dict(status='REVIEWED_BOUNDED_META_ORDINARY_DIVIDENDS',window='2024-01-01/2026-07-30',security_id=SID,
        source_hashes=hashes,review_rows=rows,dividend_events=events,mapping=mapping,
        scope='Gross nominal per Class A share; frozen source has no splits. Ex-date rights; issuer payment at model session close, not HSBC actual credit confirmation. No stock dividend or other action admission.')
    output=directory/'supplement.json';output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(output.relative_to(ROOT),sha256(output.read_bytes()).hexdigest(),len(events))


if __name__=='__main__':main()
