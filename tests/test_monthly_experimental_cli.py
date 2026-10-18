import io
import json
import unittest
from contextlib import redirect_stdout
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.monthly_experimental_domain_capture import run
from scripts.prepare_monthly_captured_training import main as prepare_main
from scripts.publish_monthly_market_configuration import main as publish_main
from test_monthly_experimental_domain_capture import fixture
from test_publish_monthly_market_configuration import inputs


class ExperimentalCliTests(unittest.TestCase):
    def test_real_capture_prepare_and_publish_cli_opt_in(self):
        with TemporaryDirectory() as folder:
            publisher_root=Path(folder)/'publisher-fixture';publisher_root.mkdir()
            request=inputs(publisher_root)
            args,plan,plan_hash,fetch,calls=fixture(folder)
            root=Path(folder)
            for path in request['supplemental_hashes']:
                (root/path).write_bytes((publisher_root/path).read_bytes())
            result=run('experiment.json',plan_hash,root=root,clock=args['clock'],capture=True,fetch=fetch)
            self.assertEqual(result['status'],'EXPERIMENTAL_DOMAIN_CAPTURED_NOT_ADMITTED')
            index='actual-capture/completion_index.json'
            preparation=dict(previous_manifest_path='previous.json',previous_manifest_sha256=plan['previous_manifest_sha256'],
                capture_index_path=index,capture_index_sha256=sha256((root/index).read_bytes()).hexdigest(),
                plan_path='experiment.json',plan_sha256=plan_hash)
            argv=['--root',str(root),'--output',str(root/'prepared')]
            for key,value in preparation.items():argv.extend(['--'+key.replace('_','-'),value])
            with patch('scripts.prepare_monthly_captured_training.utc_now',args['clock']):
                with self.assertRaises(ValueError):prepare_main(argv)
                self.assertFalse((root/'prepared').exists())
                with redirect_stdout(io.StringIO()) as stdout:prepare_main(argv+['--experimental-domain'])
            self.assertEqual(json.loads(stdout.getvalue())['domain_mode'],'EXPERIMENTAL_FIXED_DOMAIN_NOT_PRODUCTION_ADMISSION')
            self.assertEqual(set(json.loads((root/'prepared/input.json').read_bytes())['search_arguments']['prices']),{'B'})
            request['preparation_arguments']=preparation
            review=json.loads((root/'review.json').read_bytes());review['reviewed_members']=['BBB']
            raw=json.dumps(review).encode();(root/'review.json').write_bytes(raw)
            request['supplemental_hashes']['review.json']=sha256(raw).hexdigest()
            raw=json.dumps(request).encode();(root/'request.json').write_bytes(raw)
            argv=['--root',str(root),'--request','request.json','--request-sha256',sha256(raw).hexdigest()]
            with patch('scripts.publish_monthly_market_configuration.datetime') as clock:
                clock.now.side_effect=lambda *a:args['clock']()
                with redirect_stdout(io.StringIO()):self.assertEqual(publish_main(argv),1)
                self.assertFalse((root/'published').exists())
                with redirect_stdout(io.StringIO()) as stdout:
                    self.assertEqual(publish_main(argv+['--experimental-domain']),0)
            published=json.loads(stdout.getvalue())
            self.assertEqual(published['domain_mode'],'EXPERIMENTAL_FIXED_DOMAIN_NOT_PRODUCTION_ADMISSION')
            self.assertFalse(published['service_activated']);self.assertFalse(published['account_writes'])
            self.assertEqual(len(calls),1)


if __name__=='__main__':unittest.main()
