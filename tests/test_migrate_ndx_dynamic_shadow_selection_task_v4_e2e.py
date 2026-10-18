"""Full installer control flow with strict in-memory scheduler and CLI protocol stubs.

These tests do not prove Windows execution or activation: those external boundaries
are isolated. The production installer bytes, guards, rollback and evidence I/O run.
"""
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_migrate_ndx_dynamic_shadow_selection_task_v4 import SCRIPT, XML

HELPER = Path(__file__).with_name('fixture_runtime_v4_installer.ps1')
OLD = 'us_ratchet_ndx_dynamic_shadow_selection_daily_v3_reviewed_calendar'
NEW = 'us_ratchet_ndx_dynamic_shadow_selection_daily_v4_accepted_receipts'

class FullInstallerTests(unittest.TestCase):
    def exercise(self, scenario):
        with tempfile.TemporaryDirectory(prefix='ratchet-installer-') as directory:
            root = Path(directory)
            scripts = root / 'scripts'
            scripts.mkdir()
            shutil.copyfile(SCRIPT, scripts / SCRIPT.name)
            self.assertEqual(SCRIPT.read_bytes(), (scripts / SCRIPT.name).read_bytes())
            baseline = XML.replace(r'E:\Git\us_ratchet', str(root))
            if scenario == 'omitted_enabled':
                baseline = baseline.replace('<Enabled>true</Enabled>', '')
            (root / 'baseline.xml').write_text(baseline, encoding='utf-8')
            protected = ('config/config.yaml', 'data/state.json', 'data/broker_positions.json')
            for name in protected:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'fixture protected bytes\n')
            evidence = root / 'data/cache/research/ndx_dynamic_shadow_task_migration_v4'
            evidence.mkdir(parents=True)
            (evidence / 'review_draft.json').write_text('{}', encoding='utf-8')
            stubs = {
                'ndx_dynamic_shadow_runtime_v4_migration.py': "import json; print(json.dumps({'status':'READY_FOR_V4_MIGRATION_REVIEW_ONLY'}))",
                'ndx_dynamic_shadow_runtime_v4_migration_review.py': "import json; print(json.dumps({'review_sha256':'a'*64,'status':'REVIEW_DRAFT_NOT_AUTHORIZATION','missing_required_components':[],'activation_snapshot':{'sha256':'b'*64}}))",
                'ndx_dynamic_shadow_runtime_v4_task_evidence.py': "import sys,json,datetime\nif '--snapshot' in sys.argv: print(json.dumps({'captured_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}))\nelse:\n print(json.dumps({'artifact_verification':{'evidence_level':'PRE_DECISION_OPERATIONAL_ONLY'}}))\n sys.exit(" + ('2' if scenario == 'smoke_fail' else '0') + ')\n',
            }
            for name, source in stubs.items():
                (scripts / name).write_text(source, encoding='utf-8')
            result = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-File', str(HELPER), '-FixtureRoot', str(root), '-Scenario', scenario], capture_output=True, text=True, timeout=40)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = json.loads(result.stdout)
            for name in protected:
                self.assertEqual((root / name).read_bytes(), b'fixture protected bytes\n')
            self.assertTrue((evidence / 'attempts').exists(), output['failure'])
            attempts = list((evidence / 'attempts').iterdir())
            self.assertEqual(len(attempts), 1, output)
            output['evidence'] = {p.name: json.loads(p.read_text(encoding='utf-8')) for p in attempts[0].glob('*.json')}
            for call in output['calls']:
                if ':' in call:
                    self.assertIn(call.split(':', 1)[1], (OLD, NEW))
            return output

    def test_success_full_main(self):
        result = self.exercise('success')
        self.assertFalse(result['failed'], result)
        self.assertEqual(result['calls'], ['register', 'disable:'+OLD, 'enable:'+NEW, 'start:'+NEW])
        self.assertIn('post_cutover.json', result['evidence'])
        marker = result['evidence']['pre_cutover.json']['ownership_marker']
        self.assertIn(marker, result['tasks'][NEW]['Xml'])

    def test_windows_export_omitted_enabled_defaults(self):
        result = self.exercise('omitted_enabled')
        self.assertFalse(result['failed'], result)
        self.assertEqual(result['calls'], ['register', 'disable:'+OLD, 'enable:'+NEW, 'start:'+NEW])
        self.assertGreaterEqual(result['new_default_exports'], 2)

    def test_register_uncertain_and_foreign_collision(self):
        for case in ('register_before', 'register_after', 'collision'):
            with self.subTest(case=case):
                result = self.exercise(case)
                self.assertTrue(result['failed'])
                self.assertEqual(result['tasks'][OLD]['State'], 'Ready')
                self.assertIn('rollback.json', result['evidence'])
                expected = ['register'] if case != 'register_after' else ['register','disable:'+NEW,'stop:'+NEW]
                self.assertEqual(result['calls'], expected)

    def test_failures_restore_old_after_new_secured(self):
        for case in ('enable_fail','start_fail','smoke_fail'):
            with self.subTest(case=case):
                result = self.exercise(case)
                self.assertTrue(result['failed'])
                self.assertEqual(result['tasks'][OLD]['State'], 'Ready')
                self.assertEqual(result['tasks'][NEW]['State'], 'Disabled')
                self.assertEqual(result['calls'][-3:], ['disable:'+NEW,'stop:'+NEW,'enable:'+OLD])

    def test_old_drift_and_replaced_owner_fail_closed(self):
        result = self.exercise('old_drift')
        self.assertTrue(result['failed'])
        self.assertNotIn('disable:'+OLD, result['calls'])
        result = self.exercise('owner_replaced')
        self.assertTrue(result['failed'])
        self.assertNotIn('disable:'+NEW, result['calls'])
        self.assertNotIn('stop:'+NEW, result['calls'])
        self.assertNotIn('enable:'+OLD, result['calls'])

if __name__ == '__main__':
    unittest.main()
