"""Independent one-parent max10 audit. Reuses v1 arithmetic, never its runner."""
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

PARENT_DAYS={'2023-12-29','2024-01-31'}
META_PATH='tmp/meta_dividend_evidence_20261105/supplement.json'
META_SHA='3781f42104301307194fa91d82a9db9696f0c1e2a5d7c2f47ca240c438492413'
require=base.require


def check_pins(pins,root=ROOT):
    for name,h in pins.items():
        p=(root/name).resolve()
        require(p.is_relative_to(root.resolve()) and sha256(p.read_bytes()).hexdigest()==h,'PIN_CHANGED:'+name)


def pin_owner(day,parent_pins,new_pins,replayed_days):
    return parent_pins if day in replayed_days else new_pins


def validate_meta_pairs(artifact,original_events,inventory):
    require(artifact['status']=='REVIEWED_BOUNDED_META_ORDINARY_DIVIDENDS','META_STATUS')
    rows=artifact['review_rows'];events=artifact['dividend_events'];mapping=artifact['mapping']
    require(len(rows)==len(events)==len(mapping)==10,'META_TEN_COMPLETE')
    seen=set();sid='security:0001326801:30303M102'
    for row,event,official in zip(rows,events,mapping):
        key=(sid,event['ex_date'])
        require(key not in seen,'META_DUPLICATE');seen.add(key)
        require(row['security_id']==event['security_id']==sid,'META_SID')
        require(row['ex_date']==event['ex_date']==official['ex_date'] and
            row['payment_date']==event['payment_date']==official['payment_date']>=event['ex_date'],'META_DATES')
        require(F(row['amount_per_share'])==F(event['amount_per_share'])==F(official['amount_per_share'])>0
            and row['currency']==event['currency']=='USD' and F(event['withholding_rate'])==0,'META_NOMINAL_AMOUNT')
        require(not any((e['security_id'],e['ex_date'])==key for e in original_events),'META_ALREADY_PRESENT')
        observed=[e for e in inventory if e['ticker']=='META' and e['kind']=='dividends' and e['date']==event['ex_date']]
        require(observed and row['observed_provider_events']==observed,'META_SOURCE_INVENTORY')
        require(all(F(e['provider_payload']['amount'])==F(event['amount_per_share']) for e in observed),'META_PROVIDER_AMOUNT')
        require(all(ref in artifact['source_hashes'] for ref in row['source_references']),'META_EVIDENCE_PINS')
    return deepcopy(events)


