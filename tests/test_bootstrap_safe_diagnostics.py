import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from scripts.bootstrap_current_quantity_v2_simulation import run,main
from scripts.run_scheduled_quantity_v2_simulation import main as scheduled_main
from test_bootstrap_current_quantity_v2_simulation import fixture,NOW


class BootstrapDiagnosticTests(unittest.TestCase):
    def test_preview_fixed_reason_and_untrusted_error_never_create_account(self):
        for reason,suffix in [('LAST_QUOTE_STALE','LAST_QUOTE_STALE'),
                              ('https://private.example/token=SECRET C:/private','SOURCE_UNAVAILABLE')]:
            with self.subTest(reason=reason),TemporaryDirectory() as folder:
                config,args=fixture(Path(folder))
                with patch('data.current_quantity_v2_current_cash_service.CurrentQuantityV2CurrentCashService.preview',
                           return_value=dict(status='UNAVAILABLE',reason=reason)):
                    with self.assertRaises(ValueError) as raised:run(**args,execute=True,clock=lambda:NOW)
                self.assertEqual(str(raised.exception),'BOOTSTRAP_FRESH_PROPOSAL_UNAVAILABLE:'+suffix)
                self.assertFalse(Path(config['database_path']).exists())

    def test_both_clis_preserve_safe_code_and_redact_untrusted_suffix(self):
        for text,expected in [('BOOTSTRAP_FRESH_PROPOSAL_UNAVAILABLE:OUTSIDE_REGULAR_SESSION',
                               'BOOTSTRAP_FRESH_PROPOSAL_UNAVAILABLE:OUTSIDE_REGULAR_SESSION'),
                              ('BOOTSTRAP_FRESH_PROPOSAL_UNAVAILABLE:https://secret/TOKEN','ValueError')]:
            for target,entry,argv,exit_code in [
                ('scripts.bootstrap_current_quantity_v2_simulation.run',main,
                 ['--config','unused','--config-sha256','unused'],1),
                ('scripts.run_scheduled_quantity_v2_simulation.run',scheduled_main,
                 ['--bootstrap-config','unused','--bootstrap-sha256','unused','--daily-config','unused','--daily-sha256','unused'],2)]:
                with self.subTest(text=text,target=target),patch(target,side_effect=ValueError(text)):
                    with redirect_stdout(io.StringIO()) as output:self.assertEqual(entry(argv),exit_code)
                    result=json.loads(output.getvalue());self.assertEqual(result['status'],'BLOCKED')
                    self.assertEqual(result['reason'],expected);self.assertNotIn('TOKEN',output.getvalue())


if __name__=='__main__':unittest.main()
