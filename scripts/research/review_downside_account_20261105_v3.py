"""Independent multi-generation audit; never imports candidate resume helpers."""
import argparse
import inspect
import json
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.research import review_downside_account_20261105 as base
from scripts.research import review_downside_account_20261105_v2 as v2
require=base.require
CEG_PATH='tmp/ceg_dividend_evidence_20261105/supplement.json'
CEG_SHA='ab93b864a6357de136804f86c680692cc4a6575dbd7fb7872c3302e4bd98ee77'

def ancestor(directory,seen=()):
    directory=directory.resolve()
    require(directory.is_relative_to(ROOT/'tmp') and directory not in seen and len(seen)<8,'ANCESTOR_PATH')
    hashes={}
    def read(name):
        p=directory/name;hashes[p.relative_to(ROOT).as_posix()]=sha256(p.read_bytes()).hexdigest()
        return base.read(p,True)
    contract=read('contract.json');summary=read('summary.json');book=read('book.json')
    v2.check_pins(contract['source_hashes'])
    require(contract['window']=='2024_2026' and summary['status']==book['status']=='BLOCKED','ANCESTOR_BLOCKED')
    require(summary['reason']=='ORDER_PROVIDER_NOT_READY' and book['provider_audit'][-1]['reason']['detail'].startswith('BRANCH_ACTION_EXPOSURE_NOT_ADMITTED:'),'ANCESTOR_ACTION_GATE')
    require(len(book['daily_ledger'])==summary['completed_sessions'] and summary['searches']['reused']==0 and 0<=summary['elapsed_seconds']<10800,'ANCESTOR_PROGRESS')
    inherited={};old_new=0
    if contract.get('parent_output'):
        older=ancestor(ROOT/contract['parent_output'],seen+(directory,))
        require(contract['parent_file_hashes']==older['hashes'],'ANCESTOR_RECEIPTS')
        require(contract['inherited_seconds']==older['summary']['elapsed_seconds']<=summary['elapsed_seconds'] and contract['inherited_searches']==older['summary']['searches'],'ANCESTOR_BUDGET')
        require(book['daily_ledger'][:len(older['book']['daily_ledger'])]==older['book']['daily_ledger'],'ANCESTOR_PREFIX')
        inherited=older['records'];old_new=older['summary']['searches']['new'];hashes.update(older['hashes'])
    records={}
    for p in sorted(directory.glob('*.selection.json')):
        day=p.name.removesuffix('.selection.json');selection=read(p.name);side=read(day+'.sidecar.json')
        require(selection['arguments']['decision_date']==selection['raw_selection']['decision_date']==day,'ANCESTOR_DAY')
        require(base.evidence_hash({k:v for k,v in side.items() if k!='integrity_sha256'})==side['integrity_sha256']==selection['raw_selection']['downside_sidecar_sha256'],'ANCESTOR_INTEGRITY')
        if day in inherited:
            old=inherited[day];require(selection==old['selection'] and side==old['side'],'ANCESTOR_RECORD_CHANGED');pins=old['pins']
        else:pins=contract['source_hashes']
        require(side['evidence_binding']['research_source_hashes']==pins,'ANCESTOR_SOURCE_OWNER')
        records[day]=dict(selection=selection,side=side,pins=pins)
    require(set(inherited)<=set(records) and summary['searches']['new']==old_new+len(set(records)-set(inherited))<=31,'ANCESTOR_SEARCH_COUNT')
    return dict(contract=contract,summary=summary,book=book,hashes=hashes,records=records)

def validate_ceg_pairs(artifact,original_events,inventory):
    require(artifact['status']=='REVIEWED_BOUNDED_CEG_ORDINARY_DIVIDENDS','CEG_STATUS')
    rows=artifact['review_rows'];events=artifact['dividend_events'];mapping=artifact['mapping']
    require(len(rows)==len(events)==len(mapping)==10,'CEG_TEN_COMPLETE')
    sid='security:0001868275:21037T109';seen=set()
    for row,event,official in zip(rows,events,mapping):
        key=(sid,event['ex_date']);require(key not in seen,'CEG_DUPLICATE');seen.add(key)
        year=event['ex_date'][:4];amount,rounded={'2024':('0.3525','0.353'),'2025':('0.3878','0.388'),'2026':('0.4265','0.427')}[year]
        require(row['security_id']==event['security_id']==sid and row['status']=='REVIEWED_ORDINARY_CASH_DIVIDEND','CEG_SID')
        require(row['ex_date']==event['ex_date']==official['ex_date'] and row['payment_date']==event['payment_date']==official['payment_date']>=event['ex_date'],'CEG_DATES')
        require(F(row['amount_per_share'])==F(event['amount_per_share'])==F(official['amount_per_share'])==F(amount) and row['currency']==event['currency']=='USD' and F(event['withholding_rate'])==0,'CEG_EXACT_ISSUER_AMOUNT')
        observed=[e for e in inventory if e['ticker']=='CEG' and e['kind']=='dividends' and e['date']==event['ex_date']]
        require(observed and row['observed_provider_events']==observed and all(F(e['provider_payload']['amount'])==F(rounded) for e in observed),'CEG_PROVIDER_ROUNDING')
        require(F(row['provider_amount'])==F(rounded) and row['amount_resolution']=='ISSUER_EXACT_AMOUNT_OVERRIDES_EXPLICIT_PROVIDER_THREE_DECIMAL_ROUNDING','CEG_RESOLUTION')
        require(not any((e['security_id'],e['ex_date'])==key for e in original_events),'CEG_ALREADY_PRESENT')
        require(all(ref in artifact['source_hashes'] for ref in row['source_references']),'CEG_SOURCE_PINS')
    return deepcopy(events)

