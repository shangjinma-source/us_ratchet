"""Offline fixed host tests: no real snapshot/fullartifact/CORE IO or real77moments."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import ast,hashlib,importlib.util,json,os,subprocess,sys,tempfile,unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];PATH=ROOT/'tmp/full_pool_identity_fixed_host_20261009_v1.py'
spec=importlib.util.spec_from_file_location('identity_host_offline',PATH);s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)


def mocked_domain(folder):
    sources={str(folder/f'controlled_source_{i}'): '0'*64 for i in range(262)}
    namespaces={str(folder/f'controlled_ns_{i}'):[] for i in range(7)}
    ready=[dict(unique_matrix_index=11+i,matrix_sha256=s.MATRIX_SHA if i==0 else '0'*64,window_ordinals=[11,23,59,71] if i==0 else []) for i in range(12)]
    windows=[dict(window_ordinal=i,training_blocked_sid_rows=[{}] if i<51 else []) for i in range(78)]
    snapshot=dict(schema='FULL_CONDITIONAL_POOL_TRAINING_BANK_V1',windows=windows,
                  source_facts=dict(consumed_source_hashes=sources,namespace_snapshots=namespaces,source_checks=[dict(status='SOURCE_BLOCKED')]*10),
                  permissions=dict(authorized=False))
    fixed=s.EXPECTED_BINDING['fixed_roles'];fullref=dict(**fixed['full_moments'],dump_seconds=0.0)
    envelope=dict(status='PASS_COMPLETE_FIRST_UNIQUE_MATRIX_NOT_REAL_ECONOMIC_ADMISSION',scope='SNAPSHOT_BOUND_DESCRIPTIVE_EXACT_MATRIX',
        full_moments_reference=fullref,matrix_reference=dict(index=11,sha256=s.MATRIX_SHA,window_ordinals=[11,23,59,71]),
        all78_window_domain=windows,all12_ready_unique_references=ready,
        other11_ready_unique_statuses=[dict(**item,status='NOT_COMPUTED') for item in ready[1:]],source_blocked_window_ordinals=list(range(51)),
        snapshot_reference=fixed['snapshot'],budget=1535303,prior_prefix_primitives=10287,cumulative_primitives=1545590,
        not_resume=True,automatic_certificate_replay=False,evidence=dict(numerical_artifact=fullref),
        runtime=dict(effective_intdigitcap=8192,flags_intdigitcap=8192),peak_rss={},elapsed_seconds=0.0,
        source_checks=snapshot['source_facts']['source_checks'],real_joint_objective='UNREGISTERED',causal_action_rule='UNREGISTERED',
        thirteen_cohort_prior_cash='SOURCE_BLOCKED',qualified_inventory=None,qualified_denominator=None,current_account=None,current_new_money=None,
        plan_rows=[],permissions=snapshot['permissions'],source_authenticated=False,winner_selected=False)
    start=dict(status='START_FULL_FIRST_MATRIX_FROM_ZERO_NOT_RESUME',budget=1535303,prior_spent=10287,cumulative_expected=1545590,
               matrix_index=11,raw_replays=0,matrix_sha256=s.MATRIX_SHA,certificate_auto_replay=False)
    terminal=dict(status='PASS_SINGLE_FULL_MATRIX_PROCESS_AND_PROTECTION_NOT_ECONOMIC_ADMISSION',exit_code=0,protected_same=True,sealed_inventory_same=True)
    authorization=dict(status='ROOT_AUTHORIZED_ONE_FIXED_COMPLETE_MATRIX_FROM_ZERO',runner_sha256=fixed['producer_runner']['sha256'],
                       freeze_sha256=fixed['producer_freeze']['sha256'],c_review_sha256=fixed['producer_offline_c_review']['sha256'])
    docs=dict(snapshot=snapshot,full_moments={'mock':'NO_REAL_NUMBERS'},envelope=envelope,measurement_start=start,root_terminal=terminal,root_authorization=authorization)
    values=dict(matrix_sha256=s.MATRIX_SHA,mean_tasks=[],pair_tasks=[],work=dict(complete_cost=787556,spent=787556,pending_tasks=0,full_coordinates_independently_compared=5929),
                certificate=dict(independent_arithmetic_readback_complete=True),status='PASS_INDEPENDENT_RAW_CROSS_MOMENT_IDENTITY_NOT_SOURCE_OR_ECONOMIC_ADMISSION',
                producer_declarations=dict(intermediate_maxima_independently_replayed=False),permissions={'authorized':False})
    return sources,namespaces,ready,docs,values


class FixedHostOffline(unittest.TestCase):
    def orchestration(self,folder,*,mutate=None,after_drift=False,partial=False,reparse_at_values=False):
        sources,namespaces,ready,docs,values=mocked_domain(folder)
        if mutate:mutate(docs)
        calls=[];reads=[]
        def take_sized(ref):
            reads.append(str(ref[0]))
            if str(ref[0])==str(s.BINDING[0]):return json.dumps(s.EXPECTED_BINDING).encode()
            role=next(role for role,item in s.EXPECTED_BINDING['fixed_roles'].items() if item['path']==str(ref[0]))
            return json.dumps(docs[role]).encode() if role in docs else b'CONTROLLED_BYTES_NO_REAL_READ'
        def pure_call(**kw):
            calls.append(dict(budget=kw['work_budget'],mock_full77_transport=True))
            if partial:
                values['work'].update(spent=0,pending_tasks=3080,full_coordinates_independently_compared=0)
                values['certificate']['independent_arithmetic_readback_complete']=False;values['status']='PARTIAL_PENDING_BUDGET'
            if reparse_at_values:
                (folder/'measurement').rename(folder/'retained_safe_start')
                p=subprocess.run(['cmd','/c','mklink','/J',str(folder/'measurement'),str(folder/'unsafe_target')],capture_output=True,text=True)
                if p.returncode:raise RuntimeError(p.stderr)
            return values
        fake=SimpleNamespace(verify_raw_cross_moment_identity=pure_call)
        def fixedtake(ref):
            if str(ref[0]) in (str(s.HOST_FILES[1][0]),str(s.HOST_FILES[3][0])):return b'{}'
            return b'pass'
        guard_effect=[{'status':'MOCK_TEMP_GUARD'},ValueError('CONTROLLED_AFTER_GUARD_DRIFT')] if after_drift else None
        with patch.object(s,'OUT',folder/'measurement'),patch.object(s,'take_sized',side_effect=take_sized),patch.object(s,'take',side_effect=fixedtake), \
             patch.object(s,'derive_closure',return_value=(sources,namespaces)),patch.object(s,'CLOSED_MAP_SHA',s.sha(s.encoded(sources))), \
             patch.object(s,'NAMESPACE_MAP_SHA',s.sha(s.encoded(namespaces))),patch.object(s,'choose_matrix',return_value=({'controlled':'no77math'},ready)), \
             patch.object(s,'guard',side_effect=guard_effect,return_value={'status':'MOCK_TEMP_GUARD'}) as guard,patch.object(s.types,'ModuleType',return_value=fake):
            if after_drift:
                with self.assertRaisesRegex(ValueError,'CONTROLLED_AFTER_GUARD_DRIFT'):s.run(execute=True,work_budget=787556)
                code=None
            elif reparse_at_values:
                with self.assertRaisesRegex(ValueError,'reparse'):s.run(execute=True,work_budget=787556)
                code=None
            elif mutate:
                with self.assertRaises(ValueError):s.run(execute=True,work_budget=787556)
                code=None
            else:code=s.run(execute=True,work_budget=0 if partial else 787556)
        return folder/'measurement',calls,reads,guard.call_count,code

    def test_import_no_own_hash_or_business_io_and_no_asserts(self):
        tree=ast.parse(PATH.read_text())
        self.assertFalse(any(isinstance(node,ast.Assert) for node in ast.walk(tree)))
        topcalls=[node for node in tree.body if isinstance(node,ast.Assign) and isinstance(node.value,ast.Call)]
        self.assertTrue(all(isinstance(n.value.func,ast.Name) and n.value.func.id=='Path' for n in topcalls))
        with patch.object(Path,'read_bytes',side_effect=AssertionError('import business IO')):
            spec=importlib.util.spec_from_file_location('identity_host_import_again',PATH);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

    def test_all_parameter_runtime_gates_precede_own_read_or_stat(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),patch.object(Path,'lstat',side_effect=AssertionError('stat')):
            for execute,budget in ((False,787556),(1,787556),(True,None),(True,True),(True,-1),(True,787557)):
                with self.assertRaises(ValueError):s.run(execute=execute,work_budget=budget)
            with self.assertRaises(NotImplementedError):s.run(execute=True,work_budget=0,resume={})
            for get,flag in ((4300,8192),(8192,4300),(0,0)):
                with patch.object(s.sys,'get_int_max_str_digits',return_value=get),patch.object(s.sys,'flags',SimpleNamespace(int_max_str_digits=flag)):
                    with self.assertRaisesRegex(ValueError,'runtime'):s.run(execute=True,work_budget=0)

    def test_optimized_python_still_failclosed(self):
        code="import importlib.util;from pathlib import Path;from unittest.mock import patch;p=Path(r'"+str(PATH)+"');sp=importlib.util.spec_from_file_location('o',p);m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)\nwith patch.object(Path,'read_bytes',side_effect=RuntimeError('UNEXPECTED_IO')):\n try:m.run(execute=False,work_budget=0)\n except ValueError:print('OPTIMIZED_PREIO_REJECT')\n else:raise RuntimeError('NOT_REJECTED')"
        done=subprocess.run([sys.executable,'-B','-O','-X','int_max_str_digits=8192','-c',code],capture_output=True,text=True)
        self.assertEqual(done.returncode,0,done.stderr);self.assertIn('OPTIMIZED_PREIO_REJECT',done.stdout)

    def test_binding_extra_trap_rejected_before_any_role_source_read(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);binding=deepcopy(s.EXPECTED_BINDING);binding['fixed_roles']['TRAP']={'path':'UNREAD','sha256':'0'*64,'bytes':0}
            with patch.object(s,'OUT',folder/'measurement'),patch.object(s,'take_sized',return_value=json.dumps(binding).encode()) as reads, \
                 patch.object(s,'take',side_effect=AssertionError('role/source read')):
                with self.assertRaisesRegex(ValueError,'Exact13'):s.run(execute=True,work_budget=0)
            self.assertEqual(reads.call_count,1);self.assertEqual(sorted(p.name for p in (folder/'measurement').iterdir()),['START.json','exception.json'])
        with patch.object(Path,'read_bytes',side_effect=AssertionError('claims IO')):
            with self.assertRaisesRegex(ValueError,'CORE source closure'):s.associate_snapshot(dict(schema='FULL_CONDITIONAL_POOL_TRAINING_BANK_V1',source_facts=dict(consumed_source_hashes={'TRAP':'0'*64},namespace_snapshots={})),{}, {})

    def test_fixed_io_size_duplicate_nonfinite_and_temp_guard_drift(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);p=folder/'own.py';p.write_bytes(b'initial');ref=(p,s.sha(b'initial'))
            with self.assertRaisesRegex(ValueError,'byte size'):s.take_sized((*ref,999))
            self.assertEqual(s.take_sized((*ref,7)),b'initial')
            sources={str(p):ref[1]};namespaces={str(folder):s.namespace(folder)}
            self.assertEqual(s.guard(sources,namespaces)['files'],1)
            p.write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'bytes changed'):s.guard(sources,namespaces)
            p.write_bytes(b'initial');(folder/'extra_failure.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'Namespace changed'):s.guard(sources,namespaces)
        for raw in (b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":1e999}'):
            with self.assertRaises(ValueError):s.strict_document(raw)

    def test_real_junction_parent_existing_and_nested_ancestor_prewrite(self):
        for placement in ('parent','ancestor','existing'):
            with tempfile.TemporaryDirectory() as td:
                folder=Path(td);target=folder/'target';target.mkdir();link=folder/'link'
                done=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,text=True)
                self.assertEqual(done.returncode,0,done.stderr)
                try:
                    if placement=='ancestor':(target/'nested').mkdir();out=link/'nested'/'measurement'
                    elif placement=='existing':out=link
                    else:out=link/'measurement'
                    with patch.object(s,'OUT',out),patch.object(s,'take',side_effect=AssertionError('source read')):
                        with self.assertRaisesRegex(ValueError,'reparse'):s.run(execute=True,work_budget=0)
                    self.assertFalse((target/'measurement').exists())
                    if placement=='ancestor':self.assertEqual(list((target/'nested').iterdir()),[])
                    else:self.assertEqual(list(target.iterdir()),[])
                finally:os.rmdir(link)

    def test_mock_full_transport_hashref_all_domain_and_guard_counts(self):
        with tempfile.TemporaryDirectory() as td:
            out,calls,reads,guards,code=self.orchestration(Path(td))
            self.assertEqual(code,0);self.assertEqual(len(calls),1);self.assertEqual(guards,2)
            self.assertEqual(len(reads),14) # Binding+literal13, not claim-discovered paths.
            raw=(out/'independent_values.json').read_bytes();e=json.loads((out/'result.json').read_bytes())
            self.assertEqual(e['independent_values_reference']['sha256'],hashlib.sha256(raw).hexdigest())
            self.assertEqual(e['independent_values_reference']['bytes'],len(raw));self.assertNotIn('full_covariance',e)
            self.assertEqual(len(e['all78_window_domain']),78);self.assertEqual(len(e['all12_ready_unique_references']),12)
            self.assertEqual(len(e['source_blocked_window_ordinals']),51);self.assertEqual(len(e['other11_ready_unique_statuses']),11)
            self.assertEqual(e['cumulative_primitives'],2333146);self.assertFalse(e['original_certificate_independently_checked'])

    def test_mock_partial_and_after_guard_failure_retain_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            out,calls,reads,guards,code=self.orchestration(Path(td),partial=True)
            self.assertEqual(code,2);e=json.loads((out/'result.json').read_bytes());self.assertTrue(e['status'].startswith('PARTIAL_'))
            self.assertEqual(e['independent_spent'],0)
        with tempfile.TemporaryDirectory() as td:
            out,calls,reads,guards,code=self.orchestration(Path(td),after_drift=True)
            self.assertTrue((out/'independent_values.json').exists());self.assertTrue((out/'exception.json').exists());self.assertFalse((out/'result.json').exists())
            with patch.object(s,'OUT',out),patch.object(s,'take',side_effect=AssertionError('retry read')):
                with self.assertRaisesRegex(ValueError,'already exists'):s.run(execute=True,work_budget=0)

    def test_metadata_restatement_rejected_before_pure_call(self):
        changes=[lambda d:d['envelope']['full_moments_reference'].update(path='TRAP'),lambda d:d['envelope'].update(source_authenticated=True),
                 lambda d:d['envelope'].update(budget=True),lambda d:d['envelope']['source_blocked_window_ordinals'].pop(),
                 lambda d:d['measurement_start'].update(raw_replays=False),lambda d:d['root_terminal'].update(exit_code=False),
                 lambda d:d['snapshot']['source_facts']['consumed_source_hashes'].update(TRAP='0'*64)]
        for mutate in changes:
            with tempfile.TemporaryDirectory() as td:
                out,calls,reads,guards,code=self.orchestration(Path(td),mutate=mutate)
                self.assertEqual(calls,[]);self.assertEqual(guards,0)

    def test_output_reparse_at_save_does_not_write_unsafe_target(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);(folder/'unsafe_target').mkdir()
            try:
                self.orchestration(folder,reparse_at_values=True)
                self.assertEqual(list((folder/'unsafe_target').iterdir()),[])
                self.assertEqual(sorted(p.name for p in (folder/'retained_safe_start').iterdir()),['START.json'])
            finally:
                if (folder/'measurement').exists():os.rmdir(folder/'measurement')

    def test_real_small47pure_compiled_fixed_bytes_only(self):
        # Small synthetic computation; never the host run path / real77 inputs.
        raw=(ROOT/'backtest/ndx_full_pool_training_identity_readback_research.py').read_bytes();self.assertEqual(s.sha(raw),s.PURE[1])
        module=SimpleNamespace();exec(compile(raw,str(s.PURE[0]),'exec'),module.__dict__)
        p=ROOT/'tests/test_ndx_full_pool_training_identity_readback_research.py';sp=importlib.util.spec_from_file_location('bounded_identity_fixture',p);fixture=importlib.util.module_from_spec(sp);sp.loader.exec_module(fixture)
        mat=fixture.matrix();numerical=fixture.declared_producer(mat)
        result=module.verify_raw_cross_moment_identity(matrix=mat,numerical_result=numerical,work_budget=47)
        self.assertEqual(result['work']['spent'],47);self.assertTrue(result['status'].startswith('PASS_'))
        self.assertFalse(result['producer_declarations']['intermediate_maxima_independently_replayed'])

    def test_output_postmkdir_reparse_rejected_before_start(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td);target=folder/'target';target.mkdir();out=folder/'measurement'
            original=Path.mkdir
            def replaced(path,*args,**kwargs):
                if path==out:
                    done=subprocess.run(['cmd','/c','mklink','/J',str(out),str(target)],capture_output=True,text=True)
                    if done.returncode:raise RuntimeError(done.stderr)
                else:return original(path,*args,**kwargs)
            try:
                with patch.object(s,'OUT',out),patch.object(Path,'mkdir',replaced),patch.object(s,'take',side_effect=AssertionError('source')):
                    with self.assertRaisesRegex(ValueError,'reparse'):s.run(execute=True,work_budget=0)
                self.assertEqual(list(target.iterdir()),[])
            finally:
                if out.exists():os.rmdir(out)
