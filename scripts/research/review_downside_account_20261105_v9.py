"""Final 31-selection replay audit and GEHC post-cutoff receivable check."""
import argparse, inspect, json
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from scripts.research import review_downside_account_20261105_v8 as prior
previous=prior.previous; ROOT=prior.ROOT; base=prior.base; require=prior.require
FREEZE='research_contracts/downside_max10_resume_v9_20261105/freeze.json'
ARTIFACT='tmp/gehc_dividend_evidence_20261105/supplement.json'
DIGEST='92ad6d5b69cac38b33634fae65058291bbb9d16f40e35e37bf44f32229f6fd1c'
SID='security:0001932393:36266G107'

def validate_gehc_pairs(artifact, original_events, inventory):
    require(artifact['status']=='REVIEWED_ONE_GEHC_REMAINING_DIVIDEND','GEHC_STATUS')
    require(len(artifact['review_rows'])==len(artifact['dividend_events'])==1,'GEHC_ONE_ONLY')
    row=artifact['review_rows'][0]; event=artifact['dividend_events'][0]
    for item in (row,event):
        require(item['security_id']==SID and item['ex_date']=='2026-07-24' and item['payment_date']=='2026-08-14','GEHC_FIXED_DATES_SID')
        require(item['currency']=='USD' and F(item['amount_per_share'])==F(7,200),'GEHC_NOMINAL_AMOUNT')
    require(row['nominal_unit']=='GEHC_COMMON' and F(event['withholding_rate'])==0,'GEHC_GROSS_COMMON_UNIT')
    require(event['event_id']=='gehc-gross:'+SID+':2026-07-24','GEHC_EVENT_ID')
    observed=[x for x in inventory if x['ticker']=='GEHC' and x['kind']=='dividends' and '2026-06-30'<x['date']<='2026-07-30']
    require(len(observed)==2 and row['observed_provider_events']==observed and all(x['date']=='2026-07-24' and F(x['provider_payload']['amount'])==F(7,200) for x in observed),'GEHC_REMAINING_INVENTORY')
    observation=base.read(ROOT/'tmp/gehc_dividend_evidence_20261105/official_observations.json')['rows']
    require(len(observation)==1 and observation[0]['security_id']==SID and observation[0]['payment_date']=='2026-08-14' and F(observation[0]['amount_per_share'])==F(7,200) and observation[0]['url']==row['official_url'],'GEHC_ISSUER_OBSERVATION')
    require(all(p in artifact['source_hashes'] for p in row['source_references']),'GEHC_SOURCE_PINS')
    require(not any(x['security_id']==SID and x['ex_date']=='2026-07-24' for x in original_events),'GEHC_DUPLICATE')
    return deepcopy(artifact['dividend_events'])

def check_gehc_unpaid(book):
    require(book['daily_ledger'][-1]['date']=='2026-07-30','GEHC_FIXED_END')
    state=book['dividend_ledger']; event_id='gehc-gross:'+SID+':2026-07-24'; record=state['events'][event_id]
    quantity=next(x for x in book['daily_ledger'] if x['date']=='2026-07-23')['shares'].get(SID,0)
    require(record['opening_quantity']==quantity and F(record['gross'])==F(record['net'])==quantity*F(7,200) and record['event']['payment_date']=='2026-08-14','GEHC_ACCRUAL')
    require(not any(p['event_id']==event_id for p in state['payments'].values()),'GEHC_EARLY_CASH_FORBIDDEN')
    unpaid=sum((F(r['net']) for k,r in state['events'].items() if not any(p['event_id']==k for p in state['payments'].values())),F(0))
    require(F(state['receivable'])==unpaid==F(book['daily_ledger'][-1]['dividend_receivable']),'GEHC_RECEIVABLE_TOTAL')
    return dict(opening_quantity=quantity,gross_receivable=str(quantity*F(7,200)),cash_paid='0',payment_date='2026-08-14')

def check_no_new_searches(parent, summary, selection_days):
    require(len(parent['records'])==31 and set(selection_days)==set(parent['records']),'V9_ALL_SELECTIONS_INHERITED')
    require(summary['searches']==dict(new=31,reused=0,replayed=31),'V9_NO_NEW_SEARCHES')

def validate_resume(directory):
    result=previous.validate_resume(directory,freeze_path=FREEZE,schema='DOWNSIDE_MAX10_RESUME_EXECUTION_V9',parent_rows=625,parent_budget=dict(new=31,reused=0,replayed=28),additional=[(prior.prior.ARTIFACT,prior.prior.DIGEST,prior.prior.validate_pairs),(prior.ARTIFACT,prior.DIGEST,prior.validate_asml_pairs),(ARTIFACT,DIGEST,validate_gehc_pairs)],absence_origin='tmp/downside_max10_20261105_late_v5')
    check_no_new_searches(result[1],result[3],[p.name.removesuffix('.selection.json') for p in directory.glob('*.selection.json')])
    book=base.read(directory/'book.json',True); prior.check_july_unpaid(book); check_gehc_unpaid(book)
    return result

def run(output):
    namespace=dict(previous.chain.__dict__); namespace.update(validate_resume=validate_resume,__file__=__file__)
    exec(compile(inspect.getsource(previous.chain.run),'<independent-downside-v9-audit>','exec'),namespace); namespace['run'](output)
    path=ROOT/output/'independent_review.json'; report=base.read(path); book=base.read(ROOT/output/'book.json',True)
    report['resume_review'].update(parent_rows_checked=625,azn_events_checked=3,ctsh_events_checked=10,lrcx_new_events_checked=2,lrcx_existing_events_checked=2,insm_absence_sessions_checked=647,insm_financial_events_added=0,goog_kdp_events_checked=4,asml_events_checked=2,gehc_events_checked=1,new_searches_this_resume=0)
    artifact=base.read(ROOT/prior.ARTIFACT)
    report.update(asml_cutoff_review=prior.check_july_unpaid(book),gehc_cutoff_review=check_gehc_unpaid(book),asml_timing_limitation=artifact['timing_limitation'],asml_decision_dependency_review=artifact['decision_dependency_review'],insm_limitations=base.read(ROOT/previous.INSM_PATH)['limitations'])
    modules=[prior,prior.prior,previous,previous.chain,previous.prior,previous.prior.prior]
    paths=[Path(m.__file__) for m in modules]+[ROOT/FREEZE,ROOT/ARTIFACT,ROOT/prior.ARTIFACT,ROOT/prior.prior.ARTIFACT,ROOT/previous.INSM_PATH,ROOT/previous.prior.LRCX_PATH,ROOT/previous.prior.prior.AZN_PATH,ROOT/previous.prior.prior.CTSH_PATH]
    for p in paths: report['source_hashes'][p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest()
    path.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('--output',required=True); run(parser.parse_args().output)
