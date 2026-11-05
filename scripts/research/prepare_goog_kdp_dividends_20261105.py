"""Four issuer-confirmed remaining-window dividends, accounting only."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from scripts.research.review_downside_account_20261105 import read
ROOT=Path(__file__).resolve().parents[2]
TABLE=[
 ('GOOG','security:0001652044:02079K107','2026-03-09','2026-03-16','21/100','https://www.sec.gov/Archives/edgar/data/1652044/000165204426000012/googexhibit991q42025.htm'),
 ('GOOG','security:0001652044:02079K107','2026-06-08','2026-06-15','11/50','https://www.sec.gov/Archives/edgar/data/1652044/000165204426000043/googexhibit991q12026.htm'),
 ('KDP','security:0001418135:49271V100','2026-03-27','2026-04-10','23/100','https://www.sec.gov/Archives/edgar/data/1418135/000141813526000003/exhibit991keurigdrpepperde.htm'),
 ('KDP','security:0001418135:49271V100','2026-06-26','2026-07-10','23/100','https://www.keurigdrpepper.com/keurig-dr-pepper-declares-quarterly-dividend-17/')]

def main():
    directory=ROOT/'tmp/goog_kdp_dividend_evidence_20261105';directory.mkdir(exist_ok=True)
    evidence=directory/'official_observations.json'
    evidence.write_text(json.dumps(dict(retrieval='2026-11-05 official SEC issuer earnings releases and issuer KDP site parsed web observations, not raw HTTP bytes',
        rows=[dict(ticker=t,security_id=s,ex_date=ex,record_date=ex,payment_date=pay,amount_per_share=a,url=url,nominal_unit='GOOG_CLASS_C_COMMON' if t=='GOOG' else 'KDP_COMMON',scope='GOOG issuer explicitly includes Class A/B/C, but mapping only frozen GOOG Class C SID; KDP issuer common shares. Ex-date independently matched frozen provider; not substituted from record.') for t,s,ex,pay,a,url in TABLE]),indent=2),encoding='utf8')
    source='tmp/old_continuous_baseline_20261026_v9/execution_inputs.json';doc=read(ROOT/source)
    parent=read(ROOT/'tmp/downside_max10_20261105_late_v6/contract.json',True)
    pins={n:sha256((ROOT/n).read_bytes()).hexdigest() for n in [source,evidence.relative_to(ROOT).as_posix(),Path(__file__).relative_to(ROOT).as_posix()]}
    assert pins[source]==parent['source_hashes'][source]
    remaining=[e for e in doc['provider_event_inventory'] if e['ticker'] in ('GOOG','KDP') and '2026-02-27'<e['date']<='2026-07-30']
    assert {(e['ticker'],e['date'],e['kind']) for e in remaining}=={(t,ex,'dividends') for t,s,ex,pay,a,u in TABLE}
    existing=doc['dividend_events']+read(ROOT/'tmp/downside_max10_20261105_late_v6/bounded_execution_evidence.json',True)['events']
    rows=[];events=[]
    for ticker,sid,ex,pay,amount,url in TABLE:
        assert doc['prepared_input_candidate']['metadata'][sid]['ticker']==ticker
        observed=[e for e in remaining if e['ticker']==ticker and e['date']==ex]
        assert observed and all(F(e['provider_payload']['amount'])==F(amount) for e in observed)
        assert not any(e['security_id']==sid and e['ex_date']==ex for e in existing)
        for e in observed:
            name=e['source'];digest=sha256((ROOT/name).read_bytes()).hexdigest();assert digest==parent['source_hashes'][name];pins[name]=digest
        refs=[evidence.relative_to(ROOT).as_posix(),*sorted({e['source'] for e in observed})]
        rows.append(dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=amount,currency='USD',source_references=refs,observed_provider_events=observed,official_url=url,nominal_unit='GOOG_CLASS_C_COMMON' if ticker=='GOOG' else 'KDP_COMMON'))
        events.append(dict(event_id='goog-kdp-gross:'+sid+':'+ex,security_id=sid,ex_date=ex,payment_date=pay,amount_per_share=amount,withholding_rate='0',currency='USD',assumption='GROSS_RESEARCH_NO_WITHHOLDING; ISSUER_PAYMENT_SESSION_CLOSE_NOT_HSBC_CREDIT_CONFIRMATION'))
    result=dict(status='REVIEWED_FOUR_GOOG_KDP_REMAINING_DIVIDENDS',source_hashes=pins,review_rows=rows,dividend_events=events,window='2026-02-27_EXCLUSIVE_TO_2026-07-30',scope='No prior events duplicated. No Class A or Class B SID, split, spin-off or identity action admission. Accounting evidence only, not news signal.')
    out=directory/'supplement.json';out.write_text(json.dumps(result,indent=2),encoding='utf8');print(out.relative_to(ROOT),sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':main()
