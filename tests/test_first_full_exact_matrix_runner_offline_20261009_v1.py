"""Prepared first-full orchestration: synthetic transport/temp files only, no real77 math."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'tmp/first_full_exact_matrix_runner_20261009_v1.py'
spec=importlib.util.spec_from_file_location('full_first_offline_subject',PATH)
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def matrix():
    return dict(model_id=s.MODEL,ordered_security_ids=[f'S{i}' for i in range(77)],
                training_dates=[f'synthetic-date-{i}' for i in range(126)],shape=[126,77],cells=[['0']*77 for _ in range(126)])


def controlled_result():
    # Transport fixture only: declares work but does NOT perform77means/3003pair arithmetic.
    means=[dict(column=i,status='COMPUTED',value='0') for i in range(77)]
    pairs=[dict(i=i,j=j,status='COMPUTED',sample='0',value='0') for i in range(77) for j in range(i,77)]
    ledger=[];offset=0
    for i in range(77):ledger.append(dict(kind='MEAN',column=i,cost=127,start=offset,stop=offset+127));offset+=127
    for pair in pairs:
        ledger.append(dict(kind='PAIR',i=pair['i'],j=pair['j'],cost=508,start=offset,stop=offset+508));offset+=508
    return dict(schema='EXACT_TRAINING_MOMENTS_V1',status='COMPLETE',model_id=s.MODEL,matrix_sha256=s.MATRIX_SHA,
        input_binding='UNBOUND_PURE_INPUT_NOT_SOURCE_AUTHENTICATED',null_coordinates=[],mean_tasks=means,pair_tasks=pairs,full_covariance=[['0']*77 for _ in range(77)],arithmetic_ledger=ledger,
        work=dict(unit='REGISTERED_RATIONAL_PRIMITIVES_V1',scope='NUMERICAL_MOMENT_PRIMITIVES_ONLY_EXCLUDES_VALIDATION_IO_GCD_AND_INDEPENDENT_CERTIFICATE_RECHECK',validation_is_outside_primitive_budget=True,gcd_internal_operations=None,requested=s.BUDGET,spent=s.BUDGET,unused=0,mean_columns_completed=77,pair_entries_completed=3003,
                  required_tasks=3080,pending_tasks=0,source_blocked_tasks=0,matrix_validation_cells=9702,fraction_parses=9702,
                  source_io_calls=0,guard_calls=0,resume_replay_tasks=0,independent_certificate_recheck_tasks=0,
                  actual_primitive_counts=s.expected_primitives(),input_max_fraction_bits=[0,1],
                  intermediate_max_fraction_bits=[0,1],output_max_fraction_bits=[0,1]),
        certificate=dict(kind='COMPLETE_CENTERED_GRAM_PLUS_DIAGONAL',n=126,ddof=1,lambda_exact='7/20',
                         matrix_sha256=s.MATRIX_SHA,independently_checked=False),
        qualified_inventory=None,current_account=None,current_new_money=None,plan_rows=[],permissions={'authorized':False})


class FullFirstOffline(unittest.TestCase):
    def test_runtime_both_limits_fail_before_any_output_or_source_probe(self):
        for effective,flag in ((4300,4300),(8192,4300),(4300,8192),(0,0),(8192,-1)):
            with patch.object(s.sys,'get_int_max_str_digits',return_value=effective),patch.object(s.sys,'flags',SimpleNamespace(int_max_str_digits=flag)), \
                 patch.object(Path,'lstat',side_effect=AssertionError('IO before runtime gate')):
                with self.assertRaisesRegex(ValueError,'runtime get/flags'):s.run(execute=True)
        self.assertEqual(s.runtime_gate()['effective_intdigitcap'],8192)

    def test_execute_gate_also_precedes_runtime(self):
        with patch.object(s,'runtime_gate',side_effect=AssertionError('runtime probed')):
            for value in (False,None,1):
                with self.assertRaisesRegex(ValueError,'Explicit approved'):s.run(execute=value)

    def test_all_input_literals_and_bits_no_helper_or_io(self):
        with patch.object(s,'take',side_effect=AssertionError('IO')):
            report=s.input_premises(matrix())
        self.assertEqual((report['literals'],report['integer_parses'],report['gcd_calls']), (9702,19404,9702))
        for value in (str(1<<53),'1/'+str(1<<56),None,True,'-1','2/4','-0','1/1','9'*9000):
            bad=matrix();bad['cells'][0][0]=value
            with self.subTest(value=str(value)[:30]),self.assertRaises(ValueError):s.input_premises(bad)

    def test_complete_count_ledger_character_copies_and_signed_lengths(self):
        out=controlled_result();report=s.validate_complete(out,dict(max_bits=[0,1]))
        self.assertEqual(report['numeric_ascii_characters_all_copies'],12012)
        self.assertEqual(report['literals'],6083)
        # One controlled negative offdiag sample/entry plus two serializedcov copies, no covariance arithmetic.
        out['pair_tasks'][1].update(sample='-1/2',value='-1/2')
        out['full_covariance'][0][1]=out['full_covariance'][1][0]='-1/2'
        out['work']['output_max_fraction_bits']=[1,2]
        report=s.validate_complete(out,dict(max_bits=[0,1]))
        self.assertEqual(report['numeric_ascii_characters_all_copies'],12024)

    def test_partial_wrong_counts_ledger_bounds_and_boolean_types_reject(self):
        changes=[lambda r:r.update(status='PARTIAL_PENDING_BUDGET'),lambda r:r.update(full_covariance=None),
                 lambda r:r['work'].update(pair_entries_completed=1),lambda r:r['work'].update(unused=False),
                 lambda r:r['mean_tasks'][0].update(column=False),lambda r:r['arithmetic_ledger'][77].update(cost=0),
                 lambda r:r['work'].update(intermediate_max_fraction_bits=[14246,1]),
                 lambda r:r['certificate'].update(independently_checked=0),
                 lambda r:r['pair_tasks'][1].update(value='1/'+str(1<<14138))]
        for change in changes:
            out=controlled_result();change(out)
            with self.assertRaises((ValueError,TypeError)):s.validate_complete(out,dict(max_bits=[0,1]))

    def test_real_temp_pin_and_output_parent_junction_gates(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);p=base/'code.py';p.write_bytes(b'drift')
            with self.assertRaisesRegex(ValueError,'Fixed source bytes changed'):s.take((p,'0'*64))
            target=base/'target';target.mkdir();link=base/'junction'
            made=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,text=True)
            self.assertEqual(made.returncode,0,made.stderr)
            try:
                with patch.object(s,'OUT',link/'measurement'),patch.object(s,'take',side_effect=AssertionError('source read')) as take:
                    with self.assertRaisesRegex(ValueError,'reparse'):s.run(execute=True)
                    self.assertEqual(take.call_count,0)
                self.assertEqual(list(target.iterdir()),[])
            finally:os.rmdir(link)

    def orchestration(self,folder,partial=False):
        fixture_matrix=matrix();output=controlled_result()
        if partial:output['status']='PARTIAL_PENDING_BUDGET'
        # These262 fixture identities are never opened: mocked fixed transport + mocked guard only.
        sources={str(folder/f'fixture_source_{i}'): '0'*64 for i in range(262)}
        namespaces={str(folder/f'fixture_ns_{i}'):[] for i in range(7)}
        ready=[dict(unique_matrix_index=11+i,matrix_sha256='fixture',window_ordinals=[]) for i in range(12)]
        snapshot=dict(schema='FULL_CONDITIONAL_POOL_TRAINING_BANK_V1',
                      source_facts=dict(consumed_source_hashes=sources,namespace_snapshots=namespaces,source_checks=[{'status':'SOURCE_BLOCKED'}]*10),
                      windows=[dict(window_ordinal=i,training_blocked_sid_rows=[{}] if i<51 else []) for i in range(78)],permissions={'authority':False})
        blobs={str(s.HOST_FILES[1][0]):b'{}',str(s.HOST_FILES[3][0]):b'{}',str(s.SNAPSHOT[0]):json.dumps(snapshot).encode()}
        calls=[]
        def helper_stub(*,matrix,work_budget):
            calls.append(dict(shape=matrix['shape'],declared_budget=work_budget,synthetic_transport=True))
            return output
        fake=SimpleNamespace(prepare_exact_training_moments=helper_stub)
        with patch.object(s,'OUT',folder/'measurement'),patch.object(s,'take',lambda ref:blobs.get(str(ref[0]),b'pass')), \
             patch.object(s,'derive_closure',return_value=(sources,namespaces)), \
             patch.object(s,'CLOSED_MAP_SHA',s.sha(s.encoded(sources))),patch.object(s,'NAMESPACE_MAP_SHA',s.sha(s.encoded(namespaces))), \
             patch.object(s,'choose_matrix',return_value=(fixture_matrix,ready)), \
             patch.object(s,'guard',return_value={'status':'MOCK_FIXTURE_GUARD_NOT_REAL'}) as guard, \
             patch.object(s.types,'ModuleType',return_value=fake):
            if partial:
                with self.assertRaisesRegex(ValueError,'Expected complete'):s.run(execute=True)
            else:self.assertEqual(s.run(execute=True),0)
        return folder/'measurement',calls,guard.call_count

    def test_synthetic_orchestration_single_full_artifact_envelope_and_dump_hash(self):
        with tempfile.TemporaryDirectory() as td:
            out,calls,guards=self.orchestration(Path(td))
            self.assertEqual(len(calls),1);self.assertEqual(guards,2)
            envelope=json.loads((out/'result.json').read_bytes())
            numerical=(out/'full_moments.json').read_bytes();reference=envelope['full_moments_reference']
            self.assertEqual(reference['sha256'],hashlib.sha256(numerical).hexdigest())
            self.assertEqual(reference['bytes'],len(numerical))
            self.assertNotIn('full_covariance',envelope)
            self.assertEqual(len(envelope['other11_ready_unique_statuses']),11)
            self.assertEqual(len(envelope['source_blocked_window_ordinals']),51)
            self.assertEqual(envelope['cumulative_primitives'],1545590) # Synthetic declaredwork, no actual77math.

    def test_synthetic_partial_retains_raw_file_failure_and_no_retry(self):
        with tempfile.TemporaryDirectory() as td:
            out,calls,guards=self.orchestration(Path(td),partial=True)
            self.assertEqual(len(calls),1);self.assertEqual(guards,2)
            self.assertEqual(sorted(p.name for p in out.iterdir()),['START.json','exception.json','full_moments.json'])
            failure=json.loads((out/'exception.json').read_bytes());self.assertTrue(failure['numerical_file_exists'])
            with patch.object(s,'OUT',out),patch.object(s,'take',side_effect=AssertionError('retryread')):
                with self.assertRaisesRegex(ValueError,'already exists'):s.run(execute=True)

    def test_safe_fixed_read_failure_and_unknown_claim_readbefore_guard(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'measurement'
            with patch.object(s,'OUT',out),patch.object(s,'take',side_effect=ValueError('OFFLINE_FIXED_READ_TRAP')):
                with self.assertRaisesRegex(ValueError,'OFFLINE_FIXED_READ_TRAP'):s.run(execute=True)
            self.assertEqual(sorted(p.name for p in out.iterdir()),['START.json','exception.json'])
        snapshot=dict(schema='FULL_CONDITIONAL_POOL_TRAINING_BANK_V1',source_facts=dict(consumed_source_hashes={'UNREAD_TRAP':'0'*64},namespace_snapshots={}))
        with patch.object(Path,'read_bytes',side_effect=AssertionError('claimfollow')):
            with self.assertRaisesRegex(ValueError,'CORE source closure'):s.associate_snapshot(snapshot,{}, {})

    def test_small_actual_pure_helper_only_two_columns(self):
        # New small synthetic calculation only. Never source77matrix/reader/guard.
        from backtest import ndx_full_pool_training_moments_research as helper
        tiny=dict(model_id=helper.MODEL,ordered_security_ids=['A','B'],training_dates=['2026-01-01','2026-01-02','2026-01-03'],
                  shape=[3,2],cells=[['0','1/5'],['1/5','0'],['1/10','1/10']])
        result=helper.prepare_exact_training_moments(matrix=tiny,work_budget=56)
        self.assertEqual(result['full_covariance'],[['1/100','-13/2000'],['-13/2000','1/100']])
        self.assertEqual(result['work']['spent'],56)
        self.assertFalse(s.OUT.exists())

    def test_temp_source_namespace_and_owncode_drift_guard(self):
        # Actual guard implementation, ONLY controlled temporary files; not real CORE262.
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);code=folder/'owncode.py';code.write_bytes(b'initial')
            source={str(code):s.sha(b'initial')};names={str(folder):s.namespace(folder)}
            self.assertEqual(s.guard(source,names)['files'],1)
            code.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Fixed source bytes changed'):s.guard(source,names)
            code.write_bytes(b'initial');(folder/'extra_failure.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'Namespace changed'):s.guard(source,names)
            (folder/'extra_failure.json').unlink()
            self.assertEqual(s.guard(source,names)['namespaces'],1)

    def test_own_runtime_gate_rechecked_immediately_before_helperexec(self):
        # Source structure assertion complements first-gate runtime adversaries.
        import ast
        tree=ast.parse(PATH.read_text())
        function=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=='run')
        calls=sorted((x.lineno,ast.unparse(x.func)) for x in ast.walk(function) if isinstance(x,ast.Call))
        gates=[line for line,name in calls if name=='runtime_gate']
        execute=next(line for line,name in calls if name=='exec')
        self.assertEqual(len(gates),2);self.assertLess(gates[1],execute)
