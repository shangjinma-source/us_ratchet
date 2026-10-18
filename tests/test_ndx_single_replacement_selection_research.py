import unittest
from copy import deepcopy
from decimal import localcontext,Inexact
from unittest.mock import patch
from backtest import ndx_single_replacement_selection_research as m
from backtest import ndx_single_replacement_domain_research as domain
from backtest import ndx_single_replacement_evaluation_research as evaluator
from test_ndx_single_replacement_execution_registration_research import fixture_plan


def fixture(issuer_exclusion=False):
    source=fixture_plan()['prepared']['document'];originals=[]
    for c in source['cases']:
        row=deepcopy(c['identity']['original_input_row'])
        row['risk_parameters'].update(max_single_weight='1',min_single_weight='0.001',top_weight_cap='1',minimum_effective_n_ratio='0.001',risk_chain_top1_cap='1')
        if issuer_exclusion:row['securities']['C']['issuer_id']=row['securities']['B']['issuer_id']
        originals.append(dict(input_row=row,input_reference=c['identity']['input_reference']))
    prepared=domain.prepare_single_replacement_domain(originals,source['action_contract']);d=prepared['document'];total=d['integer_count']
    prepref=dict(path='E:/synthetic/preparation.json',sha256='a'*64);auditref=dict(path='E:/synthetic/independent_readback.json',sha256='b'*64)
    items=[];terminals=[];locations=[];offset=0;counts=dict(FEASIBLE=0,INFEASIBLE=0,EVALUATION_EXCEPTION=0,VALIDATION_FAILURE=0)
    for ordinal in range(total):
        task=domain.unrank(prepared,ordinal);row=d['cases'][task['scenario_index']]['identity']['original_input_row'];value=evaluator.evaluate_one(row,task);counts[value['status']]+=1
        terminals.append(dict(global_ordinal=ordinal,task_id=task['task_id'],outcome=value['status']))
        for stage in ('START','RAW_RETURNED','POSTCHECK'):
            locations.append(dict(sequence=len(locations),byte_start=offset,byte_stop=offset+100,record_sha256='c'*64,stage=stage,global_ordinal=ordinal));offset+=100
        items.append(dict(global_ordinal=ordinal,task=task,evaluation=value,
            source_reference=dict(journal_reference=dict(path='E:/synthetic/shard-0000/journal.jsonl',sha256='d'*64),record_locator=deepcopy(locations[-2]),json_pointer='/body/payload/result'),
            inspection_reference=dict(reference=deepcopy(auditref),json_pointer=f'/shards/0/inspection/terminal_rows/{ordinal}')))
    report=dict(schema='SINGLE_REPLACEMENT_EXECUTION_INDEPENDENT_READBACK_V1',status='PASS_SAVED_PREFIX',full_domain_evaluated=True,input_references=dict(preparation=prepref),
        partition=dict(full_integer_count=total,terminal_count=total,unresolved_ordinal=None,undispatched_count=0,undispatched_start=total,undispatched_stop=total,outcome_counts=counts),
        shards=[dict(shard_result_reference=dict(path='E:/synthetic/shard-0000/result.json',sha256='e'*64),inspection=dict(schema='SINGLE_REPLACEMENT_SHARD_INDEPENDENT_ARITHMETIC_V1',status='PASS_SAVED_PREFIX',complete=True,unresolved_ordinal=None,partial_tail_present=False,undispatched_ordinals=[],shard_start=0,shard_stop=total,arithmetic_checked_count=total,terminal_rows=terminals,records=locations,full_integer_count=total,journal_sha256='d'*64))],
        **dict.fromkeys(('producer_called','evaluator_called','old_account_reopened','point_in_time_verified','full_ndx_certified','economic_winner_selected','account_executed','fit_executed','orders_executed','automatic_retry_allowed'),False))
    return dict(prepared=prepared,preparation_reference=prepref,readback=report,readback_reference=auditref,records=items)


class Once:
    def __init__(self,rows):self.rows=rows;self.used=False
    def __iter__(self):
        if self.used:raise AssertionError('Stream must be consumed once')
        self.used=True;yield from self.rows


