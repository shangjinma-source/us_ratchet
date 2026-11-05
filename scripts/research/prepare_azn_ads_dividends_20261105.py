"""Admit only reviewed pre-conversion ADS ordinary dividends, offline."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from scripts.research.review_downside_account_20261105 import read
ROOT=Path(__file__).resolve().parents[2]
SID='security:0000901832:046353108'

def main():
    directory=ROOT/'tmp/azn_ads_dividends_20261105';directory.mkdir(exist_ok=True)
    source='tmp/old_continuous_baseline_20261026_v9/execution_inputs.json'
    batch_path='tmp/azn_dividend_independent_20261105/batch_review.json'
    batch=read(ROOT/batch_path);doc=read(ROOT/source)
    parent=read(ROOT/'tmp/downside_max10_20261105_late_v3/contract.json',True)
    names=[source,batch_path,'tmp/azn_dividend_independent_20261105/review.json',
        'tmp/fixed12_official_actions_20261014_v1/azn_ads_unit_web_observation.json',
        'tmp/azn_next12_conditional_admission_20261014_v1.json',
        'tmp/equal_four_20261105/source_review/admitted_supplement.json',Path(__file__).relative_to(ROOT).as_posix()]
    hashes={name:sha256((ROOT/name).read_bytes()).hexdigest() for name in names}
    for name in names:
        if name in parent['source_hashes']:assert hashes[name]==parent['source_hashes'][name]
    for name,h in batch['source_hashes'].items():assert sha256((ROOT/name).read_bytes()).hexdigest()==h
    rows=[];events=[]
    for item in batch['events']:
        ex=item['ex_date'];amount=F(item['ads_amount']);ordinary=F(item['ordinary_amount'])
        assert ex<'2026-02-02' and amount==ordinary/2
        observed=[e for e in doc['provider_event_inventory'] if e['ticker']=='AZN' and e['kind']=='dividends' and e['date']==ex]
        assert observed and all(F(e['provider_payload']['amount'])==ordinary for e in observed)
        for e in observed:
            name=e['source'];h=sha256((ROOT/name).read_bytes()).hexdigest()
            assert h==parent['source_hashes'][name];hashes[name]=h
        refs=[batch_path,'tmp/azn_dividend_independent_20261105/review.json','tmp/fixed12_official_actions_20261014_v1/azn_ads_unit_web_observation.json',*sorted({e['source'] for e in observed})]
        rows.append(dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=SID,ex_date=ex,payment_date=item['payment_date'],amount_per_share=str(amount),currency='USD',source_references=refs,observed_provider_events=observed,nominal_unit='HISTORICAL_US_ADS_REPRESENTING_HALF_ORDINARY',ordinary_amount=str(ordinary),amount_resolution='ISSUER_ORDINARY_AMOUNT_DIVIDED_BY_TWO_PER_HISTORICAL_ADS_NOT_PROVIDER_DIRECT',ex_date_scope=item['ex_date_basis']))
        events.append(dict(event_id='azn-ads-reviewed-gross:'+SID+':'+ex,security_id=SID,ex_date=ex,payment_date=item['payment_date'],amount_per_share=str(amount),withholding_rate='0',currency='USD',assumption='GROSS_NO_WITHHOLDING_OR_ADR_FEE; ISSUER_PAY_DATE_SESSION_CLOSE_NOT_DEPOSITARY_OR_HSBC_CREDIT_PROOF'))
    inventory=[e for e in doc['provider_event_inventory'] if e['ticker']=='AZN']
    result=dict(status='REVIEWED_THREE_PRECONVERSION_AZN_ADS_DIVIDENDS',source_hashes=hashes,review_rows=rows,dividend_events=events,
        window_inventory=inventory,already_admitted=['2024-02-22'],newly_admitted=[e['ex_date'] for e in events],
        excluded=[dict(date='2026-02-02',kind='splits',reason='ADS_TO_ORDINARY_CONVERSION_NOT_ADMITTED'),dict(date='2026-02-19',kind='dividends',reason='POST_CONVERSION_UNIT_AND_PAY_MAPPING_NOT_ADMITTED')],
        scope='Full existing provider inventory accounted for, not all events admitted. Exact unchanged historical ADS units required. No split/identity/cash-in-lieu admission. Offline prior official observations, retrospective accounting only.')
    output=directory/'supplement.json';output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(output.relative_to(ROOT),sha256(output.read_bytes()).hexdigest())
if __name__=='__main__':main()
