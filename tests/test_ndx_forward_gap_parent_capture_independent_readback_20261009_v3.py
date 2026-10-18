"""Independent capture reconstruction tests, no actual entrypoint execution."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_forward_gap_parent_capture_independent_readback_20261009_v3 as reader
from backtest import ndx_forward_gap_parent_capture_research_v3 as pure
from test_ndx_forward_gap_parent_capture_research_v3 import fixture, resign, replace_digest


def csv_reader():
    return reader.private_csv_reader(reader.CSV_READER.read_bytes())


def reconstruct(arguments):
    return reader.reconstruct_plan(**arguments,csv_rows=csv_reader())


class GapCaptureReadbackTests(unittest.TestCase):
    def test_full_plan_exact_for_zero_one_late_multi_and_close_crossing(self):
        cases=[fixture(),fixture(['2026-10-08'],start='2026-10-08T20:00:00+00:00'),
               fixture(['2026-10-08'],start='2026-10-12T21:00:00+00:00'),
               fixture(['2026-10-08','2026-10-09']),
               fixture(['2026-10-08'],start='2026-10-08T19:59:59+00:00',end='2026-10-08T20:00:01+00:00')]
        for args in cases:
            expected=pure.plan_gap_parent_capture(**args);before=deepcopy(args)
            with patch.object(pure,'plan_gap_parent_capture',side_effect=AssertionError('New pure called')):
                actual=reconstruct(args)
            reader.exact(actual,expected);self.assertEqual(args,before)

    def test_exact_plan_rejects_changed_non_count_fields(self):
        original=reconstruct(fixture())
        changes=[lambda p:p['known_typed_rows'][0].update(seal_status='SEALED'),
                 lambda p:p['accounted_baseline_references']['QQQ'].update(sha256='f'*64),
                 lambda p:p['parent_attempt_inventory'].clear(),
                 lambda p:p['first_actual_observed_session_by_month'].update({'2026-10':'2026-10-05'}),
                 lambda p:p.update(timeliness_verified=0),lambda p:p.update(extra=True)]
        for change in changes:
            altered=deepcopy(original);change(altered)
            with self.assertRaises(ValueError):reader.exact(altered,original)

    def test_asymmetry_revision_are_exact_independent_diagnostics(self):
        a=fixture(['2026-10-08']);a['source_bytes']['SPY']=a['accounted_baseline_bytes']['SPY'];resign(a,'SPY')
        reader.exact(reconstruct(a),pure.plan_gap_parent_capture(**a))
        a=fixture();a['source_bytes']['QQQ']=a['source_bytes']['QQQ'].replace(b',10,',b',11,',1);resign(a,'QQQ')
        reader.exact(reconstruct(a),pure.plan_gap_parent_capture(**a))

    def test_parent_authority_anchors_attempts_pending_reject(self):
        mutations=[lambda a:a['parent']['readback'].update(status='PASS'),
                   lambda a:a['parent']['document'].update(decision_eligible=True),
                   lambda a:a['parent']['document']['history']['parent_attempt_inventory'].append({'status':'STARTED'}),
                   lambda a:a['parent']['document']['history'].update(pending_source_sessions=[{'session':'2026-10-08'}]),
                   lambda a:a['parent']['readback']['counts'].update(observation_count=True),
                   lambda a:a['parent']['document']['history'].update(capture_reference=a['parent']['reference'])]
        for mutation in mutations:
            a=fixture();mutation(a)
            with self.assertRaises((ValueError,KeyError)):reconstruct(a)

    def test_actual_prefix_bytes_and_tzif_hash(self):
        a=fixture();old=reader.digest(a['actual_baseline_bytes']['QQQ'])
        a['actual_baseline_bytes']['QQQ']=a['actual_baseline_bytes']['QQQ'].rstrip(b'\n')+b'\r\n'
        replace_digest(a['parent'],old,reader.digest(a['actual_baseline_bytes']['QQQ']))
        with self.assertRaises(ValueError):reconstruct(a)
        a=fixture();a['tzif_bytes']+=b'changed'
        with self.assertRaises(ValueError):reconstruct(a)

    def test_private_csv_reader_pinned_and_sysmodules_independent(self):
        with self.assertRaisesRegex(ValueError,'Frozen CSV reader SHA'):
            reader.private_csv_reader(b'bad')
        with patch.dict('sys.modules',{'scripts.ndx_variable_prefix_capture_independent_readback_20261003':None}):
            self.assertEqual(reconstruct(fixture())['status'],'NO_NEW_SESSION')

    def test_pending_all_four_pins_before_io(self):
        for name in ('PRODUCER_SHA','PURE_SHA','CAPTURE_SHA','PUBLICATION_SHA'):
            pins=dict.fromkeys(('PRODUCER_SHA','PURE_SHA','CAPTURE_SHA','PUBLICATION_SHA'),'a'*64);pins[name]=None
            with (patch.multiple(reader,**pins),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')),
                  patch.object(Path,'exists',side_effect=AssertionError('IO')),patch.object(Path,'mkdir',side_effect=AssertionError('Output'))):
                with self.assertRaisesRegex(ValueError,'Pending immutable SHA'):reader.readback(execute=True)

    def test_save_createonly_bytes_roundtrip_and_duplicate_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'started.json'
            with patch.object(reader.shutil,'disk_usage',return_value=type('Space',(),{'free':10*1024**3})()):
                ref=reader.save(path,{'schema':'TEST','flag':False});self.assertEqual(reader.digest(path.read_bytes()),ref['sha256'])
                with self.assertRaises(FileExistsError):reader.save(path,{'schema':'TEST'})
        with self.assertRaises(ValueError):reader.decode(b'{"a":1,"a":2}')


if __name__=='__main__':unittest.main()
