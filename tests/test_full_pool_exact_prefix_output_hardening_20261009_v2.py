"""Temporary Windows junction fixtures only; no actual source guard or moments."""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
RUNNER=ROOT/'tmp/full_pool_exact_prefix_runner_20261009_v2.py'
spec=importlib.util.spec_from_file_location('offline_prefix_output_v2',RUNNER)
subject=importlib.util.module_from_spec(spec);spec.loader.exec_module(subject)


def junction(link,target):
    result=subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,text=True)
    if result.returncode:
        raise AssertionError('Windows junction fixture failed: '+result.stderr)
    if not link.is_junction() or link.is_symlink():
        raise AssertionError('Expected actual Windows junction, not synthetic reparse attributes')


class OutputHardeningOffline(unittest.TestCase):
    def test_parent_real_junction_before_any_mkdir_start_or_fixed_read(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);target=base/'target';target.mkdir();link=base/'junction'
            junction(link,target)
            try:
                with patch.object(subject,'OUT',link/'measurement'),patch.object(subject,'take',side_effect=AssertionError('FIXED_READ_TRAP')) as take:
                    with self.assertRaisesRegex(ValueError,'[Rr]eparse'):subject.run(execute=True)
                    self.assertEqual(take.call_count,0)
                self.assertEqual(list(target.iterdir()),[])
            finally:os.rmdir(link)

    def test_ancestor_junction_also_rejected_before_output_probe(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);target=base/'target';target.mkdir();(target/'nested').mkdir();link=base/'junction'
            junction(link,target)
            try:
                with patch.object(subject,'OUT',link/'nested'/'measurement'),patch.object(subject,'take',side_effect=AssertionError('read')) as take:
                    with self.assertRaisesRegex(ValueError,'reparse'):subject.run(execute=True)
                    self.assertEqual(take.call_count,0)
                self.assertEqual(list((target/'nested').iterdir()),[])
            finally:os.rmdir(link)

    def test_existing_output_junction_is_never_followed_or_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);target=base/'target';target.mkdir();out=base/'measurement'
            junction(out,target)
            try:
                with patch.object(subject,'OUT',out),patch.object(subject,'take',side_effect=AssertionError('read')) as take:
                    with self.assertRaisesRegex(ValueError,'already exists'):subject.run(execute=True)
                    self.assertEqual(take.call_count,0)
                self.assertEqual(list(target.iterdir()),[])
            finally:os.rmdir(out)

    def test_postmkdir_junction_swap_rejected_before_start(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);target=base/'target';target.mkdir();out=base/'measurement'
            original=Path.mkdir
            def swapped(path,*args,**kwargs):
                original(path,*args,**kwargs)
                if path==out:
                    path.rmdir();junction(path,target)
            try:
                with patch.object(subject,'OUT',out),patch.object(Path,'mkdir',swapped),patch.object(subject,'take',side_effect=AssertionError('read')) as take:
                    with self.assertRaisesRegex(ValueError,'reparse'):subject.run(execute=True)
                    self.assertEqual(take.call_count,0)
                self.assertEqual(list(target.iterdir()),[])
            finally:
                if out.is_junction():os.rmdir(out)

    def test_save_time_junction_swap_does_not_write_failure_to_unsafe_target(self):
        with tempfile.TemporaryDirectory() as td:
            base=Path(td);target=base/'target';target.mkdir();out=base/'measurement';hold=base/'original_safe_output'
            def fixed_read_trap(reference):
                out.rename(hold);junction(out,target)
                raise ValueError('FIXED_READ_TRAP_AFTER_START')
            try:
                with patch.object(subject,'OUT',out),patch.object(subject,'take',side_effect=fixed_read_trap):
                    with self.assertRaisesRegex(ValueError,'reparse'):subject.run(execute=True)
                self.assertEqual(list(target.iterdir()),[])
                self.assertEqual([p.name for p in hold.iterdir()],['START.json'])
            finally:
                if out.is_junction():os.rmdir(out)

    def test_safe_output_failure_is_createonly_and_retry_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'measurement'
            with patch.object(subject,'OUT',out),patch.object(subject,'take',side_effect=ValueError('CONTROLLED_FIXED_READ_FAILURE')) as take:
                with self.assertRaisesRegex(ValueError,'CONTROLLED_FIXED_READ_FAILURE'):subject.run(execute=True)
                self.assertEqual(sorted(p.name for p in out.iterdir()),['START.json','exception.json'])
                failure=json.loads((out/'exception.json').read_bytes())
                self.assertEqual(failure['exception_type'],'ValueError')
                self.assertFalse(failure['completed_prefix_result_saved'])
                before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()}
                take.reset_mock()
                with self.assertRaisesRegex(ValueError,'already exists'):subject.run(execute=True)
                self.assertEqual(take.call_count,0)
                self.assertEqual(before,{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir()})

    def test_parameter_gate_before_parent_stat(self):
        with patch.object(Path,'lstat',side_effect=AssertionError('Parent probed before execute gate')):
            for value in (False,None,1,'yes'):
                with self.assertRaisesRegex(ValueError,'Explicit approved'):subject.run(execute=value)

    def test_existing_output_regular_file_is_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            out=Path(td)/'measurement';out.write_bytes(b'keep')
            with patch.object(subject,'OUT',out),patch.object(subject,'take',side_effect=AssertionError('read')):
                with self.assertRaisesRegex(ValueError,'already exists'):subject.run(execute=True)
            self.assertEqual(out.read_bytes(),b'keep')

    def test_inverse_delta_exact_and_formal_namespace_absent(self):
        raw=RUNNER.read_bytes()
        transformations=[
            (b"    regular(OUT.parent, directory=True)\n    require(not os.path.lexists(OUT), 'Measurement namespace already exists; no retry/overwrite')\n",
             b"    require(not OUT.exists(), 'Measurement namespace already exists; no retry/overwrite')\n"),
            (b'    OUT.mkdir()\n    regular(OUT, directory=True)\n',b'    OUT.mkdir()\n'),
            (b'    def save(name,value):\n        regular(OUT, directory=True)\n',b'    def save(name,value):\n')]
        for changed,original in transformations:
            self.assertEqual(raw.count(changed),1);raw=raw.replace(changed,original)
        self.assertEqual(hashlib.sha256(raw).hexdigest(),'22ada3caae65f45b6f7c2ef4e13da2aa09d8c6d4041cb0b9aaecf20287a32af9')
        self.assertFalse(subject.OUT.exists())
        import sys
        self.assertNotIn('backtest.ndx_full_pool_training_moments_research',sys.modules)
        self.assertNotIn('backtest.ndx_variable_cardinality_new_cash_source_binding_research',sys.modules)
