"""Raw transport through reviewed full history; no paper/live order execution."""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_verified_context_monthly_capture_v1 import capture_session
from data.strategy_verified_context_monthly_normalizer_v1 import normalize_verified_capture
from data.strategy_monthly_supplement_capture import restore_reviewed_monthly_history
from data.monthly_peak_exit_history import monthly_exit_observations
from data.monthly_peak_exit_store import MonthlyPeakExitStore
from test_strategy_prospective_paper_daily_capture_v2 import arguments


class FullWindowTests(unittest.TestCase):
    def test_early_peak_outside_twenty_days_still_causes_exit(self):
        with TemporaryDirectory() as folder:
            args,_=arguments(folder)
            request=args['capture_requests']['B']
            config=json.loads(request['configuration_bytes'])
            config.update(monthly_decision_date='2026-10-01',output_root='full-month-capture')
            raw_config=canonical(config);config_hash=sha256(raw_config).hexdigest()
            sessions=json.loads(args['authority']['descriptor_arguments']['calendar_bytes'])['sessions']
            rows=[row for row in sessions if '2026-10-01'<=row['date']<'2026-11-03']
            self.assertGreater(len(rows),20)
            original=args['fetch_daily']()
            body=json.loads(original['body']);series=body['chart']['result'][0]
            series['timestamp']=[int(datetime.fromisoformat(row['open']).timestamp()) for row in rows]
            prices=[150]+[100]*(len(rows)-1)
            series['indicators']=dict(quote=[dict(close=prices)],adjclose=[dict(adjclose=prices)])
            captured=capture_session(root=args['root'],configuration_bytes=raw_config,
                configuration_sha256=config_hash,execute=True,clock=args['clock'],
                fetch_daily=lambda *unused:dict(status=200,body=canonical(body)),fetch_official=args['fetch_official'])
            self.assertEqual(captured['status'],'CAPTURED_MONTHLY_WINDOW_UNIT_REVIEW_REQUIRED')
            normalized=normalize_verified_capture(root=args['root'],capture_directory=captured['output'],
                expected_configuration_sha256=config_hash,parent_reference=request['parent_reference'],clock=args['clock'])
            self.assertEqual(normalized['status'],'CONDITIONAL_HISTORY_READY_NOT_ACCOUNT_ADMITTED')
            receipt=normalized['receipt'];files=normalized['files']
            short=json.loads(files[receipt['normalized_inputs_path']])
            self.assertEqual(len(short['histories']['B']['closes']),20)
            self.assertTrue(all(float(row['close'])==100 for row in short['histories']['B']['closes']))
            name=receipt['monthly_history_inputs_path']
            receipt['monthly_history_inputs']={'B':dict(path=name,sha256=sha256(files[name]).hexdigest())}
            full=restore_reviewed_monthly_history(receipt=receipt,files=files,decision_date='2026-10-01')
            full['base_target']['monthly_decision_date']='2026-10-01'
            self.assertEqual(len(full['histories']['B']['closes']),len(rows))
            observations=monthly_exit_observations(**full)
            store=MonthlyPeakExitStore(Path(folder)/'risk.sqlite')
            result=store.advance(account_id='isolated-source-window',expected_previous_session=None,
                observations=observations,baseline_targets={'B':10})
            self.assertEqual(result['state']['peaks']['B'],'150')
            self.assertEqual(result['effective_target_quantities'],{'B':0})


if __name__=='__main__':unittest.main()
