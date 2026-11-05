import unittest,json,tempfile
from pathlib import Path
from hashlib import sha256
from copy import deepcopy
from unittest.mock import patch
from scripts.research import run_downside_account_candidate_20261105 as runner


class FreezeGuardTests(unittest.TestCase):
    def test_missing_bad_schema_cap_budget_and_source_fail_before_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);f=root/'research_contracts/downside_max10_20261105/freeze.json';f.parent.mkdir(parents=True)
            source=root/runner.RUNNER_NAME;source.parent.mkdir(parents=True);source.write_bytes(b'fixture')
            valid=dict(schema=runner.FREEZE_SCHEMA,status='READY_FOR_FIXED_MAX10_EXECUTION',max_holdings=10,windows={'2021_2023':36,'2024_2026':31},seconds_per_window=10800,seconds_per_month=600,source_hashes={runner.RUNNER_NAME:sha256(source.read_bytes()).hexdigest()})
            with patch.object(runner,'ROOT',root):
                with self.assertRaises(FileNotFoundError):runner.run('2021_2023','tmp/output')
                for key,value in [('schema','BAD'),('max_holdings',102),('seconds_per_month',601),('seconds_per_window',1800),('windows',{'2021_2023':37})]:
                    altered=deepcopy(valid);altered[key]=value;f.write_text(json.dumps(altered),encoding='utf-8')
                    with self.subTest(key=key),self.assertRaises(ValueError):runner.run('2021_2023','tmp/output')
                    self.assertFalse((root/'tmp/output').exists())
                f.write_text(json.dumps(valid),encoding='utf-8');self.assertEqual(runner.validate_execution_freeze(root),valid)
                source.write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'SOURCE_CHANGED'):runner.run('2021_2023','tmp/output')
                self.assertFalse((root/'tmp/output').exists())


if __name__=='__main__':unittest.main()
