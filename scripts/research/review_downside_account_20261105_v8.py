"""v8 independent final-notice and cutoff audit; reuses existing finance review."""
import argparse,inspect,json
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from scripts.research import review_downside_account_20261105_v7 as prior
previous=prior.previous;ROOT=prior.ROOT;base=prior.base;require=prior.require
FREEZE='research_contracts/downside_max10_resume_v8_20261105/freeze.json'
ARTIFACT='tmp/asml_remaining_dividend_review_20261105/supplement.json'
DIGEST='2fac5620c3e9f99cf3338219121e6239a6b19a62a82483238f71bafa539f65d7'
SID='security:0000937966:N07059210'

def validate_asml_pairs(artifact,original_events,inventory):
    require(artifact['status']=='REVIEWED_TWO_ASML_FINAL_GROSS_DIVIDENDS','ASML_STATUS')
    prefix='tmp/asml_remaining_dividend_review_20261105/'
    api=base.read(ROOT/(prefix+'jpm_final_dividends.json'))['data']['items']
    search=base.read(ROOT/(prefix+'jpm_search_asml.json'))['data']['items']
    require(dict(cusip='N07059210',name='ASML',symbol='ASML') in search,'ASML_PUBLIC_SEARCH_IDENTITY')
    require(len(artifact['review_rows'])==len(artifact['dividend_events'])==len(artifact['mapping'])==2,'ASML_TWO_ONLY')
    table=[('2026-04-27','2026-05-05','3.16845','3.177','2026-04-28',14),('2026-07-28','2026-08-05','2.137748','2.138','2026-07-28',11)]
    for row,event,mapping,(ex,pay,gross,raw,ann,seq) in zip(artifact['review_rows'],artifact['dividend_events'],artifact['mapping'],table):
        matches=[x for x in api if x.get('recordDate','')[:10]==ex];require(len(matches)==1,'ASML_FINAL_UNIQUE');final=matches[0];under=final['underlying']
        require(final['status']=='Final' and final['sequenceNo']==seq and final['announcementDate'][:10]==ann and final['paymentDate'][:10]==pay and final['ratio']=='1:1','ASML_FINAL_NOTICE')
        require(F(str(final['ratePerDr']))==F(gross)==F(str(under['currencyPerDr']))*F(str(under['finalExchangeRate'])) and under['currency']=='EUR' and under['exchangeDate'][:10]==ex,'ASML_FINAL_FX_GROSS')
        require(F(str(final['ratePerDr']))-F(str(final['withHoldingAmount']))==F(str(final['finalDivRatePerDr'])),'ASML_NET_DISTINCT')
        require(row['security_id']==event['security_id']==SID and row['ex_date']==event['ex_date']==ex and row['payment_date']==event['payment_date']==pay,'ASML_FIXED_DATES_SID')
        require(F(row['amount_per_share'])==F(event['amount_per_share'])==F(gross) and row['currency']==event['currency']=='USD' and F(event['withholding_rate'])==0,'ASML_GROSS_NOT_ESTIMATE_OR_NET')
        require(row['final_announcement_date']==ann and row['amount_resolution']=='FINAL_DEPOSITARY_GROSS_USD_OVERRIDES_INITIAL_OR_ROUNDED_PROVIDER' and row['nominal_unit']=='ASML_NEW_YORK_REGISTERED_SHARE_RATIO_ONE_TO_ONE','ASML_TIMING_AND_UNIT')
        require(mapping['final_notice']==final and mapping['post_cutoff_unpaid']==(pay>'2026-07-30'),'ASML_MAPPING')
        observed=[e for e in inventory if e['ticker']=='ASML' and e['kind']=='dividends' and e['date']==ex]
        require(observed and row['observed_provider_events']==observed and all(F(e['provider_payload']['amount'])==F(raw) for e in observed),'ASML_ORIGINAL_ESTIMATE_PRESERVED')
        require(all(ref in artifact['source_hashes'] for ref in row['source_references']),'ASML_SOURCE_PINS')
        require(not any((e['security_id'],e['ex_date'])==(SID,ex) for e in original_events),'ASML_DUPLICATE')
    for receipt in base.read(ROOT/(prefix+'jpm_final_pdf_receipts.json')):
        body=(ROOT/receipt['path']).read_bytes()
        require(receipt['status']==200 and body.startswith(b'%PDF') and sha256(body).hexdigest()==receipt['sha256']==artifact['source_hashes'][receipt['path']],'ASML_FINAL_PDF_PIN')
    return deepcopy(artifact['dividend_events'])

