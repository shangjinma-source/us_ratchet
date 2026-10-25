from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from scripts.prepare_paper_first_templates_v2 import prepare


class FirstTemplatePreparationTests(unittest.TestCase):
    def inputs(self, folder):
        root = Path(folder)
        def write(name,value):
            raw = canonical(value)
            (root/name).write_bytes(raw)
            return dict(path=name,sha256=sha256(raw).hexdigest())
        evidence = write('evidence.json',dict(source='synthetic identity evidence'))
        identity = write('identity.json',dict(candidates=[dict(ticker='B',security_id='B',
            status='READY_CONDITIONAL',identity_reviewed=True,identity_source_references=['evidence.json'])],
            source_hashes={'evidence.json':evidence['sha256']}))
        training = write('training.json',dict(admission=dict(members=['B'],decision_date='2026-10-14')))
        calendar = write('calendar.json',dict(schema='FIXED_EXCHANGE_SESSIONS_V1',exchange='NASDAQ',
            sessions=[dict(date='2026-10-14')]))
        return dict(root=root,output='prepared',training_reference=training,
                    identity_reference=identity,calendar_reference=calendar)

    def test_isolated_templates_have_no_fabricated_parent(self):
        with TemporaryDirectory() as folder:
            args = self.inputs(folder)
            result = prepare(**args)
            self.assertEqual(result['candidate_count'],1)
            self.assertFalse(result['daily_evidence_approved'])
            reference = result['daily_sources']['B']['configuration']
            raw = (Path(folder)/'prepared'/reference['path']).read_bytes()
            self.assertEqual(sha256(raw).hexdigest(),reference['sha256'])
            self.assertEqual(json.loads(raw)['security_id'],'B')
            self.assertNotIn('parent',result['daily_sources']['B'])
            for name,digest in result['source_sha256'].items():
                self.assertEqual(sha256((Path(folder)/'prepared'/name).read_bytes()).hexdigest(),digest)
            with self.assertRaisesRegex(ValueError,'OUTPUT_MUST_BE_NEW'):
                prepare(**args)

    def test_changed_identity_source_fails_before_output(self):
        with TemporaryDirectory() as folder:
            args = self.inputs(folder)
            (Path(folder)/'evidence.json').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'IDENTITY_SOURCE_CHANGED'):
                prepare(**args)
            self.assertFalse((Path(folder)/'prepared').exists())


if __name__=='__main__':
    unittest.main()
