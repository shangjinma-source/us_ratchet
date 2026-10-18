from copy import deepcopy
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_compact_history_runtime_20261009_v1 as runtime


class RegisteredCompactRuntimeTest(unittest.TestCase):
    def test_explicit_execute_and_pending_binding_do_not_create_output(self):
        with TemporaryDirectory() as folder:
            registration=Path(folder)/'registration.json'
            registration.write_text('{}')
            digest=hashlib.sha256(registration.read_bytes()).hexdigest()
            with self.assertRaisesRegex(ValueError,'Explicit'):
                runtime.run(registration_path=str(registration),registration_sha256=digest)
            with patch.object(runtime,'REGISTRATION_CORE',(runtime.REGISTRATION_CORE[0],None)):
                with self.assertRaisesRegex(ValueError,'Pending'):
                    runtime.run(registration_path=str(registration),registration_sha256=digest,execute=True)
            self.assertEqual([p.name for p in Path(folder).iterdir()],['registration.json'])

    def test_duplicate_keys_and_nonfinite_registration_reject(self):
        for raw in [b'{"a":1,"a":2}',b'{"a":NaN}',b'{"a":Infinity}']:
            with self.subTest(raw=raw),self.assertRaises(ValueError):runtime.decode(raw)

    def test_saved_sources_require_exact_bytes_no_failure_or_link(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'source.json';path.write_bytes(b'old')
            ref=runtime.reference(path,hashlib.sha256(b'old').hexdigest())
            self.assertEqual(runtime.consume(ref,{}),b'old')
            path.write_bytes(b'new')
            with self.assertRaisesRegex(ValueError,'Source bytes'):runtime.consume(ref,{})
            path.write_bytes(b'old');(path.parent/'failure.json').write_text('{}')
            with self.assertRaisesRegex(ValueError,'Failed source'):runtime.consume(ref,{})

    def test_inventory_rejects_new_file_and_detects_started_drift(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'started.json').write_bytes(b'original');sources={}
            runtime.namespace(root,{'started.json'},sources)
            (root/'started.json').write_bytes(b'changed')
            with self.assertRaises(ValueError):runtime.namespace(root,{'started.json'},sources)
            (root/'unexpected.json').write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'Exact immutable'):runtime.namespace(root,{'started.json'},sources)

    def test_accounted_baseline_cannot_impersonate_last_actual(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);header=b'Date,Open,High,Low,Close,Volume\n'
            row=lambda date:(date+',1,1,1,1,1\n').encode()
            old=root/'old.csv';old.write_bytes(header+row('2026-10-02'))
            current=root/'accounted.csv';current.write_bytes(old.read_bytes()+row('2026-10-05'))
            refs=lambda p:runtime.reference(p,hashlib.sha256(p.read_bytes()).hexdigest())
            view=dict(known_typed_rows=[dict(session='2026-10-02'),dict(session='2026-10-05')],
                last_observed_session='2026-10-02',baseline_references={t:refs(old)for t in ('QQQ','SPY')},
                accounted_baseline_references={t:refs(current)for t in ('QQQ','SPY')})
            runtime.verify_baselines(view,{})
            forged=deepcopy(view);forged['baseline_references']=forged['accounted_baseline_references']
            with self.assertRaisesRegex(ValueError,'last actual baseline'):runtime.verify_baselines(forged,{})
            forged=deepcopy(view);forged['accounted_baseline_references']=forged['baseline_references']
            with self.assertRaisesRegex(ValueError,'accounted baseline'):runtime.verify_baselines(forged,{})

    def test_private_dependency_uses_consumed_module_instead_of_sys_modules(self):
        helper=runtime.compile_private('E:/synthetic/helper.py',b'value=7')
        raw=b'from backtest import ndx_prospective_observation_parent_history_research as compact\nvalue=compact.value'
        module=runtime.compile_private('E:/synthetic/core.py',raw,dict(compact=helper),
            'from backtest import ndx_prospective_observation_parent_history_research as compact')
        self.assertEqual(module.value,7)
        with self.assertRaisesRegex(ValueError,'One explicit'):
            runtime.compile_private('E:/synthetic/core.py',raw+raw,dict(compact=helper),
                'from backtest import ndx_prospective_observation_parent_history_research as compact')

    def test_save_is_create_only_and_resource_gate_precedes_file(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'history.json'
            runtime.save(path,dict(ok=True))
            with self.assertRaises(FileExistsError):runtime.save(path,dict(ok=False))
            target=Path(folder)/'publication.json'
            class Disk: free=0
            with patch.object(runtime.shutil,'disk_usage',return_value=Disk()):
                with self.assertRaisesRegex(ValueError,'Resource stop'):runtime.save(target,{})
            self.assertFalse(target.exists())


if __name__=='__main__':unittest.main()
