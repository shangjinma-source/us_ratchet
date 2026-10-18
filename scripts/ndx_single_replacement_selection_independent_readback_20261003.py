"""Independent saved full-domain ranking, sharing the authenticated byte parser.

Never invokes the selector, evaluator or account. This checks selection, not a
second independent implementation of the preceding evaluation mathematics.
"""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import hashlib
import os
import sys
if __package__ in (None,''):
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts import ndx_single_replacement_selection_20261003 as source

SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PUBLISHER_SHA='d12ed8b502429a9149d8be366a6fb4ad40825b15f86bdb98ca75f8e6a4e31c13'
OUTPUT=source.ROOT/'data/cache/research/single_replacement_selection_independent_readback_20261003_v1'
require=source.require;exact=source.exact;enc=source.enc;sha=source.sha;ref=source.ref


def inspect_selection(c,saved):
    """Independent Fraction reduction; one evaluation at a time, forty winners."""
    original=c['prepared'];d=original['document'];require(sha(enc(d))==original['content_sha256'],'Prepared content')
    require(len(d['cases'])==40 and d['integer_count']==source.TOTAL,'Complete original domain')
    require(c['audit']['full_domain_evaluated'] is True,'No prefix selection')
    rows=[];cursor=0;feasible=infeasible=0
    records=iter(source.stream_records(c))
    for ci,case in enumerate(d['cases']):
        require(type(case['scenario_index']) is int and case['scenario_index']==ci and case['first_global_ordinal']==cursor,'Original case order')
        row={k:case[k] for k in ('scenario_index','scenario_id','pair_count','integer_count','financial_integer_count_before_issuer','structurally_excluded_integer_count')}
        row.update(scenario_identity_sha256=case['identity_sha256'],feasible_count=0,infeasible_count=0,status='NO_FEASIBLE',selected=None);best=None
        for pair in case['pairs']:
            for q in range(1,pair['enumerable_quantity_count']+1):
                r=next(records);task=r['task'];identity=task['identity'];v=r['evaluation']
                require(r['global_ordinal']==cursor and task['scenario_index']==ci and task['pair_index']==pair['pair_index'],'Original task positions')
                require(identity['scenario_identity_sha256']==case['identity_sha256'] and identity['outgoing_security_id']==pair['outgoing_security_id'] and identity['incoming_security_id']==pair['incoming_security_id'] and type(identity['buy_quantity']) is int and identity['buy_quantity']==q and identity['sell_quantity']==pair['sell_quantity'],'Original pair/q scope')
                require(task['task_id']==sha(enc(identity)),'Original numerical identity')
                status=v['status'];require(status in ('FEASIBLE','INFEASIBLE') and v['feasible'] is (status=='FEASIBLE'),'No technical ranking')
                row['feasible_count' if v['feasible'] else 'infeasible_count']+=1
                if v['feasible']:
                    key=(Fraction(v['original_target_stock_l1']),Fraction(v['total_fee_usd']),identity['outgoing_security_id'],identity['incoming_security_id'],q)
                    require(key[0]>=0 and key[1]>=0,'Saved nonnegative ranking coordinates')
                    if best is None or key<best:best=key;row['selected']=deepcopy(r);row['status']='SELECTED_REQUIRES_NEW_SIGNED_PATH'
                cursor+=1
        require(row['feasible_count']+row['infeasible_count']==case['integer_count'],'Case complete denominator')
        feasible+=row['feasible_count'];infeasible+=row['infeasible_count'];rows.append(row)
    sentinel=object();require(next(records,sentinel) is sentinel and cursor==source.TOTAL,'Entire domain and journal EOF')
    p=c['audit']['partition'];require(p['full_integer_count']==p['terminal_count']==cursor and p['unresolved_ordinal'] is None and p['undispatched_count']==0,'Full audit partition')
    exact(p['outcome_counts'],dict(FEASIBLE=feasible,INFEASIBLE=infeasible,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0),'Independent outcome counts')
    selected=sum(r['selected'] is not None for r in rows)
    flags=dict.fromkeys(('source_bytes_authenticated','evaluation_reperformed','account_executed','fit_executed','future_returns_used','cross_family_winner_selected','global_optimality_claimed','point_in_time_verified','full_ndx_certified','promotion_allowed','execution_authorized'),False)
    expected=dict(schema='SINGLE_REPLACEMENT_COMPLETE_DOMAIN_SELECTION_V1',status='COMPLETE_WITHIN_FAMILY_SELECTION_NOT_ACCOUNT_OR_CROSS_FAMILY_WINNER',preparation_reference=c['refs']['preparation'],prepared_content_sha256=original['content_sha256'],readback_reference=c['refs']['execution_audit'],action_contract=d['action_contract'],scope=d['scope'],scenario_count=40,pair_count=d['pair_count'],integer_count=cursor,financial_integer_count_before_issuer=d['financial_integer_count_before_issuer'],structurally_excluded_integer_count=d['structurally_excluded_integer_count'],feasible_count=feasible,infeasible_count=infeasible,selected_case_count=selected,no_feasible_case_count=40-selected,rows=rows,ranking='NOT_SELECTED_FUTURE_ORIGINAL_TARGET_L1_THEN_TOTAL_BILATERAL_FEE_THEN_STABLE_PAIR_Q',stream_consumed_once=True,all_registered_points_consumed=True,selection_basis='SAVED_INDEPENDENTLY_INSPECTED_ORIGINAL_TARGET_STOCK_L1_AND_BILATERAL_FEE',**flags)
    exact(saved,dict(document=expected,content_sha256=sha(enc(expected))),'All saved selection fields independently reconstructed')
    return dict(scenario_count=40,integer_count=cursor,selected_case_count=selected,no_feasible_case_count=40-selected,feasible_count=feasible,infeasible_count=infeasible)


