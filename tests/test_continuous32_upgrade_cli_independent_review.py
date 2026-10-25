import contextlib,io,json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch,Mock
import scripts.run_continuous32_upgrade as cli

class UpgradeCliReview(unittest.TestCase):
 def arguments(self,root,mode=()):
  return ['upgrade','--root',root,'--configuration-path','config.json','--configuration-sha256','a'*64,'--package-path','upgrade.json','--package-sha256','b'*64,'--receipt-path','receipt.jsonl',*mode]
 def test_default_offline_and_create_only_receipt(self):
  with TemporaryDirectory() as root:
   with patch('sys.argv',self.arguments(root)),patch.object(cli,'run',return_value={'status':'MOCK_OFFLINE'}) as run,contextlib.redirect_stdout(io.StringIO()):
    self.assertEqual(cli.main(),0)
   args=run.call_args.args[0];self.assertFalse(args.preflight);self.assertFalse(args.execute)
   path=Path(root)/'receipt.jsonl';before=path.read_bytes()
   with patch('sys.argv',self.arguments(root)),patch.object(cli,'run') as run:
    with self.assertRaises(FileExistsError):cli.main()
    run.assert_not_called()
   self.assertEqual(path.read_bytes(),before)
 def test_mutually_exclusive_and_clock_override_rejected_before_run(self):
  with TemporaryDirectory() as root:
   for mode in (['--preflight','--execute'],['--clock','2026-10-20']):
    with patch('sys.argv',self.arguments(root,mode)),patch.object(cli,'run') as run,contextlib.redirect_stderr(io.StringIO()):
     with self.assertRaises(SystemExit) as error:cli.main()
     self.assertEqual(error.exception.code,2);run.assert_not_called()
   self.assertFalse((Path(root)/'receipt.jsonl').exists())
 def test_modes_are_explicit_failure_preserved_no_retry(self):
  for flag in ('--preflight','--execute'):
   with self.subTest(flag=flag),TemporaryDirectory() as root:
    with patch('sys.argv',self.arguments(root,[flag])),patch.object(cli,'run',side_effect=ValueError('SYNTHETIC_FAILURE')) as run,contextlib.redirect_stdout(io.StringIO()):
     self.assertEqual(cli.main(),1)
    self.assertEqual(run.call_count,1)
    rows=[json.loads(line) for line in (Path(root)/'receipt.jsonl').read_text().splitlines()]
    self.assertEqual([r['status'] for r in rows],['STARTED','FAILED_PRESERVED'])
    self.assertEqual(rows[-1]['mode'],flag[2:])
