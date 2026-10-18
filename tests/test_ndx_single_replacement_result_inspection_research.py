import json
import tempfile
import unittest
from copy import deepcopy
from decimal import localcontext, Inexact
from pathlib import Path
from unittest.mock import patch
from backtest import ndx_single_replacement_result_inspection_research as m
from backtest import ndx_single_replacement_evaluation_research as producer
from backtest import ndx_single_replacement_domain_research as domain
from scripts import ndx_single_replacement_shard_worker_20261003 as worker
from test_ndx_single_replacement_execution_registration_research import fixture_plan
from test_ndx_single_replacement_shard_worker_20261003 import context


def point():
    prepared=fixture_plan()['prepared'];task=domain.unrank(prepared,0)
    row=prepared['document']['cases'][0]['identity']['original_input_row']
    return dict(prepared=prepared,global_ordinal=0,task=task,saved_result=producer.evaluate_one(row,task))


def journal_fixture(mode='normal'):
    c=context();descriptor=c['plan']['document']['shards'][0];prepared=fixture_plan()['prepared']
    with tempfile.TemporaryDirectory() as tmp,patch.object(worker,'resource'):
        folder=Path(tmp)/'shard';function=c['evaluator'].evaluate_one;count=[]
        def evaluate(row,task):
            count.append(1)
            if mode=='exception' and len(count)==2:raise KeyboardInterrupt('original exception')
            if mode=='none':return None
            return function(row,task)
        with patch.object(c['evaluator'],'evaluate_one',evaluate):r=worker.process_shard(c,descriptor,folder)
        report=json.loads(worker.read(r));raw=(folder/'journal.jsonl').read_bytes()
    return dict(prepared=prepared,journal_bytes=raw,descriptor=descriptor,context_sha256=report['context_sha256'])


def resign(raw,mutate):
    records=[json.loads(b) for b in raw.splitlines()];mutate(records);previous='0'*64
    for record in records:
        record['body']['previous_sha256']=previous;record['record_sha256']=m.digest(record['body']);previous=record['record_sha256']
    return b''.join(m.encode(r)+b'\n' for r in records)


class Tests(unittest.TestCase):
    def test_independent_fraction_hand_values_and_no_production_call(self):
        a=point();before=deepcopy(a)
        self.assertEqual(a['saved_result']['cash_after_usd'],'4999/40')
        self.assertEqual(a['saved_result']['total_fee_usd'],'1/40')
        self.assertEqual(a['saved_result']['original_target_stock_l1'],'8/5')
        with patch.object(producer,'evaluate_one',side_effect=AssertionError('No evaluator')),patch.object(domain,'unrank',side_effect=AssertionError('No rank')),localcontext() as ctx:
            ctx.prec=2;ctx.traps[Inexact]=True;out=m.inspect_saved_evaluation(**a)
        self.assertEqual(out['status'],'PASS');self.assertEqual(a,before)
        for change in ('cash','fee','risk','l1','zero','identity'):
            b=deepcopy(a)
            if change=='cash':b['saved_result']['cash_after_usd']='125'
            elif change=='fee':b['saved_result']['sell_fee_usd']='0'
            elif change=='risk':b['saved_result']['risk']['checks']['MAX_SINGLE_WEIGHT']=True
            elif change=='l1':b['saved_result']['original_target_stock_l1']='0'
            elif change=='zero':del b['task']['proposed_holdings']['ZERO']
            else:b['task']['identity']['buy_quantity']=2
            with self.subTest(change=change),self.assertRaises(ValueError):m.inspect_saved_evaluation(**b)

    def test_complete_journal_and_resigned_numeric_or_identity_attack(self):
        a=journal_fixture()
        with patch.object(producer,'evaluate_one',side_effect=AssertionError()),patch.object(domain,'unrank',side_effect=AssertionError()):out=m.inspect_saved_journal(**a)
        self.assertTrue(out['complete']);self.assertEqual(out['arithmetic_checked_count'],2);self.assertEqual(out['full_integer_count'],560)
        for mode in ('numeric','start','status','ordinal'):
            b=deepcopy(a)
            def attack(records):
                if mode=='numeric':records[1]['body']['payload']['result']['cash_after_usd']='0'
                elif mode=='start':records[0]['body']['payload']['task']['signed_trade_quantities']['ZERO']=1
                elif mode=='status':records[2]['body']['payload']['outcome']='EVALUATION_EXCEPTION'
                else:records[3]['body']['global_ordinal']=False
            b['journal_bytes']=resign(b['journal_bytes'],attack)
            with self.subTest(mode=mode),self.assertRaises(ValueError):m.inspect_saved_journal(**b)

    def test_failure_and_every_partial_stage_retains_unknown_prefix(self):
        for mode in ('exception','none'):
            a=journal_fixture(mode);out=m.inspect_saved_journal(**a)
            self.assertEqual(out['terminal_rows'][-1]['outcome'],'EVALUATION_EXCEPTION' if mode=='exception' else 'VALIDATION_FAILURE')
            self.assertEqual(out['arithmetic_checked_count'],1 if mode=='exception' else 0)
        a=journal_fixture();lines=a['journal_bytes'].splitlines(keepends=True)
        for length in range(6):
            b=deepcopy(a);b['journal_bytes']=b''.join(lines[:length])+lines[length][:11]
            out=m.inspect_saved_journal(**b)
            self.assertEqual(out['unresolved_ordinal'],length//3)
            self.assertEqual(out['undispatched_ordinals'],[1] if length<3 else [])

    def test_rehashed_cap_and_full_denominator_not_trusted(self):
        a=point()
        for field in ('integer_count','pair_count','financial_integer_count_before_issuer'):
            b=deepcopy(a);b['prepared']['document'][field]+=1;b['prepared']['content_sha256']=m.digest(b['prepared']['document'])
            with self.subTest(field=field),self.assertRaises(ValueError):m.inspect_saved_evaluation(**b)


if __name__=='__main__':unittest.main()
