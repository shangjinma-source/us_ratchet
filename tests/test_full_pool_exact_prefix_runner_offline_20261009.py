"""Offline fixtures only: no actual source guard, reader, inspector or moments call."""
from copy import deepcopy
from pathlib import Path
import hashlib
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/'tmp/full_pool_exact_prefix_runner_20261009_v1.py'
spec=importlib.util.spec_from_file_location('prepared_prefix_runner_offline',RUNNER)
subject=importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)


class OfflinePrefixGuards(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.temp.name)
        def file(folder,name,raw=b'fixture'):
            directory=cls.root/folder;directory.mkdir(exist_ok=True)
            p=directory/name;p.write_bytes(raw)
            return dict(path=str(p),sha256=hashlib.sha256(raw).hexdigest())
        cls.core=file('core','source.json')
        cls.bridge=file('bridge','bridge.json')
        cls.failed=file('failed','failure.json',b'fixed old failed evidence not admitted')
        file('failed','started.json')
        cls.hosts=[]
        for i in range(8):
            r=file('anchors',f'anchor{i}.json');cls.hosts.append((Path(r['path']),r['sha256']))
        roles={}
        for i in range(257):
            key=subject.BRIDGE_ROLE if i==0 else f'core.{i}'
            roles[key]=dict(profile='CORE',reference=deepcopy(cls.bridge if i==0 else cls.core))
        roles['failed.original']=dict(profile='CORE_PRESERVED_FAILED_EVIDENCE_ONLY',reference=deepcopy(cls.failed))
        for i in range(33):
            roles[f'optional.{i}']=dict(profile='OPTIONAL_SAVED_DUAL_NUMBERS',reference=dict(path=str(cls.root/f'NEVER_READ_{i}'),sha256='0'*64))
        namespaces={f'core{i}':dict(profile='CORE',path=str(cls.root/'core'),expected_direct_regular_files=['source.json']) for i in range(4)}
        namespaces['fixed_failed']=dict(profile='CORE_PRESERVED_FAILED_EVIDENCE_ONLY',path=str(cls.root/'failed'),expected_direct_regular_files=['failure.json','started.json'])
        for i in range(4):
            namespaces[f'optional{i}']=dict(profile='OPTIONAL_SAVED_DUAL_NUMBERS',path=str(cls.root/f'optional_ns{i}'),expected_direct_regular_files=[])
        cls.catalogue=dict(schema='CONDITIONAL_FULL_POOL_FIXED_HOST_ROLE_CATALOGUE_DESIGN_V1',roles=roles,
                           channel_order=[{} for _ in range(77)],namespaces=namespaces)
        raw=cls.root/'raw';raw.mkdir()
        entries=[]
        for i in range(511):
            name=f'raw_{i:03d}.json';(raw/name).write_bytes(b'')
            entries.append(dict(name=name,type='regular_file',reparse_point=False))
        cls.supplement=dict(schema='FIXED_HOST_CATALOGUE_SUPPLEMENT_DESIGN_V1',raw_capture_namespace=dict(path=str(raw),expected_direct_entries=entries))
        cls.sources,cls.namespaces=subject.derive_closure(cls.catalogue,cls.supplement,cls.hosts)
        cls.snapshot=dict(schema='FULL_CONDITIONAL_POOL_TRAINING_BANK_V1',source_facts=dict(
            consumed_source_hashes=deepcopy(cls.sources),namespace_snapshots=deepcopy(cls.namespaces)))

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_fixed_failed_evidence_preserved_optional_not_read(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Pure closure attempted IO')):
            sources,namespaces=subject.derive_closure(self.catalogue,self.supplement,self.hosts)
            subject.associate_snapshot(self.snapshot,sources,namespaces)
        self.assertEqual(len(sources),11)
        self.assertEqual(len(namespaces),4)
        self.assertIn(self.failed['path'],sources)
        self.assertEqual([x['name'] for x in namespaces[str(self.root/'failed')]],['failure.json','started.json'])
        # Only temporary fixture sources/namespaces are guarded; original failure names are allowed.
        self.assertEqual(subject.guard(sources,namespaces)['files'],11)

    def test_claim_extra_and_missing_refs_rejected_before_trap(self):
        for mutate in (lambda s:s['source_facts']['consumed_source_hashes'].update({str(self.root/'TRAP'):'0'*64}),
                       lambda s:s['source_facts']['consumed_source_hashes'].pop(self.core['path']),
                       lambda s:s['source_facts']['namespace_snapshots'].update({str(self.root/'TRAP_NS'):[]})):
            snap=deepcopy(self.snapshot);mutate(snap)
            with (patch.object(Path,'read_bytes',side_effect=AssertionError('Claim followed')),
                  self.assertRaisesRegex(ValueError,'independently derived')):
                subject.associate_snapshot(snap,self.sources,self.namespaces)

    def test_coordinated_claim_digest_rejected(self):
        snap=deepcopy(self.snapshot)
        snap['source_facts']['consumed_source_hashes'][self.core['path']]='f'*64
        snap['self_digest']='caller re-signed'
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),self.assertRaises(ValueError):
            subject.associate_snapshot(snap,self.sources,self.namespaces)
        snap=deepcopy(self.snapshot)
        first=next(iter(snap['source_facts']['namespace_snapshots'].values()))
        first[0]['reparse_point']=0
        with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),self.assertRaises(ValueError):
            subject.associate_snapshot(snap,self.sources,self.namespaces)

    def test_catalogue_type_profiles_alias_pin_and_namespace_paths(self):
        changes=[lambda c:c['roles']['core.1'].update(profile='CORE_ARBITRARY_NEW'),
                 lambda c:c['roles']['core.1']['reference'].update(path='relative.json'),
                 lambda c:c['roles']['core.1']['reference'].update(sha256=True),
                 lambda c:c['roles']['optional.0'].update(reference=dict(path=self.core['path'],sha256='0'*64)),
                 lambda c:c['namespaces']['core0'].update(expected_direct_regular_files=['../trap']),
                 lambda c:c['namespaces']['core0'].update(expected_direct_regular_files=['source.json','source.json'])]
        for mutate in changes:
            c=deepcopy(self.catalogue);mutate(c)
            with patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),self.assertRaises(ValueError):
                subject.derive_closure(c,self.supplement,self.hosts)

    def test_source_drift_restore_and_owncode_guard(self):
        for reference in (self.core,dict(path=str(self.root/'synthetic_own_code.py'),sha256=hashlib.sha256(b'code').hexdigest())):
            p=Path(reference['path'])
            if not p.exists():p.write_bytes(b'code')
            before=p.read_bytes()
            p.write_bytes(before+b'changed')
            try:
                with self.assertRaisesRegex(ValueError,'Fixed source bytes changed'):
                    subject.guard({reference['path']:reference['sha256']},{})
            finally:p.write_bytes(before)
            self.assertEqual(subject.guard({reference['path']:reference['sha256']},{})['files'],1)

    def test_extra_failure_namespace_rejected_and_restored(self):
        extra=self.root/'failed'/'unexpected_failure.json'
        extra.write_bytes(b'')
        try:
            with self.assertRaisesRegex(ValueError,'Namespace changed'):
                subject.guard(self.sources,self.namespaces)
        finally:extra.unlink()
        self.assertEqual(subject.guard(self.sources,self.namespaces)['namespaces'],4)

    def test_symlink_regular_gate_if_os_supports_it(self):
        link=self.root/'fixture_link.json'
        try:link.symlink_to(Path(self.core['path']))
        except OSError:return
        try:
            with self.assertRaisesRegex(ValueError,'Symlink/reparse'):
                subject.take((link,self.core['sha256']))
        finally:link.unlink()

    def test_parameters_default_and_false_never_create_measurement_or_read(self):
        before=subject.OUT.exists()
        with patch.object(Path,'read_bytes',side_effect=AssertionError('Read before explicit gate')):
            for value in (False,None,1,'true',{}):
                with self.assertRaisesRegex(ValueError,'Explicit approved'):
                    subject.run(execute=value)
        self.assertEqual(subject.OUT.exists(),before)
        self.assertFalse(before)

    def test_strict_json_duplicate_nonfinite_and_utf8(self):
        for raw in (b'{"x":1,"x":2}',b'NaN',b'1e400',b'"\xff"'):
            with self.assertRaises((ValueError,UnicodeError)):
                subject.strict_document(raw)
        self.assertEqual(subject.strict_document(b'{"exact":"1/3"}'),{'exact':'1/3'})

    def test_fixed_matrix_selection_shape_refs_and_all_domain_not_math(self):
        matrix=dict(model_id=subject.MODEL,shape=[126,77],ordered_security_ids=[f'S{i}' for i in range(77)],
                    training_dates=[str(i) for i in range(126)],cells=[['0']*77 for _ in range(126)])
        matrices=[dict(numerical_status='SOURCE_BLOCKED') for _ in range(11)]
        for i in range(12):
            matrices.append(dict(numerical_status='NUMERIC_READY_NOT_SOURCE_QUALIFIED',matrix_sha256=subject.sha(subject.encoded(matrix)),
                                 window_ordinals=[11,23,59,71] if i==0 else [],matrix=matrix,moments=None))
        coverage=dict(zip(('securities','issuers','original_provenance','windows','sid_window_cells','training_cell_coordinates',
                          'training_numeric_ready_windows','blocked_training_windows','unique_numeric_ready_matrices'),
                         (77,76,101,78,6006,756756,27,51,12)))
        snap=dict(coverage=coverage,windows=[dict(unique_matrix_index=11) for _ in range(78)],source_columns=[{}]*77,
                  permissions={'allowed':False},qualified_inventory=None,qualified_denominator=None,current_account=None,
                  current_new_money=None,plan_rows=[],real_joint_objective='UNREGISTERED',causal_action_rule='UNREGISTERED',
                  thirteen_cohort_prior_cash='SOURCE_BLOCKED',unique_training_matrices=matrices)
        with patch.object(subject,'MATRIX_SHA',subject.sha(subject.encoded(matrix))),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            chosen,ready=subject.choose_matrix(snap)
            self.assertIs(chosen,matrix);self.assertEqual(len(ready),12)
            bad=deepcopy(snap);bad['windows'][23]['unique_matrix_index']=12
            with self.assertRaisesRegex(ValueError,'Window matrix relation'):subject.choose_matrix(bad)
            bad=deepcopy(snap);bad['unique_training_matrices'][11]['matrix']['cells'][0][0]='1/2'
            with self.assertRaisesRegex(ValueError,'matrix payload'):subject.choose_matrix(bad)
            bad=deepcopy(snap);bad['coverage']['securities']=75
            with self.assertRaisesRegex(ValueError,'Whole snapshot'):subject.choose_matrix(bad)
        # Synthetic matrix was never passed to a moments helper; no original modules imported.
        import sys
        self.assertNotIn('backtest.ndx_full_pool_training_moments_research',sys.modules)
        self.assertNotIn('backtest.ndx_variable_cardinality_new_cash_source_binding_research',sys.modules)
