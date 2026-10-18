from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_observation_writer_20261009_v1 as writer
from scripts import ndx_prospective_observation_writer_v3_20261009 as previous


def parent():
    return writer.envelope(previous.PARENT_BOUND,{})


class RegisteredObservationWriterTests(unittest.TestCase):
    def test_explicit_false_and_pending_configuration_precede_io(self):
        with patch.object(writer,'consume',side_effect=AssertionError('Unexpected IO')):
            self.assertEqual(writer.run(registration_path='E:/synthetic/r.json',registration_sha256='a'*64),dict(status='NOT_EXECUTED'))
            with patch.object(writer,'REGISTRATION_CORE',(writer.REGISTRATION_CORE[0],None)):
                with self.assertRaises(ValueError):writer.run(registration_path='E:/synthetic/r.json',registration_sha256='a'*64,execute=True)

    def test_mutable_cache_claim_is_rejected_before_read(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'QQQ.csv';path.write_bytes(b'cache')
            with patch.object(writer,'CURRENT',{'QQQ':path,'SPY':Path(folder)/'SPY.csv'}),patch.object(Path,'read_bytes',side_effect=AssertionError('Live cache read')):
                with self.assertRaisesRegex(ValueError,'diagnostic only'):writer.consume(dict(path=str(path),sha256='a'*64),{})

    def test_bound_external_parent_attempt_readonly_inventory(self):
        saved=parent()
        with TemporaryDirectory() as folder:
            root=Path(folder);sources={}
            with patch.object(writer,'RESEARCH',root):found=writer.attempt_inventory(saved,sources,root/'future_observation')
            self.assertEqual(len(found),1)
            expected=saved['document']['history']['observations'][0]
            self.assertIn(expected['payload_reference']['path'],found)
            started=found[expected['payload_reference']['path']]['started.json']
            self.assertEqual(started['sha256'],expected['original_source_hash_claims']['audit'][started['path']])
            writer.guard(sources)
            self.assertEqual(list(root.iterdir()),[])

    def test_external_prior_start_must_come_from_inherited_audit(self):
        saved=parent();entry=saved['document']['history']['observations'][0]
        key=str(Path(entry['payload_reference']['path']).parent/'started.json')
        entry['original_source_hash_claims']['audit'][key]='a'*64
        with TemporaryDirectory() as folder,patch.object(writer,'RESEARCH',Path(folder)):
            with self.assertRaises(ValueError):writer.attempt_inventory(saved,{},Path(folder)/'future')

    def test_semantic_partial_attempt_cannot_hide_under_renamed_namespace(self):
        saved=parent()
        for name,document in [('started.json',dict(schema='PROSPECTIVE_OBSERVATION_WRITER_STARTED_V4')),
            ('observation_payload.json',dict(schema='PROSPECTIVE_OBSERVATION_PAYLOAD_RESEARCH_V1')),
            ('failure.json',dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY'))]:
            with self.subTest(name=name),TemporaryDirectory() as folder:
                root=Path(folder);hidden=root/'unrelated_name';hidden.mkdir();writer.save(hidden/name,document)
                with patch.object(writer,'RESEARCH',root),self.assertRaisesRegex(ValueError,'UNRESOLVED'):
                    writer.attempt_inventory(saved,{},root/'new_attempt')
                self.assertTrue((hidden/name).exists())

    def test_private_import_is_explicit_and_consumed_bytes_bound(self):
        raw=b'from somewhere import dependency\nresult=dependency+1'
        module=writer.private_module(raw,'E:/synthetic/core.py',writer.sha(raw),'_synthetic',[
            ('from somewhere import dependency','dependency',4)])
        self.assertEqual(module.result,5)
        with self.assertRaisesRegex(ValueError,'Private source SHA'):
            writer.private_module(raw+b'\n','E:/synthetic/core.py',writer.sha(raw),'_synthetic')

    def test_createonly_and_resource_failure_preserve_prior_bytes(self):
        with TemporaryDirectory() as folder:
            path=Path(folder)/'started.json';writer.save(path,dict(ok=True));before=path.read_bytes()
            with self.assertRaises(FileExistsError):writer.save(path,dict(ok=False))
            self.assertEqual(path.read_bytes(),before)
            class Disk:free=0
            with patch.object(writer.shutil,'disk_usage',return_value=Disk()):
                with self.assertRaisesRegex(ValueError,'Resource stop'):writer.save(path.parent/'receipt.json',{})
                writer.save(path.parent/'failure.json',dict(status='FAILED_REQUIRES_EXTERNAL_SHA_RECOVERY_NO_RETRY'))
            self.assertTrue(path.exists());self.assertTrue((path.parent/'failure.json').exists())
            self.assertFalse((path.parent/'receipt.json').exists())


if __name__=='__main__':unittest.main()
