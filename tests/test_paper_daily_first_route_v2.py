from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from core.strategy_account_ledger import canonical
from data.strategy_prospective_paper_daily_capture_v2 import capture_prospective_daily
import test_strategy_prospective_paper_daily_capture_v2 as fixture


class FirstRouteTests(unittest.TestCase):
    def test_first_reviewed_packet_enters_actual_daily_aggregation(self):
        with TemporaryDirectory() as folder:
            args,calls=fixture.arguments(folder)
            old=capture_prospective_daily(**args)
            receipt=deepcopy(old['receipt'])
            receipt['monthly_history_inputs_path']=receipt['monthly_history_inputs']['B']['path']
            packet_raw=canonical(receipt)
            directory=Path(folder)/'first-review-result';directory.mkdir()
            complete_raw=canonical(dict(schema='PAPER_FIRST_WINDOW_ARCHIVE_V2',
                status='FIRST_WINDOW_REVIEWED_NOT_ADMITTED',receipt_sha256=sha256(packet_raw).hexdigest()))
            (directory/'complete.json').write_bytes(complete_raw)
            reviewed=dict(status='FIRST_WINDOW_REVIEWED_NOT_ADMITTED',directory=str(directory),
                complete_sha256=sha256(complete_raw).hexdigest(),receipt_bytes=packet_raw,
                files=old['daily_arguments']['files'])
            request=args['capture_requests']['B'];config=json.loads(request['configuration_bytes'])
            config.update(schema='PAPER_FIRST_DAILY_WINDOW_V2',security_id='B',identity=config.pop('identity_review'))
            config.pop('security');raw=canonical(config)
            args['capture_requests']['B']=dict(configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest())
            args['output_directory']=Path(folder)/'first-published'
            args['read_binding']=lambda: {}
            # Replace only the already separately tested first-source producer.
            # Formal daily verification and aggregate archive are actual modules.
            with patch('data.strategy_prospective_paper_daily_capture_v2.capture_first_window',return_value=reviewed) as first:
                result=capture_prospective_daily(**args)
            self.assertEqual(first.call_count,1)
            self.assertEqual(result['status'],'DAILY_SIGNAL_READY')
            self.assertEqual(result['receipt']['parent_reviews']['B'],sha256(packet_raw).hexdigest())
            refs=result['receipt']['first_window_archives']['B']
            self.assertEqual(result['daily_arguments']['files'][refs['receipt_path']],packet_raw)
            self.assertEqual(result['daily_arguments']['files'][refs['complete_path']],complete_raw)


if __name__=='__main__':unittest.main()
