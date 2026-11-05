"""Small v4 audit configuration, using independent v3 arithmetic and ancestry."""
import argparse
import inspect
import json
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
from scripts.research import review_downside_account_20261105_v3 as chain
ROOT=chain.ROOT;require=chain.require;base=chain.base
AZN_PATH='tmp/azn_ads_dividends_20261105/supplement.json'
AZN_SHA='cb742ebfba7b736fd5925cb44279c3f83d4aabada888011ce2c5c9b84de23882'
CTSH_PATH='tmp/ctsh_dividend_evidence_20261105/supplement.json'
CTSH_SHA='17c62e66cb2a897ab4949f0e7746e0bbab4a7348f7f8a8a2979aed7cea17b95d'
# CTSH binding is loaded only from the explicitly approved freeze, never latest.
FREEZE='research_contracts/downside_max10_resume_v4_20261105/freeze.json'

def validate_azn_pairs(artifact,original_events,inventory):
    require(artifact['status']=='REVIEWED_THREE_PRECONVERSION_AZN_ADS_DIVIDENDS','AZN_STATUS')
    exact={'2024-08-09':('1','1/2','2024-09-09'),'2025-02-21':('21/10','21/20','2025-03-24'),'2025-08-08':('103/100','103/200','2025-09-08')}
    rows=artifact['review_rows'];events=artifact['dividend_events'];sid='security:0000901832:046353108'
    require(len(rows)==len(events)==3,'AZN_THREE_ONLY');seen=set()
    for row,event in zip(rows,events):
        ex=event['ex_date'];require(ex in exact and ex not in seen,'AZN_DATE_DOMAIN');seen.add(ex)
        ordinary,ads,pay=exact[ex]
        require(row['security_id']==event['security_id']==sid and row['ex_date']==ex and row['payment_date']==event['payment_date']==pay,'AZN_FIELDS')
        require(F(row['amount_per_share'])==F(event['amount_per_share'])==F(ads)==F(ordinary)/2 and F(row['ordinary_amount'])==F(ordinary),'AZN_ADS_HALF_UNIT')
        require(row['currency']==event['currency']=='USD' and F(event['withholding_rate'])==0,'AZN_CURRENCY')
        require(row['nominal_unit']=='HISTORICAL_US_ADS_REPRESENTING_HALF_ORDINARY','AZN_UNIT_LABEL')
        observed=[e for e in inventory if e['ticker']=='AZN' and e['kind']=='dividends' and e['date']==ex]
        require(observed and row['observed_provider_events']==observed and all(F(e['provider_payload']['amount'])==F(ordinary) for e in observed),'AZN_PROVIDER_ORDINARY')
        require(all(ref in artifact['source_hashes'] for ref in row['source_references']),'AZN_SOURCE_PINS')
        require(not any((e['security_id'],e['ex_date'])==(sid,ex) for e in original_events),'AZN_DUPLICATE')
    require({x['date'] for x in artifact['excluded']}=={'2026-02-02','2026-02-19'},'AZN_CONVERSION_EXCLUDED')
    return deepcopy(events)

def validate_ctsh_pairs(artifact,original_events,inventory):
    require(artifact['status']=='REVIEWED_BOUNDED_CTSH_ORDINARY_DIVIDENDS','CTSH_STATUS')
    dates=[('2024-02-16','2024-02-28'),('2024-05-17','2024-05-29'),('2024-08-20','2024-08-28'),('2024-11-19','2024-11-27'),('2025-02-18','2025-02-26'),('2025-05-19','2025-05-28'),('2025-08-18','2025-08-26'),('2025-11-18','2025-11-26'),('2026-02-18','2026-02-26'),('2026-05-18','2026-05-27')]
    rows=artifact['review_rows'];events=artifact['dividend_events'];sid='security:0001058290:192446102'
    require(len(rows)==len(events)==10,'CTSH_TEN_COMPLETE')
    for row,event,(ex,pay) in zip(rows,events,dates):
        amount=F({'2024':'3/10','2025':'31/100','2026':'33/100'}[ex[:4]])
        require(row['security_id']==event['security_id']==sid and row['ex_date']==event['ex_date']==ex and row['payment_date']==event['payment_date']==pay,'CTSH_DATES_SID')
        require(row['status']=='REVIEWED_ORDINARY_CASH_DIVIDEND' and row['nominal_unit']=='CTSH_CLASS_A_USD_PER_COMMON_SHARE','CTSH_NOMINAL_UNIT')
        require(F(row['amount_per_share'])==F(event['amount_per_share'])==amount and row['currency']==event['currency']=='USD' and F(event['withholding_rate'])==0,'CTSH_AMOUNT')
        observed=[e for e in inventory if e['ticker']=='CTSH' and e['kind']=='dividends' and e['date']==ex]
        require(observed and row['observed_provider_events']==observed and all(F(e['provider_payload']['amount'])==amount for e in observed),'CTSH_PROVIDER')
        require(all(ref in artifact['source_hashes'] for ref in row['source_references']),'CTSH_SOURCE_PINS')
        require(not any((e['security_id'],e['ex_date'])==(sid,ex) for e in original_events),'CTSH_DUPLICATE')
    return deepcopy(events)

def validate_resume(directory):
    freeze=base.read(ROOT/FREEZE);chain.v2.check_pins(freeze['source_hashes'])
    require(freeze['schema']=='DOWNSIDE_MAX10_RESUME_EXECUTION_V4','V4_FREEZE')
    names=freeze['additional_execution_artifacts']
    require(names==[chain.v2.META_PATH,chain.CEG_PATH,AZN_PATH,CTSH_PATH],'V4_ARTIFACT_ORDER')
    require(freeze['source_hashes'][AZN_PATH]==AZN_SHA,'AZN_APPROVED_HASH')
    require(freeze['source_hashes'][CTSH_PATH]==CTSH_SHA,'CTSH_APPROVED_HASH')
    result=chain.validate_resume(directory,parent_rows=146,parent_budget=dict(new=8,reused=0,replayed=5),additional=[(AZN_PATH,AZN_SHA,validate_azn_pairs),(names[3],freeze['source_hashes'][names[3]],validate_ctsh_pairs)])
    require(result[0]['parent_output']==freeze['parent_output'] and result[0]['inherited_seconds']==freeze['inherited_seconds'],'V4_FREEZE_PARENT')
    return result

def run(output):
    namespace=dict(chain.__dict__);namespace.update(validate_resume=validate_resume,__file__=__file__)
    exec(compile(inspect.getsource(chain.run),'<independent-downside-v4-audit>','exec'),namespace);namespace['run'](output)
    path=ROOT/output/'independent_review.json';report=base.read(path)
    report['resume_review'].update(parent_rows_checked=146,azn_events_checked=3,ctsh_events_checked=10)
    for p in [Path(chain.__file__),ROOT/FREEZE,ROOT/AZN_PATH,ROOT/CTSH_PATH]:report['source_hashes'][p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest()
    path.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
