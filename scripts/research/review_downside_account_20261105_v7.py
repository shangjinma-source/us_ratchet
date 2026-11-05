"""v7 independent audit configuration; retains v6 absence and financial checks."""
import argparse,inspect,json
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from scripts.research import review_downside_account_20261105_v6 as previous
ROOT=previous.ROOT;base=previous.base;require=previous.require
FREEZE='research_contracts/downside_max10_resume_v7_20261105/freeze.json'
ARTIFACT='tmp/goog_kdp_dividend_evidence_20261105/supplement.json'
DIGEST='87f45c2209a340bee43d4d3222e06d1b2f1d7daefdfccd320e7c6803aab4ae13'

def validate_pairs(artifact,original_events,inventory):
    require(artifact['status']=='REVIEWED_FOUR_GOOG_KDP_REMAINING_DIVIDENDS','NEW_DIVIDEND_STATUS')
    table=[('GOOG','security:0001652044:02079K107','2026-03-09','2026-03-16','21/100'),('GOOG','security:0001652044:02079K107','2026-06-08','2026-06-15','11/50'),('KDP','security:0001418135:49271V100','2026-03-27','2026-04-10','23/100'),('KDP','security:0001418135:49271V100','2026-06-26','2026-07-10','23/100')]
    require(len(artifact['review_rows'])==len(artifact['dividend_events'])==4,'FOUR_COMPLETE')
    for row,event,(ticker,sid,ex,pay,amount) in zip(artifact['review_rows'],artifact['dividend_events'],table):
        require(row['security_id']==event['security_id']==sid and row['ex_date']==event['ex_date']==ex and row['payment_date']==event['payment_date']==pay,'FIXED_SID_DATES')
        require(row['nominal_unit']==('GOOG_CLASS_C_COMMON' if ticker=='GOOG' else 'KDP_COMMON'),'CLASS_C_OR_COMMON_REQUIRED')
        require(row['status']=='REVIEWED_ORDINARY_CASH_DIVIDEND' and F(row['amount_per_share'])==F(event['amount_per_share'])==F(amount) and row['currency']==event['currency']=='USD' and F(event['withholding_rate'])==0,'FIXED_NOMINAL_AMOUNT')
        observed=[e for e in inventory if e['ticker']==ticker and e['kind']=='dividends' and e['date']==ex]
        require(observed and row['observed_provider_events']==observed and all(F(e['provider_payload']['amount'])==F(amount) for e in observed),'EXACT_PROVIDER')
        require(all(ref in artifact['source_hashes'] for ref in row['source_references']),'EVIDENCE_PINS')
        require(not any((e['security_id'],e['ex_date'])==(sid,ex) for e in original_events),'DUPLICATE_EVENT')
    return deepcopy(artifact['dividend_events'])

def validate_resume(directory):
    return previous.validate_resume(directory,freeze_path=FREEZE,schema='DOWNSIDE_MAX10_RESUME_EXECUTION_V7',parent_rows=541,parent_budget=dict(new=27,reused=0,replayed=25),additional=[(ARTIFACT,DIGEST,validate_pairs)],absence_origin='tmp/downside_max10_20261105_late_v5')

def run(output):
    namespace=dict(previous.chain.__dict__);namespace.update(validate_resume=validate_resume,__file__=__file__)
    exec(compile(inspect.getsource(previous.chain.run),'<independent-downside-v7-audit>','exec'),namespace);namespace['run'](output)
    path=ROOT/output/'independent_review.json';report=base.read(path)
    report['resume_review'].update(parent_rows_checked=541,azn_events_checked=3,ctsh_events_checked=10,lrcx_new_events_checked=2,lrcx_existing_events_checked=2,insm_absence_sessions_checked=647,insm_financial_events_added=0,goog_kdp_events_checked=4)
    report['insm_limitations']=base.read(ROOT/previous.INSM_PATH)['limitations']
    for p in [Path(previous.__file__),Path(previous.chain.__file__),Path(previous.prior.__file__),Path(previous.prior.prior.__file__),ROOT/FREEZE,ROOT/ARTIFACT,ROOT/previous.INSM_PATH,ROOT/previous.prior.LRCX_PATH,ROOT/previous.prior.prior.AZN_PATH,ROOT/previous.prior.prior.CTSH_PATH]:
        report['source_hashes'][p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest()
    path.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
