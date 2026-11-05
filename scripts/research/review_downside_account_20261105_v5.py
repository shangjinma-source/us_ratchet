"""Configuration-only independent v5 audit; no execution runner imports."""
import argparse
import inspect
import json
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from scripts.research import review_downside_account_20261105_v4 as prior
chain=prior.chain;base=prior.base;ROOT=prior.ROOT;require=prior.require
FREEZE='research_contracts/downside_max10_resume_v5_20261105/freeze.json'
LRCX_PATH='tmp/lrcx_dividend_evidence_20261105/supplement.json'
LRCX_SHA='989942d872e7c771a0c363b5b2ad9e293233e1b8bf3b4aba20c0a67adf19f58c'

def validate_lrcx_pairs(artifact,original_events,inventory):
    require(artifact['status']=='REVIEWED_BOUNDED_LRCX_ORDINARY_DIVIDENDS','LRCX_STATUS')
    sid='security:0000707549:512807306';rows=artifact['review_rows'];events=artifact['dividend_events']
    require(len(rows)==len(events)==2,'LRCX_TWO_ONLY')
    for ex,pay in [('2025-12-03','2026-01-07'),('2026-03-04','2026-04-08')]:
        old=[e for e in original_events if e['security_id']==sid and e['ex_date']==ex]
        require(len(old)==1 and old[0]['payment_date']==pay and F(old[0]['amount_per_share'])==F('13/50'),'LRCX_EXISTING_BOUND_PAIR')
    for row,event,(ex,pay) in zip(rows,events,[('2025-09-24','2025-10-15'),('2026-06-17','2026-07-08')]):
        require(row['security_id']==event['security_id']==sid and row['ex_date']==event['ex_date']==ex and row['payment_date']==event['payment_date']==pay,'LRCX_DATES_SID')
        require(row['status']=='REVIEWED_ORDINARY_CASH_DIVIDEND' and row['nominal_unit']=='LRCX_POST_OCTOBER_2024_SPLIT_COMMON_SHARE','LRCX_SPLIT_UNIT')
        require(F(row['amount_per_share'])==F(event['amount_per_share'])==F('13/50') and row['currency']==event['currency']=='USD' and F(event['withholding_rate'])==0,'LRCX_AMOUNT')
        observed=[e for e in inventory if e['ticker']=='LRCX' and e['kind']=='dividends' and e['date']==ex]
        require(observed and row['observed_provider_events']==observed and all(F(e['provider_payload']['amount'])==F('13/50') for e in observed),'LRCX_PROVIDER')
        require(all(ref in artifact['source_hashes'] for ref in row['source_references']),'LRCX_EVIDENCE_PINS')
        require(not any((e['security_id'],e['ex_date'])==(sid,ex) for e in original_events),'LRCX_DUPLICATE')
    return deepcopy(events)

def validate_resume(directory):
    freeze=base.read(ROOT/FREEZE);chain.v2.check_pins(freeze['source_hashes'])
    require(freeze['schema']=='DOWNSIDE_MAX10_RESUME_EXECUTION_V5','V5_FREEZE')
    extra=[(prior.AZN_PATH,prior.AZN_SHA,prior.validate_azn_pairs),(prior.CTSH_PATH,prior.CTSH_SHA,prior.validate_ctsh_pairs),(LRCX_PATH,LRCX_SHA,validate_lrcx_pairs)]
    require(freeze['additional_execution_artifacts']==[chain.v2.META_PATH,chain.CEG_PATH,*[x[0] for x in extra]],'V5_ARTIFACT_ORDER')
    require(all(freeze['source_hashes'][p]==h for p,h,_ in extra),'APPROVED_ARTIFACT_HASHES')
    result=chain.validate_resume(directory,parent_rows=417,parent_budget=dict(new=21,reused=0,replayed=8),additional=extra)
    require(result[0]['parent_output']==freeze['parent_output'] and result[0]['inherited_seconds']==freeze['inherited_seconds'],'V5_FREEZE_PARENT')
    return result

def run(output):
    namespace=dict(chain.__dict__);namespace.update(validate_resume=validate_resume,__file__=__file__)
    exec(compile(inspect.getsource(chain.run),'<independent-downside-v5-audit>','exec'),namespace);namespace['run'](output)
    path=ROOT/output/'independent_review.json';report=base.read(path)
    report['resume_review'].update(parent_rows_checked=417,azn_events_checked=3,ctsh_events_checked=10,lrcx_new_events_checked=2,lrcx_existing_events_checked=2)
    for p in [Path(chain.__file__),Path(prior.__file__),ROOT/FREEZE,ROOT/prior.AZN_PATH,ROOT/prior.CTSH_PATH,ROOT/LRCX_PATH]:
        report['source_hashes'][p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest()
    path.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