def check_july_unpaid(book):
    event_id='asml-final-gross:'+SID+':2026-07-28';state=book['dividend_ledger']
    require(book['daily_ledger'][-1]['date']=='2026-07-30','FIXED_END_DATE')
    record=state['events'][event_id]
    pre=next(x for x in book['daily_ledger'] if x['date']=='2026-07-27');quantity=pre['shares'].get(SID,0)
    require(record['opening_quantity']==quantity and F(record['gross'])==F(record['net'])==quantity*F('2.137748') and record['event']['payment_date']=='2026-08-05','ASML_JULY_ACCRUAL')
    require(not any(p['event_id']==event_id for p in state['payments'].values()),'ASML_EARLY_CASH_FORBIDDEN')
    unpaid=sum((F(r['net']) for key,r in state['events'].items() if not any(p['event_id']==key for p in state['payments'].values())),F(0))
    require(F(state['receivable'])==unpaid==F(book['daily_ledger'][-1]['dividend_receivable']),'ASML_RECEIVABLE_TOTAL')
    return dict(july_opening_quantity=quantity,july_gross_receivable=str(quantity*F('2.137748')),july_cash_paid='0')

def validate_resume(directory):
    result=previous.validate_resume(directory,freeze_path=FREEZE,schema='DOWNSIDE_MAX10_RESUME_EXECUTION_V8',parent_rows=563,parent_budget=dict(new=28,reused=0,replayed=27),additional=[(prior.ARTIFACT,prior.DIGEST,prior.validate_pairs),(ARTIFACT,DIGEST,validate_asml_pairs)],absence_origin='tmp/downside_max10_20261105_late_v5')
    check_july_unpaid(base.read(directory/'book.json',True))
    return result

def run(output):
    namespace=dict(previous.chain.__dict__);namespace.update(validate_resume=validate_resume,__file__=__file__)
    exec(compile(inspect.getsource(previous.chain.run),'<independent-downside-v8-audit>','exec'),namespace);namespace['run'](output)
    path=ROOT/output/'independent_review.json';report=base.read(path)
    report['resume_review'].update(parent_rows_checked=563,azn_events_checked=3,ctsh_events_checked=10,lrcx_new_events_checked=2,lrcx_existing_events_checked=2,insm_absence_sessions_checked=647,insm_financial_events_added=0,goog_kdp_events_checked=4,asml_events_checked=2)
    artifact=base.read(ROOT/ARTIFACT);report['asml_cutoff_review']=check_july_unpaid(base.read(ROOT/output/'book.json',True));report['asml_timing_limitation']=artifact['timing_limitation'];report['asml_decision_dependency_review']=artifact['decision_dependency_review']
    report['insm_limitations']=base.read(ROOT/previous.INSM_PATH)['limitations']
    modules=[prior,previous,previous.chain,previous.prior,previous.prior.prior]
    paths=[Path(m.__file__) for m in modules]+[ROOT/FREEZE,ROOT/ARTIFACT,ROOT/prior.ARTIFACT,ROOT/previous.INSM_PATH,ROOT/previous.prior.LRCX_PATH,ROOT/previous.prior.prior.AZN_PATH,ROOT/previous.prior.prior.CTSH_PATH]
    for p in paths:report['source_hashes'][p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest()
    path.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