class Tests(unittest.TestCase):
    def test_exact_hand_tiers_and_single_pass_no_evaluation(self):
        a=fixture();first=[r for r in a['records'] if r['task']['scenario_index']==0]
        for r in first:r['evaluation'].update(original_target_stock_l1='2',total_fee_usd='2',sell_fee_usd='1',buy_fee_usd='1')
        # Same original L1: lower bilateral fee wins, then A,C,q before B,C,q.
        tied=[r for r in first if r['task']['identity']['incoming_security_id']=='C' and r['task']['identity']['buy_quantity']==1]
        self.assertEqual([r['task']['identity']['outgoing_security_id'] for r in tied],['A','B'])
        for r in tied:r['evaluation'].update(original_target_stock_l1='1',total_fee_usd='1',sell_fee_usd='1/2',buy_fee_usd='1/2')
        before=deepcopy(a);a['records']=Once(a['records'])
        with patch.object(evaluator,'evaluate_one',side_effect=AssertionError('No evaluation')),patch.object(domain,'unrank',side_effect=AssertionError('No producer rank')),localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True;out=m.select_complete_single_replacements(**a)
        self.assertEqual(out['document']['rows'][0]['selected']['task']['task_id'],tied[0]['task']['task_id'])
        self.assertEqual(out['document']['integer_count'],560);self.assertEqual(out['document']['selected_case_count'],40)
        # Primary L1 wins even when its fee is larger.
        before['records'][1]['evaluation'].update(original_target_stock_l1='0',total_fee_usd='20',sell_fee_usd='10',buy_fee_usd='10')
        out=m.select_complete_single_replacements(**before)
        self.assertEqual(out['document']['rows'][0]['selected']['global_ordinal'],1)

    def test_missing_extra_reordered_and_exception_never_select_prefix(self):
        for mode in ('missing','extra','swap','exception','unknown','notfull'):
            a=fixture()
            if mode=='missing':a['records'].pop()
            elif mode=='extra':a['records'].append(deepcopy(a['records'][-1]))
            elif mode=='swap':a['records'][0],a['records'][1]=a['records'][1],a['records'][0]
            elif mode=='exception':a['readback']['partition']['outcome_counts']['EVALUATION_EXCEPTION']=1
            elif mode=='unknown':a['readback']['shards'][0]['inspection']['unresolved_ordinal']=0
            else:a['readback']['full_domain_evaluated']=False
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.select_complete_single_replacements(**a)

    def test_issuer_excluded_denominator_and_no_feasible_case(self):
        a=fixture(True);before=deepcopy(a)
        for r in a['records']:
            if r['task']['scenario_index']==0:
                r['evaluation']['risk']['checks']['MAX_SINGLE_WEIGHT']=False;r['evaluation']['risk']['all_passed']=False
                r['evaluation']['status']='INFEASIBLE';r['evaluation']['feasible']=False
                a['readback']['shards'][0]['inspection']['terminal_rows'][r['global_ordinal']]['outcome']='INFEASIBLE'
                a['readback']['partition']['outcome_counts']['FEASIBLE']-=1;a['readback']['partition']['outcome_counts']['INFEASIBLE']+=1
        result=m.select_complete_single_replacements(**a)['document']
        self.assertEqual(result['financial_integer_count_before_issuer'],560)
        self.assertGreater(result['structurally_excluded_integer_count'],0)
        self.assertEqual(result['integer_count']+result['structurally_excluded_integer_count'],560)
        self.assertEqual(result['rows'][0]['status'],'NO_FEASIBLE');self.assertIsNone(result['rows'][0]['selected'])
        self.assertEqual(result['no_feasible_case_count'],1);self.assertEqual(result['selected_case_count'],39)
        self.assertEqual(a['prepared'],before['prepared'])

    def test_source_pointer_task_and_policy_attack(self):
        for mode in ('locator','audit','task','policy','denominator','bool'):
            a=fixture()
            if mode=='locator':a['records'][0]['source_reference']['record_locator']['byte_start']+=1
            elif mode=='audit':a['records'][0]['inspection_reference']['json_pointer']='/shards/0/inspection/terminal_rows/1'
            elif mode=='task':a['records'][0]['task']['proposed_holdings']['ZERO']=1
            elif mode=='policy':a['prepared']['document']['action_contract']['ranking_policy']='future returns';a['prepared']['content_sha256']=m.digest(a['prepared']['document'])
            elif mode=='denominator':a['readback']['partition']['terminal_count']-=1
            else:a['records'][0]['evaluation']['feasible']=1
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.select_complete_single_replacements(**a)


if __name__=='__main__':unittest.main()
