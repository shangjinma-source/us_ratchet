from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from scripts import ndx_registered_scoring_first_task_independent_readback_20261003 as reader
from test_ndx_registered_scoring_first_task_independent_readback_20261003 import fixture


class Review(unittest.TestCase):
    def test_exception_and_unknown_return_cannot_be_success(self):
        with TemporaryDirectory() as td:
            args,docs,refs,inputs,sources,parents=fixture(Path(td))
            for change in (lambda d:d['raw_fit'].update(error={'type':'RuntimeError','message':'saved error'}),lambda d:d['raw_score'].update(result_preserved_as_json=False),lambda d:d['raw_fit'].update(internal_optimizer_call_count=0),lambda d:d['postcheck'].update(attempted_job_count=True),lambda d:d['raw_score'].update(source_hashes={'invented':'a'*64})):
                changed=deepcopy(docs);change(changed)
                with patch.object(reader,'TASK_ID',args['assembled']['job_id']),self.assertRaises(ValueError):
                    reader.inspect_envelopes(changed,refs,inputs,sources,parents['rolling_fitter_manifest'])

    def test_post_report_drift_preserves_report_and_blocks_retry(self):
        with TemporaryDirectory() as td:
            root=Path(td);parent=root/'parent';parent.mkdir()
            args,docs,refs,inputs,sources,parents=fixture(parent)
            original=reader.save
            def save(path,value):
                result=original(path,value)
                if path.name=='independent_readback.json':(parent/'raw_fit.json').write_bytes(b'tampered after report')
                return result
            with patch.object(reader,'PARENT',parent),patch.object(reader,'OUTPUT',root/'audit'),patch.object(reader,'TASK_ID',args['assembled']['job_id']),patch.object(reader,'POSTCHECK_SHA',refs['postcheck']['sha256']),patch.object(reader,'load_context',return_value=(parents,inputs,sources,args['channel_bindings'],args['assembled']['registered_job_preserved'])),patch.object(reader,'save',side_effect=save):
                with self.assertRaises(ValueError):reader.readback(execute=True)
                self.assertTrue((root/'audit/independent_readback.json').is_file())
                self.assertTrue((root/'audit/failure.json').is_file())
                with self.assertRaises(ValueError):reader.readback(execute=True)

    def test_consumed_bytes_single_read_and_private_inspection_only(self):
        with TemporaryDirectory() as td:
            file=Path(td)/'source';file.write_bytes(b'known')
            with patch.object(Path,'read_bytes',side_effect=[b'known',b'changed']) as read:
                self.assertEqual(reader.take(reader.ref(file,reader.sha(b'known')),{}),b'known')
                self.assertEqual(read.call_count,1)
        sources={};core=reader.private_inspector(sources)
        self.assertTrue(callable(core.inspect_registered_scoring_result))
        self.assertEqual(set(sources),{str(reader.INSPECTOR),str(reader.ROOT/reader.CODES['inspector'][0])})


if __name__=='__main__':unittest.main()
