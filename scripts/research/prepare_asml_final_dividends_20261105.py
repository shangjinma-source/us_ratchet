"""JPM public final notices, exact gross USD accounting; no search or execution."""
import json
from pathlib import Path
from hashlib import sha256
from fractions import Fraction as F
from scripts.research.review_downside_account_20261105 import read
ROOT=Path(__file__).resolve().parents[2]
SID='security:0000937966:N07059210'
DIRECTORY='tmp/asml_remaining_dividend_review_20261105'

def main():
    p=ROOT/DIRECTORY;api=read(p/'jpm_final_dividends.json')['data']['items']
    search=read(p/'jpm_search_asml.json')['data']['items'];assert dict(cusip='N07059210',name='ASML',symbol='ASML') in search
    document_path='tmp/old_continuous_baseline_20261026_v9/execution_inputs.json';doc=read(ROOT/document_path)
    parent=read(ROOT/'tmp/downside_max10_20261105_late_v7/contract.json',True)
    assert doc['prepared_input_candidate']['metadata'][SID]==dict(ticker='ASML',issuer_id='issuer:0000937966')
    names=[document_path,*[DIRECTORY+'/'+n for n in ['adr_home.html','globals.js','main-389e2277.67473b10.js','jpm_search_asml.json','jpm_final_dividends.json','jpm_final_pdf_receipts.json','jpm_final_2026-04-27.pdf','jpm_final_2026-07-28.pdf']],Path(__file__).relative_to(ROOT).as_posix()]
    pins={n:sha256((ROOT/n).read_bytes()).hexdigest() for n in names};assert pins[document_path]==parent['source_hashes'][document_path]
    for receipt in read(p/'jpm_final_pdf_receipts.json'):
        assert receipt['status']==200 and pins[receipt['path']]==receipt['sha256'] and (ROOT/receipt['path']).read_bytes().startswith(b'%PDF')
    table=[('2026-04-27','2026-05-05','3.16845','3.177',14),('2026-07-28','2026-08-05','2.137748','2.138',11)]
    remaining=[e for e in doc['provider_event_inventory'] if e['ticker']=='ASML' and '2026-03-31'<e['date']<='2026-07-30']
    assert {(e['date'],e['kind']) for e in remaining}=={(r[0],'dividends') for r in table}
    rows=[];events=[];mapping=[]
    for ex,pay,gross,provider,seq in table:
        final=[r for r in api if r.get('recordDate','')[:10]==ex];assert len(final)==1
        final=final[0];under=final['underlying']
        assert final['status']=='Final' and final['sequenceNo']==seq and final['ratio']=='1:1' and final['paymentDate'][:10]==pay
        assert F(str(final['ratePerDr']))==F(gross)==F(str(under['currencyPerDr']))*F(str(under['finalExchangeRate']))
        assert under['currency']=='EUR' and under['exchangeDate'][:10]==ex
        assert F(str(final['ratePerDr']))-F(str(final['withHoldingAmount']))==F(str(final['finalDivRatePerDr']))
        observed=[e for e in remaining if e['date']==ex];assert all(F(e['provider_payload']['amount'])==F(provider) for e in observed)
        for e in observed:
            name=e['source'];h=sha256((ROOT/name).read_bytes()).hexdigest();assert h==parent['source_hashes'][name];pins[name]=h
        refs=[DIRECTORY+'/jpm_final_dividends.json',DIRECTORY+'/jpm_final_'+ex+'.pdf',*sorted({e['source'] for e in observed})]
        url='https://adr.api.wsod.com/jpmadr-public/v1/cms/document?cmsId='+final['notices']['pdf']+'&sequenceNo='+str(seq)
        rows.append(dict(status='REVIEWED_ORDINARY_CASH_DIVIDEND',security_id=SID,ex_date=ex,payment_date=pay,amount_per_share=str(F(gross)),currency='USD',source_references=refs,observed_provider_events=observed,official_url=url,nominal_unit='ASML_NEW_YORK_REGISTERED_SHARE_RATIO_ONE_TO_ONE',provider_amount=provider,amount_resolution='FINAL_DEPOSITARY_GROSS_USD_OVERRIDES_INITIAL_OR_ROUNDED_PROVIDER',final_announcement_date=final['announcementDate'][:10],final_foreign_exchange_rate=str(under['finalExchangeRate'])))
        events.append(dict(event_id='asml-final-gross:'+SID+':'+ex,security_id=SID,ex_date=ex,payment_date=pay,amount_per_share=str(F(gross)),currency='USD',withholding_rate='0',assumption='GROSS_RESEARCH_NO_WITHHOLDING; JPM_FINAL_PAYMENT_DATE_AT_CLOSE; FINAL_AMOUNT_RETROSPECTIVE_ACCRUAL_NOT_PIT_SIGNAL'))
        mapping.append(dict(ex_date=ex,final_notice=final,source_url=url,post_cutoff_unpaid=pay>'2026-07-30'))
    result=dict(status='REVIEWED_TWO_ASML_FINAL_GROSS_DIVIDENDS',source_hashes=pins,review_rows=rows,dividend_events=events,mapping=mapping,
      timing_limitation='April final notice published Apr28 versus Apr27 exdate. Ledger final gross accrual at exdate is retrospective accounting, not contemporaneously known exact USD. No cash before pay; July8/5 beyond cutoff remains receivable.',
      decision_dependency_review=dict(monthly_sizing='continuous_guided_cost_monthly_provider.py:156 uses cash+held shares only, unpaid rights excluded',daily_exit='qqq_risk_budget_account_runner.py:88 risk.apply receives day/month/target/closes/adjustments, not receivable/equity',next_open_budget='cash only; unreceived dividend cannot increase available cash',impact='Apr27 close reported equity/DD contains finalApr28 amount; no sizing,20percent exit or buying-capacity dependency identified. Exact reported valuation is not fully point-in-time.',needs_root_acceptance=True),
      provenance='Public adr.com scripts disclosed search and dr/dividends route. API returned exact PDF cmsId and sequenceNo; no ID guessing or auth bypass. Both final PDFs retained.')
    out=p/'supplement.json';out.write_text(json.dumps(result,indent=2),encoding='utf8');print(out.relative_to(ROOT),sha256(out.read_bytes()).hexdigest())
if __name__=='__main__':main()