def validate_resume(directory):
    contract=base.read(directory/'contract.json',True);v2.check_pins(contract['source_hashes'])
    parent=ancestor(ROOT/contract['parent_output'])
    require(contract['parent_file_hashes']==parent['hashes'],'PARENT_RECEIPT_DOMAIN')
    require(len(parent['book']['daily_ledger'])==83 and parent['summary']['searches']==dict(new=5,reused=0,replayed=2),'FIXED_83_PARENT')
    require(contract['inherited_seconds']==parent['summary']['elapsed_seconds'] and contract['inherited_searches']==parent['summary']['searches'],'INHERITED_BUDGET')
    for key in ('window','candidate','max_holdings','initial_cash','fee_bps','slippage_bps','start','end','maximum_new_searches','seconds','monthly_seconds','serialization_policy'):
        require(contract[key]==parent['contract'][key],'PARENT_RULES:'+key)
    for day,record in parent['records'].items():
        require(base.read(directory/(day+'.selection.json'),True)==record['selection'] and base.read(directory/(day+'.sidecar.json'),True)==record['side'],'REPLAY_RECORD')
    book=base.read(directory/'book.json',True);summary=base.read(directory/'summary.json',True)
    require(book['status']==summary['status']=='COMPLETE' and summary['completed_sessions']==summary['required_sessions']==len(book['daily_ledger'])==646,'COMPLETE_REQUIRED')
    require(book['daily_ledger'][:83]==parent['book']['daily_ledger'],'83_PREFIX_EXACT')
    boundary=base.read(directory/'parent_prefix_boundary.json',True);end=base.read(directory/'parent_prefix_review.json',True)
    require(boundary['status']=='PASS_BEFORE_NEW_SEARCH' and boundary['rows']==83 and boundary['searches']['new']==5 and end==dict(status='PASS',daily_ledger_rows=83),'PREFIX_BOUNDARY')
    require(summary['searches']==dict(new=31,reused=0,replayed=5) and contract['inherited_seconds']<=summary['elapsed_seconds']<=10800,'FINAL_CUMULATIVE_BUDGET')
    initial=base.read(ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
    original=list(initial['dividend_events'])+base.read(ROOT/'tmp/equal_four_20261105/source_review/admitted_supplement.json')['dividend_events']['2024_2026']+base.read(directory/'bounded_execution_evidence.json',True)['events']
    saved=base.read(directory/'additional_execution_evidence.json',True);expected=[(v2.META_PATH,v2.META_SHA,v2.validate_meta_pairs),(CEG_PATH,CEG_SHA,validate_ceg_pairs)]
    require([x['path'] for x in saved]==[x[0] for x in expected],'EXACT_ADDITIONAL_ARTIFACTS')
    added=[]
    for item,(name,digest,validator) in zip(saved,expected):
        require(contract['source_hashes'].get(name)==digest==sha256((ROOT/name).read_bytes()).hexdigest(),'APPROVED_ARTIFACT')
        artifact=base.read(ROOT/name);v2.check_pins(artifact['source_hashes']);require(item['artifact']==artifact,'SAVED_ARTIFACT')
        added.extend(validator(artifact,original+added,initial['provider_event_inventory']))
    return contract,parent,added,summary

def run(output):
    directory=ROOT/output;contract,parent,events,summary=validate_resume(directory)
    input_path=(ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').resolve()
    def read(path,encoded=False):
        value=base.read(path,encoded)
        if Path(path).resolve()==input_path:value=deepcopy(value);value['dividend_events'].extend(deepcopy(events))
        return value
    def review_selection(selected,side,returns,reference,pins):
        require(pins==contract['source_hashes'],'CURRENT_PINS');day=selected['raw_selection']['decision_date']
        owner=parent['records'][day]['pins'] if day in parent['records'] else pins
        return base.review_selection(selected,side,returns,reference,owner)
    namespace=dict(base.__dict__);namespace.update(read=read,review_selection=review_selection,__file__=__file__)
    exec(compile(inspect.getsource(base.run),'<independent-downside-v3-audit>','exec'),namespace);namespace['run'](output)
    path=directory/'independent_review.json';report=json.loads(path.read_bytes())
    report['status']='INDEPENDENT_DOWNSIDE_MAX10_CHAIN_FINANCE_PASS'
    report['resume_review']=dict(parent_output=contract['parent_output'],parent_rows_checked=83,reused_months=sorted(parent['records']),cumulative_elapsed_seconds=summary['elapsed_seconds'],final_budget=summary['searches'],meta_events_checked=10,ceg_events_checked=10)
    report['parent_file_hashes']=parent['hashes']
    paths=[Path(base.__file__),Path(v2.__file__),directory/'summary.json',directory/'additional_execution_evidence.json',directory/'parent_prefix_boundary.json',directory/'parent_prefix_review.json',ROOT/v2.META_PATH,ROOT/CEG_PATH]
    report['source_hashes'].update({p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths})
    path.write_text(json.dumps(report,indent=2),encoding='utf8');print(report['status'])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
