"""Two bounded accounting mappings; no strategy execution or source mutation."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from scripts.research.review_downside_account_20261105 import read

ROOT=Path(__file__).resolve().parents[2]
TABLE=[('CSX','research:security:csx','2021-05-27','2021-06-15','7/25','0.093333',
 'https://www.sec.gov/Archives/edgar/data/277948/000119312521184344/d177874dex991.htm'),
 ('EBAY','research:security:ebay','2021-05-28','2021-06-18','9/50','0.18',
 'https://www.sec.gov/Archives/edgar/data/1065088/000106508821000009/exhibit991erebayq12021.htm')]

def main():
    directory=ROOT/'tmp/early_dividend_gaps_20261105';directory.mkdir(exist_ok=True)
    observations=directory/'official_observations.json'
    observations.write_text(json.dumps(dict(retrieval='Official SEC parsed web views, 2026-11-05; observations not original HTTP bytes',
        csx=dict(url=TABLE[0][-1],publication='2021-06-04',nominal_amount='0.28',pay='2021-06-15',
                 fact='Issuer confirms regular cash dividend unaffected by three-for-one split distributed June 28. Provider amount is rounded future split-adjusted, not nominal cash entitlement.'),
        ebay=dict(url=TABLE[1][-1],publication='2021-04-28',nominal_amount='0.18',record='2021-06-01',pay='2021-06-18'),
        limitation='Retrospective accounting evidence, not alpha; ex dates remain frozen provider dates. No admission of CSX June split or ALXN May absence.'),indent=2),encoding='utf8')
    source='tmp/recent_continuous_baseline_20261026_v7/execution_inputs.json'
    parent=read(ROOT/'tmp/downside_max10_20261105_early_v1/contract.json',True)
    doc=json.loads((ROOT/source).read_bytes())
    hashes={p:sha256((ROOT/p).read_bytes()).hexdigest() for p in [source,observations.relative_to(ROOT).as_posix(),Path(__file__).relative_to(ROOT).as_posix()]}
    assert hashes[source]==parent['source_hashes'][source]
    rows=[];events=[]
    for ticker,sid,ex,pay,amount,provider_amount,url in TABLE:
        observed=[e for e in doc['provider_event_inventory'] if e['ticker']==ticker and e['kind']=='dividends' and e['date']==ex]
        assert observed and all(F(str(e['provider_event']['amount']))==F(provider_amount) for e in observed)
        for e in observed:
            name=e['source'];digest=sha256((ROOT/name).read_bytes()).hexdigest()
            assert digest==parent['source_hashes'][name];hashes[name]=digest
        refs=[observations.relative_to(ROOT).as_posix(),*sorted({e['source'] for e in observed})]
        normalized=[dict(ticker=ticker,source=e['source'],kind='dividends',date=ex,provider_payload={k:str(v) if k=='amount' else v for k,v in e['provider_event'].items()},mapping_status='REQUIRES_EXPOSURE_SCOPED_ECONOMIC_MAPPING') for e in observed]
        rows.append(dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=amount,currency='USD',source_references=refs,observed_provider_events=normalized,official_url=url,nominal_unit='PRE_SPLIT_NOMINAL_SHARE' if ticker=='CSX' else 'NOMINAL_COMMON_SHARE',provider_amount=provider_amount,amount_resolution='OFFICIAL_EXACT_NOMINAL_ENTITLEMENT_NOT_ROUNDED_PROVIDER_MULTIPLICATION'))
        events.append(dict(event_id='early-reviewed-gross:'+sid+':'+ex,security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=amount,withholding_rate='0',currency='USD',assumption='EXPLICIT_GROSS_RESEARCH; ISSUER_PAYMENT_SESSION_CLOSE_NOT_HSBC_CONFIRMATION'))
    result=dict(status='REVIEWED_TWO_ORDINARY_DIVIDENDS_ONLY',source_hashes=hashes,review_rows=rows,dividend_events=events,not_admitted=['ALXN May absence','CSX June split'])
    output=directory/'supplement.json';output.write_text(json.dumps(result,indent=2),encoding='utf8')
    print(output.relative_to(ROOT),sha256(output.read_bytes()).hexdigest())

if __name__=='__main__':main()
