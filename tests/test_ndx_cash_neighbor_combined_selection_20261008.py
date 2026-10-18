from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from backtest import ndx_cash_neighbor_combined_stream_selection_research as new
from backtest import ndx_cash_neighbor_stream_selection_research as old
from scripts import ndx_cash_neighbor_combined_selection_20261008 as source
from scripts import ndx_cash_neighbor_combined_selection_independent_readback_20261008 as reader
from test_ndx_cash_neighbor_selection_research import fixture


def combined(arguments):
    arguments=deepcopy(arguments);audit=arguments['full_audit']['document'];refs=audit['shard_audit_references'];counts=audit['counts']['outcome_counts']
    audit.clear();audit.update(schema='CASH_NEIGHBOR_COMBINED_INDEPENDENT_READBACK_V1',status='PASS',task_count=301657,physical_recovery_segment_count=45,new_dispatch_count=42301,previously_audited_arithmetic_reused_count=531,existing_external_original_task_count=1,arithmetic_checked_in_this_run=301125,sidecar_raw_arithmetic_rechecked_count=1,old_candidate_count=2648,selection_union_candidate_count=304305,logical_shard_reports=refs,outcome_counts={k:counts[k]for k in ('FEASIBLE','INFEASIBLE','EXTERNALLY_REFERENCED')},source_hashes={})
    for key in ('evaluator_called','producer_called','old_tasks_redispatched','account_executed','orders_executed','point_in_time_verified','promotion_allowed','economic_winner_selected','full_integer_domain_exhausted','future_independent_oos','automatic_retry_allowed','runtime_binary_closure_verified'):audit[key]=False
    for record in arguments['new_records']:record['shard_audit']['document']['schema']='CASH_COMBINED_LOGICAL_SHARD_AUDIT_V1'
    return arguments


