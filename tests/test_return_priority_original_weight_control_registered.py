import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import return_priority_original_weight_control_registered as runner

class RegisteredControlTests(unittest.TestCase):
    def fixture(self, root, fail=False):
        def write(name,obj):
            p=root/name;p.parent.mkdir(parents=True,exist_ok=True)
            p.write_text(json.dumps(obj),encoding='utf-8')
            return hashlib.sha256(p.read_bytes()).hexdigest()
        component=root/runner.COMPONENT;component.parent.mkdir(parents=True,exist_ok=True)
        component.write_text("def execute_control(**kwargs):\n    "+("raise RuntimeError('synthetic failure')" if fail else "return {'synthetic': True}")+"\n")
        pins={runner.COMPONENT:hashlib.sha256(component.read_bytes()).hexdigest(),runner.PROPOSAL:write(runner.PROPOSAL,{}),runner.BINDING:write(runner.BINDING,{})}
        protected={n:write(n,{}) for n in runner.PROTECTED}
        write(runner.RUNNER,{})
        loaded=hashlib.sha256((root/runner.RUNNER).read_bytes()).hexdigest()
        draft={'source_hashes':pins,'protected_before':protected}
        draftsha=write('draft.json',draft)
        write('review.json',dict(status='PASS_CONDITIONAL_INPUT_AND_SYNTHETIC_MECHANICS_REQUIRES_SEPARATE_RUN_REGISTRATION',independent_review=True,reviewed_source_hashes={**pins,'draft.json':draftsha}))
        write('gate.json',dict(status='PASS',root_checked=True,reviewed_source_hashes={runner.RUNNER:loaded}))
        return loaded

    def test_stub_once_and_retry_refused(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);loaded=self.fixture(root)
            with patch.object(runner,'ROOT',root),patch.object(runner,'LOADED_SHA',loaded),patch.object(runner,'scope'):
                runner.register(draft_path='draft.json',review_path='review.json',runner_review_path='gate.json',output='out')
                sha=runner.digest('out/registration.json')
                self.assertEqual(runner.run(directory='out',registration_sha256=sha),{'synthetic':True})
                self.assertTrue(json.loads((root/'out/protected_after.json').read_text())['unchanged'])
                with self.assertRaisesRegex(ValueError,'ALREADY_STARTED'):runner.run(directory='out',registration_sha256=sha)

    def test_failure_preserved_and_no_retry(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);loaded=self.fixture(root,True)
            with patch.object(runner,'ROOT',root),patch.object(runner,'LOADED_SHA',loaded),patch.object(runner,'scope'):
                runner.register(draft_path='draft.json',review_path='review.json',runner_review_path='gate.json',output='out')
                sha=runner.digest('out/registration.json')
                with self.assertRaisesRegex(RuntimeError,'synthetic'):runner.run(directory='out',registration_sha256=sha)
                self.assertTrue((root/'out/failure.json').is_file());self.assertTrue((root/'out/protected_after.json').is_file())
                with self.assertRaisesRegex(ValueError,'ALREADY_STARTED'):runner.run(directory='out',registration_sha256=sha)

    def test_changed_input_and_cached_method_rejected(self):
        import sys,types
        with TemporaryDirectory() as tmp:
            root=Path(tmp);loaded=self.fixture(root)
            with patch.object(runner,'ROOT',root),patch.object(runner,'LOADED_SHA',loaded),patch.object(runner,'scope'):
                runner.register(draft_path='draft.json',review_path='review.json',runner_review_path='gate.json',output='out')
                sha=runner.digest('out/registration.json')
                name=runner.COMPONENT[:-3].replace('/','.')
                with patch.dict(sys.modules,{name:types.ModuleType(name)}):
                    with self.assertRaisesRegex(ValueError,'CACHED_METHOD'):runner.run(directory='out',registration_sha256=sha)
                (root/runner.PROPOSAL).write_text('{"changed":true}')
                with self.assertRaisesRegex(ValueError,'PIN_CHANGED'):runner.run(directory='out',registration_sha256=sha)
                self.assertFalse((root/'out/started.json').exists())

    def test_captured_bytes_do_not_reopen_method(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);self.fixture(root)
            with patch.object(runner,'ROOT',root):
                captured=runner.method_bytes()
                (root/runner.COMPONENT).write_text("raise RuntimeError('changed on disk')")
                with runner.isolated(captured) as module:self.assertEqual(module.execute_control(),{'synthetic':True})

    def test_actual_saved_scope_read_only(self):
        draft=json.loads((runner.ROOT/'research_contracts/original_weight_next12_control_draft_20261015_v1.json').read_bytes())
        proposal=json.loads((runner.ROOT/runner.PROPOSAL).read_bytes());binding=json.loads((runner.ROOT/runner.BINDING).read_bytes())
        runner.scope(draft,proposal,binding)
        proposal['proposed_account']['initial_cash']='25000'
        with self.assertRaisesRegex(ValueError,'CAPITAL'):runner.scope(draft,proposal,binding)

if __name__=='__main__':unittest.main()
