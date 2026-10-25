from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_prospective_paper_daily_capture_v2 import capture_prospective_daily
from data.strategy_paper_registered_continuity_v2 import capture_registered_continuity
from test_strategy_prospective_paper_daily_capture_v2 import arguments


class RegisteredContinuityTests(unittest.TestCase):
    def test_next_session_actual_capture_and_normalization(self):
        with TemporaryDirectory() as folder:
            args, calls = arguments(folder, extra_sessions=[dict(date='2026-11-04',
                open='2026-11-04T14:30:00+00:00', close='2026-11-04T21:00:00+00:00')])
            captured = capture_prospective_daily(**args)
            source = captured['daily_arguments']['files']
            reference = captured['receipt']['security_packets']['B']
            raw = source[reference['path']]
            receipt = json.loads(raw)
            parent = dict(receipt_bytes=raw, trusted_parent_sha256=sha256(raw).hexdigest(),
                files={name:source[name] for name in receipt['source_sha256']},
                source_operation_id='registered-first-session')
            original = args['fetch_daily']
            def next_daily(*values):
                response = original(*values)
                document = json.loads(response['body'])
                series = document['chart']['result'][0]
                series['timestamp'].append(int(datetime.fromisoformat('2026-11-03T14:30:00+00:00').timestamp()))
                series['indicators']['quote'][0]['close'].append(101)
                series['indicators']['adjclose'][0]['adjclose'].append(101)
                return dict(response, body=canonical(document))
            rss = b'<rss><channel><title>Nasdaq</title><pubDate>Wed, 04 Nov 2026 14:00:00 GMT</pubDate><item><title>Unrelated notice</title><pubDate>Wed, 04 Nov 2026 14:00:00 GMT</pubDate></item></channel></rss>'
            config = json.loads(args['capture_requests']['B']['configuration_bytes'])
            binding = dict(account_revision=args['book']['revision'], session='2026-11-04')
            request = dict(root=folder, directory=Path(folder)/'next-session', security_id='B',
                parent=parent, configuration=config, authority=args['authority'],
                read_binding=lambda:dict(binding), expected_binding=dict(binding),
                clock=lambda:datetime.fromisoformat('2026-11-04T15:00:10+00:00'),
                fetch_daily=next_daily, fetch_official=lambda:dict(status=200,body=rss))
            result = capture_registered_continuity(**request)
            self.assertEqual(result['status'], 'CONDITIONAL_HISTORY_READY_NOT_ACCOUNT_ADMITTED')
            inputs = json.loads(result['files'][result['receipt']['normalized_inputs_path']])
            self.assertEqual(inputs['signal_date'], '2026-11-03')
            self.assertEqual(result['receipt']['execution_session']['date'], '2026-11-04')
            self.assertEqual(parent['receipt_bytes'], raw)
            self.assertTrue((Path(folder)/'next-session/complete.json').is_file())
            # The first-window template must automatically use its saved parent
            # on the next day, through the real aggregate verifier and archive.
            config.update(schema='PAPER_FIRST_DAILY_WINDOW_V2', security_id='B',
                identity=config.pop('identity_review'), output_root='routed-next-session')
            config.pop('security')
            config_raw = canonical(config)
            args['capture_requests']['B'] = dict(configuration_bytes=config_raw,
                configuration_sha256=sha256(config_raw).hexdigest())
            args.update(clock=request['clock'], fetch_daily=next_daily,
                fetch_official=request['fetch_official'], output_directory=Path(folder)/'next-published',
                parent_loader=lambda sid, before_session: parent if sid=='B' and before_session=='2026-11-04' else None,
                read_binding=lambda:dict(account_id=args['book']['account_id'],
                    account_revision=args['book']['revision'],
                    target_id=captured['receipt']['target_id'], session='2026-11-04'))
            routed = capture_prospective_daily(**args)
            self.assertEqual(routed['status'], 'DAILY_SIGNAL_READY')
            self.assertEqual(routed['receipt']['parent_reviews']['B'], parent['trusted_parent_sha256'])
            self.assertEqual(routed['receipt']['first_window_archives'], {})
            count = len(calls)
            with self.assertRaisesRegex(ValueError, 'RECOVERY_REQUIRED'):
                capture_registered_continuity(**request)
            self.assertEqual(len(calls), count)
            request['directory'] = Path(folder)/'snapshot-changed'
            binding['account_revision'] = 'changed'
            with self.assertRaisesRegex(ValueError, 'SNAPSHOT_CHANGED'):
                capture_registered_continuity(**request)
            self.assertFalse(request['directory'].exists())


if __name__ == '__main__':
    unittest.main()