def validate_resume(directory):
    contract=base.read(directory/'contract.json',True)
    require(contract['window']=='2024_2026','V2_LATE_ONLY')
    check_pins(contract['source_hashes']);check_pins(contract['parent_file_hashes'])
    parent=ROOT/contract['parent_output']
    expected={str((parent/n).relative_to(ROOT)).replace('\\','/') for n in ['contract.json','summary.json','book.json',
        *[day+suffix for day in sorted(PARENT_DAYS) for suffix in ('.selection.json','.sidecar.json')]]}
    require(set(contract['parent_file_hashes'])==expected,'PARENT_ARTIFACT_DOMAIN')
    old=base.read(parent/'contract.json',True);summary=base.read(parent/'summary.json',True);oldbook=base.read(parent/'book.json',True)
    check_pins(old['source_hashes'])
    require(old['window']=='2024_2026' and summary['status']==oldbook['status']=='BLOCKED' and
        summary['reason']=='ORDER_PROVIDER_NOT_READY' and len(oldbook['daily_ledger'])==21,'PARENT_FIXED_BLOCK')
    require(oldbook['provider_audit'][-1]['reason']['detail']=='BRANCH_ACTION_EXPOSURE_NOT_ADMITTED:2024-01-31','PARENT_ACTION_BLOCK')
    require(summary['searches']==contract['inherited_searches']=={'new':2,'reused':0} and
        summary['elapsed_seconds']==contract['inherited_seconds'] and 0<=summary['elapsed_seconds']<10800,'INHERITED_BUDGET')
    for key in ('candidate','max_holdings','initial_cash','fee_bps','slippage_bps','start','end','maximum_new_searches','seconds','monthly_seconds','serialization_policy'):
        require(old[key]==contract[key],'PARENT_RULES:'+key)
    for day in PARENT_DAYS:
        for suffix in ('.selection.json','.sidecar.json'):
            require(base.read(parent/(day+suffix),True)==base.read(directory/(day+suffix),True),'REUSED_RECORD_CHANGED')
        side=base.read(directory/(day+'.sidecar.json'),True)
        require(side['evidence_binding']['research_source_hashes']==old['source_hashes'],'REUSED_PIN_OWNER')
    book=base.read(directory/'book.json',True)
    require(book['status']=='COMPLETE' and book['daily_ledger'][:21]==oldbook['daily_ledger'],'PARENT_PREFIX_EXACT')
    boundary=base.read(directory/'parent_prefix_boundary.json',True);end=base.read(directory/'parent_prefix_review.json',True)
    require(boundary['status']=='PASS_BEFORE_NEW_SEARCH' and boundary['rows']==21 and
        boundary['searches']['new']==2 and end==dict(status='PASS',daily_ledger_rows=21),'PREFIX_BOUNDARY')
    final=base.read(directory/'summary.json',True)
    require(final['status']=='COMPLETE' and final['completed_sessions']==final['required_sessions']==646,'FULL_SUMMARY')
    require(final['searches']==dict(new=31,reused=0,replayed=2) and
        contract['inherited_seconds']<=final['elapsed_seconds']<=10800,'CUMULATIVE_BUDGET')
    require(contract['source_hashes'].get(META_PATH)==META_SHA and sha256((ROOT/META_PATH).read_bytes()).hexdigest()==META_SHA,'META_APPROVED_ARTIFACT')
    artifact=base.read(ROOT/META_PATH);check_pins(artifact['source_hashes'])
    require(base.read(directory/'additional_execution_evidence.json',True)==artifact,'META_SAVED_ARTIFACT')
    initial=base.read(ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json')
    original_events=list(initial['dividend_events'])
    original_events+=base.read(ROOT/'tmp/equal_four_20261105/source_review/admitted_supplement.json')['dividend_events']['2024_2026']
    original_events+=base.read(directory/'bounded_execution_evidence.json',True)['events']
    events=validate_meta_pairs(artifact,original_events,initial['provider_event_inventory'])
    return contract,old,events,dict(parent_output=contract['parent_output'],parent_rows_checked=21,
        reused_months=sorted(PARENT_DAYS),inherited_seconds=contract['inherited_seconds'],final_budget=final['searches'],
        cumulative_elapsed_seconds=final['elapsed_seconds'],meta_events_checked=10)


def run(output):
    directory=ROOT/output
    contract,parent,events,lineage=validate_resume(directory)
    input_path=(ROOT/'tmp/old_continuous_baseline_20261026_v9/execution_inputs.json').resolve()
    def read(path,encoded=False):
        value=base.read(path,encoded)
        if Path(path).resolve()==input_path:
            value=deepcopy(value);value['dividend_events'].extend(deepcopy(events))
        return value
    def review_selection(selected,side,returns,reference,pins):
        require(pins==contract['source_hashes'],'CURRENT_RUN_PINS')
        day=selected['raw_selection']['decision_date']
        owner=pin_owner(day,parent['source_hashes'],pins,PARENT_DAYS)
        return base.review_selection(selected,side,returns,reference,owner)
    # Execute the unchanged v1 audit function in an isolated audit namespace;
    # only input assembly and expected sidecar pin owner differ for resume.
    namespace=dict(base.__dict__);namespace.update(read=read,review_selection=review_selection,__file__=__file__)
    exec(compile(inspect.getsource(base.run),'<independent-downside-v2-audit>','exec'),namespace)
    namespace['run'](output)
    path=directory/'independent_review.json';report=json.loads(path.read_bytes())
    report['status']='INDEPENDENT_DOWNSIDE_MAX10_RESUME_FINANCE_PASS';report['resume_review']=lineage
    paths=[Path(base.__file__),directory/'summary.json',directory/'additional_execution_evidence.json',
        directory/'parent_prefix_boundary.json',directory/'parent_prefix_review.json',ROOT/META_PATH]
    report['source_hashes'].update({p.relative_to(ROOT).as_posix():sha256(p.read_bytes()).hexdigest() for p in paths})
    report['parent_file_hashes']=contract['parent_file_hashes']
    path.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(status=report['status'],resume=lineage)))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);run(parser.parse_args().output)
