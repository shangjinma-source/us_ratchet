from datetime import timedelta
from hashlib import sha256
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
import test_registered_quantity_v2_paper_protocol as fixtures
from scripts import register_quantity_v2_paper_protocol as registrar


def setup(root):
    args,request,save=fixtures.fixture(root)
    for relative,source in [(registrar.REGISTRAR,Path(registrar.__file__)),(registrar.CORE,Path(registrar.core.__file__))]:
        destination=Path(root)/relative;destination.parent.mkdir(parents=True,exist_ok=True)
        destination.write_bytes(source.read_bytes())
        request['source_hashes'][relative]=sha256(destination.read_bytes()).hexdigest()
    ref=save('request.json',request)
    return dict(root=root,request_path='request.json',expected_request_sha256=ref['sha256'],clock=lambda:args['now']),request,args['now']


class RegistrarTests(unittest.TestCase):
    def test_direct_cli_help_from_unrelated_directory(self):
        with TemporaryDirectory() as folder:
            result=subprocess.run([sys.executable,'-E','-B',str(Path(registrar.__file__).resolve()),'--help'],
                cwd=folder,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertIn('--request-sha256',result.stdout)

    def test_readonly_then_create_only_no_account(self):
        with TemporaryDirectory() as root:
            args,request,now=setup(root);before=sorted(str(x) for x in Path(root).rglob('*'))
            self.assertEqual(registrar.run(**args)['status'],'PREFLIGHT_ONLY')
            self.assertEqual(before,sorted(str(x) for x in Path(root).rglob('*')))
            result=registrar.run(**args,execute=True)
            self.assertEqual(result['status'],'REGISTERED_NOT_ACTIVATED')
            output=Path(root)/'registration'
            self.assertEqual((output/'request.json').read_bytes(),(Path(root)/'request.json').read_bytes())
            receipt=json.loads((output/'receipt.json').read_bytes())
            self.assertEqual(receipt['request_sha256'],args['expected_request_sha256'])
            self.assertFalse(Path(request['identity']['database_path']).exists())
            self.assertFalse((Path(root)/registrar.LOCK).exists())
            with self.assertRaisesRegex(ValueError,'ATTEMPT_EXISTS'):registrar.run(**args,execute=True)

    def test_lock_collision_preserves_failed_attempt(self):
        with TemporaryDirectory() as root:
            args,_,_=setup(root);lock=Path(root)/registrar.LOCK
            lock.parent.mkdir(parents=True);lock.write_bytes(b'other owner')
            with self.assertRaisesRegex(ValueError,'RUN_LOCK_PRESENT'):registrar.run(**args,execute=True)
            self.assertEqual(lock.read_bytes(),b'other owner')
            self.assertTrue((Path(root)/'registration/failed.json').exists())
            self.assertFalse((Path(root)/'registration/complete.json').exists())
            with self.assertRaisesRegex(ValueError,'ATTEMPT_EXISTS'):registrar.run(**args,execute=True)

    def test_clock_rollback_preserves_failure_without_completion(self):
        with TemporaryDirectory() as root:
            args,_,now=setup(root)
            values=iter([now,now+timedelta(seconds=2),now+timedelta(seconds=1)])
            args['clock']=lambda:next(values)
            with self.assertRaisesRegex(ValueError,'CLOCK_ROLLBACK'):registrar.run(**args,execute=True)
            output=Path(root)/'registration'
            self.assertTrue((output/'started.json').exists());self.assertTrue((output/'failed.json').exists())
            self.assertFalse((output/'complete.json').exists())

    def test_account_appearing_after_started_blocks(self):
        with TemporaryDirectory() as root:
            args,request,_=setup(root);original=registrar.save
            def save(path,value):
                original(path,value)
                if path.name=='started.json':Path(request['identity']['database_path']).write_bytes(b'foreign')
            with patch.object(registrar,'save',side_effect=save):
                with self.assertRaisesRegex(ValueError,'DATABASE_EXISTS'):registrar.run(**args,execute=True)
            self.assertEqual(Path(request['identity']['database_path']).read_bytes(),b'foreign')
            self.assertFalse((Path(root)/'registration/receipt.json').exists())

    def test_cleanup_failure_retains_lock_and_complete_requires_reconciliation(self):
        with TemporaryDirectory() as root:
            args,_,_=setup(root);original=Path.unlink
            def unlink(path,*a,**kw):
                if path.name=='running.lock':raise OSError('synthetic cleanup failure')
                return original(path,*a,**kw)
            with patch.object(Path,'unlink',unlink):
                with self.assertRaisesRegex(ValueError,'LOCK_RECONCILIATION'):registrar.run(**args,execute=True)
            self.assertTrue((Path(root)/registrar.LOCK).exists())
            self.assertTrue((Path(root)/'registration/complete.json').exists())
            self.assertTrue((Path(root)/'registration/lock_cleanup_failed.json').exists())
            with self.assertRaisesRegex(ValueError,'ATTEMPT_EXISTS'):registrar.run(**args,execute=True)

    def test_external_hash_and_executable_pins_not_self_approved(self):
        for mode in ('request','registrar'):
            with self.subTest(mode=mode),TemporaryDirectory() as root:
                args,_,_=setup(root)
                if mode=='request':args['expected_request_sha256']='0'*64
                else:(Path(root)/registrar.REGISTRAR).write_bytes(b'changed after approval')
                with self.assertRaises(ValueError):registrar.run(**args,execute=True)
                self.assertFalse((Path(root)/'registration').exists())


if __name__=='__main__':unittest.main()