class Tests(unittest.TestCase):
    def test_same_full_ranking_and_ledger_with_explicit_combined_schema(self):
        a=fixture();old_rows=[];expected=old.select_scenario_stream(**a,emit_ledger_row=lambda v:old_rows.append(v));b=combined(a);rows=[];got=new.select_scenario_stream(**b,emit_ledger_row=lambda v:rows.append(v))
        expected['schema']='CASH_NEIGHBOR_COMBINED_STREAM_SCENARIO_SELECTION_V1';self.assertEqual(got,expected);self.assertEqual(rows,old_rows)

    def test_combined_denominator_and_authority_attacks(self):
        for key,value in [('task_count',301656),('new_dispatch_count',42300),('old_candidate_count',0),('evaluator_called',0),('promotion_allowed',True)]:
            a=combined(fixture());a['full_audit']['document'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):new.select_scenario_stream(**a,emit_ledger_row=lambda _:None)

    def test_no_prefix_or_unlinked_logical_audit(self):
        for kind in ('prefix','unlinked','extra'):
            a=combined(fixture())
            if kind=='prefix':a['new_records']=[]
            elif kind=='extra':a['new_records']*=2
            else:a['new_records'][0]['shard_audit']['reference']['sha256']='f'*64
            with self.subTest(kind=kind),self.assertRaises(ValueError):new.select_scenario_stream(**a,emit_ledger_row=lambda _:None)

    def test_both_source_entrypoints_stay_pending_before_io(self):
        with patch.dict(source.BOUND,{'full_audit':(None,None)}),patch.dict(reader.BOUND,{'index':(None,None)}),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaises(ValueError):source.prepare()
            with self.assertRaises(ValueError):reader.readback(execute=True)

    def test_new_journal_locators_are_readable_without_fabricated_sequence(self):
        with tempfile.TemporaryDirectory()as directory:
            row=dict(schema='CASH_NEIGHBOR_RECOVERY_RECORD_V1',record_sequence=0,previous_record_sha256='0'*64,registration_sha256='a'*64,task_id='b'*64,original_shard_task_position=163,original_global_task_position=259356,scenario_candidate_ordinal=46163,stage='RAW_RETURNED',payload={'saved':'value'})
            row['record_sha256']=source.digest(row);raw=source.enc(row)+b'\n';p=Path(directory)/'journal';p.write_bytes(raw);r=source.ref(p,source.sha(raw));sources={};streamed=set();rows=source.saved_journal(r,sources,streamed)
            self.assertEqual(rows[0][0],row);ev=reader.Evidence(sources)
            try:self.assertEqual(ev.span(rows[0][1],True),row['payload'])
            finally:ev.close()

    def test_real_partial_sidecar_and_recovery_shapes_preserved(self):
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);sources={}
            def put(name,value,lines=False):
                raw=b''.join(source.enc(x)+b'\n'for x in value)if lines else source.enc(value)
                p=root/name;p.write_bytes(raw);r=source.ref(p,source.sha(raw));sources[r['path']]=r['sha256'];return r
            tasks=[dict(task_id=f'{i:064x}',scenario_candidate_ordinal=i)for i in range(164)]
            tr=put('tasks',tasks,True);descriptor=dict(global_shard_index=279,shard={'path':tr['path'],'sha256':tr['sha256'],'start':0,'stop':164})
            post=dict(outcome='INFEASIBLE',original_target_stock_weight_l1=None,evaluation_error=None,validation_error=None)
            def journal(positions,recovery):
                result=[];previous='0'*64
                for position in positions:
                    stages=[('TASK_STARTED',dict(task_reference=dict(tr,jsonl_line_index=position))),('RAW_RETURNED',dict(result={},error=None,explicit_evaluator_call_attempt_count=1,returned_evaluation_count=1))]
                    if position!=162:stages.append(('POSTCHECK',post))
                    for stage,payload in stages:
                        row=dict(schema='CASH_NEIGHBOR_RECOVERY_RECORD_V1'if recovery else'CASH_NEIGHBOR_JOURNAL_RECORD_V1',previous_record_sha256=previous,task_id=tasks[position]['task_id'],stage=stage,payload=payload)
                        if recovery:row.update(record_sequence=len(result),registration_sha256='a'*64,original_shard_task_position=position,original_global_task_position=259193+position,scenario_candidate_ordinal=position)
                        else:row.update(sequence=len(result),context_sha256='b'*64,task_position=position)
                        row['record_sha256']=source.digest(row);previous=row['record_sha256'];result.append(row)
                return result
            oldref=put('old',journal(range(163),False),True);newref=put('new',journal([163],True),True)
            original=source.saved_journal(oldref,{},set());rawloc=original[-1][1]
            sidecar=put('sidecar',dict(task_id=tasks[162]['task_id'],raw_record_reference={k:rawloc[k]for k in ('sequence','byte_start','byte_stop','record_sha256','task_id','stage')},independent_postcheck=post))
            sr=put('started',{});cr=put('completion',dict(started_reference=sr))
            report=dict(schema='CASH_COMBINED_LOGICAL_SHARD_AUDIT_V1',status='PASS',descriptor=descriptor,original_shard_index=279,task_count=164,task_results=[dict(task_id=t['task_id'],**post)for t in tasks],evidence=dict(original_partial_journal_reference=oldref,recovery_journal_reference=newref,sidecar_reference=sidecar,recovery_completion_reference=cr))
            ar=put('audit',report);d=dict(full_audit=dict(logical_shard_reports=[ar]*280,source_hashes=sources));locator={};saved=[]
            for record in source.new_records(d,{},[descriptor],{},dict(sources),set(),locator):saved.append((record,deepcopy(locator)))
            self.assertEqual(len(saved),164)
            self.assertIn('sidecar_reference',saved[162][1]);self.assertNotIn('postcheck_record',saved[162][1])
            self.assertEqual(saved[163][1]['journal_schema'],'CASH_NEIGHBOR_RECOVERY_RECORD_V1')
            self.assertEqual(saved[162][0]['references']['postcheck'],sidecar)


if __name__=='__main__':unittest.main()