def save(name,value):
    b=enc(value);p=OUTPUT/name
    with p.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Saved reader bytes');return ref(p,sha(b))


def readback(*,registration_reference=None,selection_reference=None,publication_reference=None,execute=False):
    require(execute is True,'Explicit readback')
    for r in (registration_reference,selection_reference,publication_reference):source.reference(r)
    require(source.LOADED==PUBLISHER_SHA and source.filehash(source.SOURCE)==PUBLISHER_SHA,'Frozen shared source/parser code')
    c=source.load_inputs(registration_reference,compile_selector=False)
    require(selection_reference['path']==str(source.OUTPUT/'selection.json') and publication_reference['path']==str(source.OUTPUT/'publication.json'),'Fixed selection publication namespace')
    expected_sources=dict(c['sources']);selection=source.decode(source.take(selection_reference,c['sources']));pub=source.decode(source.take(publication_reference,c['sources']))
    require(selection['schema']=='SOURCE_BOUND_SINGLE_REPLACEMENT_SELECTION_V1' and pub['schema']=='SINGLE_REPLACEMENT_SELECTION_PUBLICATION_V1' and pub['status']=='PUBLISHED_PENDING_INDEPENDENT_READBACK','Published saved selection roles')
    require(selection['scope']=='FULL_SAVED_WITHIN_FAMILY_SELECTION_NOT_ACCOUNTS_OR_FORMAL_WINNER','Exact saved scope')
    for v in (selection,pub):
        source.flags(v);exact(v['source_hashes'],expected_sources,'Full exact source closure');exact(v['input_references'],c['refs'],'Seven fixed source roles');exact(v['registration_reference'],registration_reference,'External registration')
    exact(pub['selection_reference'],selection_reference,'Publication selected bytes');exact(pub['raw_reference'],selection['raw_reference'],'Same original return')
    require(pub['started_reference']['path']==str(source.OUTPUT/'started.json') and pub['raw_reference']['path']==str(source.OUTPUT/'raw_selection.json'),'Fixed raw/START paths')
    started=source.decode(source.take(pub['started_reference'],c['sources']));raw=source.decode(source.take(pub['raw_reference'],c['sources']))
    require(started['schema']=='SINGLE_REPLACEMENT_SELECTION_STARTED_V1','Original START');source.flags(started)
    exact(started['source_hashes'],expected_sources,'START source closure');exact(started['input_references'],c['refs'],'START source roles');exact(started['registration_reference'],registration_reference,'START registration')
    exact(raw,dict(returned=True,result=selection['selection']),'Original selector return preserved')
    c['dirs'][str(source.OUTPUT)]=['publication.json','raw_selection.json','selection.json','started.json']
    source.guard(c);require(not OUTPUT.exists(),'Create-only no retry');OUTPUT.mkdir(parents=True,exist_ok=False);saved=[]
    try:
        saved.append(save('started.json',dict(schema='SINGLE_REPLACEMENT_SELECTION_READBACK_STARTED_V1',selection_reference=selection_reference,publication_reference=publication_reference,registration_reference=registration_reference,**source.FLAGS)))
        counts=inspect_selection(c,selection['selection']);source.guard(c)
        saved.append(save('independent_readback.json',dict(schema='SINGLE_REPLACEMENT_SELECTION_INDEPENDENT_READBACK_V1',status='PASS',selection_reference=selection_reference,publication_reference=publication_reference,registration_reference=registration_reference,reader_sha256=LOADED,source_hashes=c['sources'],counts=counts,scope='INDEPENDENT_SAVED_FRACTION_RANKING_SHARED_AUTHENTICATED_JOURNAL_PARSER_NOT_REEVALUATION',selector_called=False,shared_source_parser_reference=ref(source.SOURCE,PUBLISHER_SHA),**source.FLAGS)))
        source.guard(c);require(source.filehash(SOURCE)==LOADED,'Loaded reader bytes')
        for r in saved:require(source.filehash(r['path'])==r['sha256'],'Final reader output')
        require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact reader namespace');return saved[-1]
    except BaseException as e:
        save('failure.json',dict(error_type=type(e).__name__,error=str(e),saved_references=saved,**source.FLAGS));raise


if __name__=='__main__':
    import argparse,json
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true')
    for k in ('registration','selection','publication'):p.add_argument('--'+k);p.add_argument('--'+k+'-sha')
    a=p.parse_args();print(json.dumps(readback(registration_reference=ref(a.registration,a.registration_sha),selection_reference=ref(a.selection,a.selection_sha),publication_reference=ref(a.publication,a.publication_sha),execute=a.execute)))
