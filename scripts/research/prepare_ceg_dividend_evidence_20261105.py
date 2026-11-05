"""Bounded ten CEG ordinary dividend mappings; no account execution."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from scripts.research.review_downside_account_20261105 import read

ROOT=Path(__file__).resolve().parents[2]
SID='security:0001868275:21037T109'
OFFICIAL='https://investors.constellationenergy.com/static-files/848d735d-45de-4bcc-bb3c-09c13a8e7bf6'
Q1='https://investors.constellationenergy.com/static-files/1bf1dc88-f513-430a-96da-ad4997e7130e'
Q2='https://investors.constellationenergy.com/news-releases/news-release-details/constellation-energy-corporation-declares-dividend-12'
TABLE=[
 ('2024-03-07','2024-03-08','2024-03-19','0.3525',OFFICIAL),
 ('2024-05-29','2024-05-29','2024-06-10','0.3525',OFFICIAL),
 ('2024-08-12','2024-08-12','2024-09-06','0.3525',OFFICIAL),
 ('2024-11-15','2024-11-15','2024-12-06','0.3525',OFFICIAL),
 ('2025-03-07','2025-03-07','2025-03-18','0.3878',Q1),
 ('2025-05-16','2025-05-16','2025-06-06','0.3878',Q1),
 ('2025-08-18','2025-08-18','2025-09-05','0.3878',Q1),
 ('2025-11-17','2025-11-17','2025-12-05','0.3878',Q1),
 ('2026-03-09','2026-03-09','2026-03-20','0.4265',Q1),
 ('2026-05-15','2026-05-15','2026-06-05','0.4265',Q2)]



def main():
    directory=ROOT/'tmp/ceg_dividend_evidence_20261105'; directory.mkdir(exist_ok=True)
    evidence=directory/'official_web_observations.json'
    document_path=ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'
    document=json.loads(document_path.read_bytes())
    parent=read(ROOT/'tmp/downside_max10_20261105_late_v1/contract.json',True)
    hashes={p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in [evidence,document_path,Path(__file__)]}
    assert hashes[document_path.relative_to(ROOT).as_posix()]==parent['source_hashes'][document_path.relative_to(ROOT).as_posix()]
    inventory=[e for e in document['provider_event_inventory'] if e['ticker']=='CEG' and e['kind']=='dividends' and '2024-01-01'<=e['date']<='2026-07-30']
    assert {e['date'] for e in inventory}=={r[0] for r in TABLE}
    rows=[];events=[];mapping=[]
    for ex,record,pay,amount,url in TABLE:
        observed=[e for e in inventory if e['date']==ex]
        expected_provider={'0.3525':'0.353','0.3878':'0.388','0.4265':'0.427'}[amount]
        assert observed and all(F(e['provider_payload']['amount'])==F(expected_provider) for e in observed)
        for event in observed:
            name=event['source'];digest=sha256((ROOT/name).read_bytes()).hexdigest()
            assert digest==parent['source_hashes'][name];hashes[name]=digest
        refs=[evidence.relative_to(ROOT).as_posix(),*sorted({e['source'] for e in observed})]
        rows.append(dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=SID,ex_date=ex,payment_date=pay,
            amount_per_share=amount,currency='USD',source_references=refs,observed_provider_events=observed,
            official_url=url,evidence_scope='PROVIDER_EX_DATE_PLUS_OFFICIAL_ISSUER_PAYMENT_RECORD',nominal_unit='CEG_NOMINAL_COMMON_SHARE', provider_amount=expected_provider, amount_resolution='ISSUER_EXACT_AMOUNT_OVERRIDES_EXPLICIT_PROVIDER_THREE_DECIMAL_ROUNDING'))
        events.append(dict(event_id='ceg-reviewed-gross:'+SID+':'+ex,security_id=SID,ex_date=ex,payment_date=pay,
            amount_per_share=amount,withholding_rate='0',currency='USD',
            assumption='EXPLICIT_GROSS_RESEARCH_NO_WITHHOLDING_MODELED_NOT_USER_TAX_RATE; PAYMENT_AT_SESSION_CLOSE'))
        mapping.append(dict(ex_date=ex,record_date=record,payment_date=pay,amount_per_share=amount,official_url=url,
            ex_date_evidence='FROZEN_PROVIDER_EVENT_DATE_NOT_SUBSTITUTED_WITH_RECORD_DATE',
            publication_scope='2024/2025 annual report retrospective accounting only; 2026 issuer declaration. Not a contemporaneous alpha input.'))
    result=dict(status='REVIEWED_BOUNDED_CEG_ORDINARY_DIVIDENDS',window='2024-01-01/2026-07-30',security_id=SID,
        source_hashes=hashes,review_rows=rows,dividend_events=events,mapping=mapping,
        scope='Gross nominal per common share; frozen source has no splits. Ex-date rights; issuer payment at model session close, not HSBC actual credit confirmation. No stock dividend or other action admission.')
    output=directory/'supplement.json';output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(output.relative_to(ROOT),sha256(output.read_bytes()).hexdigest(),len(events))


if __name__=='__main__':main()
