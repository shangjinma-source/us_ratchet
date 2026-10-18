"""Independent synthetic isolation and failure tests; no saved numeric inputs."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_dated_training_panel_research import fixture
from test_ndx_dated_training_panel_20261003 import fixture as wrapper_fixture
from backtest import ndx_dated_training_panel_research as core
from scripts import ndx_dated_training_panel_20261003 as wrapper


class IndependentReview(unittest.TestCase):
    def test_evaluation_and_late_metadata_cannot_enter_training(self):
        args = fixture()
        original = core.prepare_dated_training_panel(**args)
        row = args['channels_document']['rows'][0]
        row['coordinate']['median_dollar_volume_usd'] = 1e100
        for item in row['channel']['evaluation_returns']:
            item.update(split_only_return_exact='9', split_only_return_float=9.0)
        row['channel']['evaluation_returns_sha256'] = core.digest(row['channel']['evaluation_returns'])
        changed = core.prepare_dated_training_panel(**args)
        self.assertEqual(original['fit_payload'], changed['fit_payload'])
        self.assertNotEqual(original['evaluation_references'], changed['evaluation_references'])
        self.assertNotEqual(original['original_coordinate_evidence'], changed['original_coordinate_evidence'])
        self.assertFalse(changed['liquidity_qualification_at_training_cutoff_verified'])

    def test_resigned_predecessor_float_and_class_attacks(self):
        for field, value in [('previous_session', '2026-03-23'), ('split_only_return_float', True), ('split_only_return_float', float('inf'))]:
            args = fixture()
            channel = args['channels_document']['rows'][0]['channel']
            channel['training_returns'][0][field] = value
            with self.assertRaises(ValueError):
                channel['training_returns_sha256'] = core.digest(channel['training_returns'])
                core.prepare_dated_training_panel(**args)
        panel = core.prepare_dated_training_panel(**fixture())
        with self.assertRaises(ValueError):
            core.selected_mapping_dated(panel, ['S000', 'S001'])
        panel['fit_payload']['selected_by_security']['S002']['median_dollar_volume_usd'] = 123
        panel['content_sha256'] = core.digest({k:v for k,v in panel.items() if k != 'content_sha256'})
        with self.assertRaises(ValueError):
            core.selected_mapping_dated(panel, ['S002'])

    def test_wrapper_binding_checks_before_projection(self):
        for mutate in [lambda d:d['channels_readback']['per_channel'][-1].update(receipt_reference={'path':'other','sha256':'e'*64}), lambda d:d['channels_publication'].update(source_hashes={'unexpected':'f'*64}), lambda d:d['parent_panel']['panel']['universe']['data'][-1].__setitem__(-1, 0)]:
            docs, refs = wrapper_fixture()
            mutate(docs)
            with self.assertRaises(ValueError):
                wrapper.project_inputs(docs, refs)

    def test_source_runtime_and_failure_namespace(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'source'; p.write_bytes(b'a')
            sources={str(p):wrapper.sha(b'a')}; runtime=wrapper.runtime()
            p.write_bytes(b'b')
            with self.assertRaises(ValueError): wrapper.guard(sources,runtime)
            with patch.object(wrapper,'runtime',return_value={'changed':True}):
                with self.assertRaises(ValueError): wrapper.guard({},runtime)
            out=Path(folder)/'failed';out.mkdir();(out/'failure.json').write_text('{}')
            with patch.object(wrapper,'OUTPUT',out),patch.object(wrapper,'load_inputs',side_effect=AssertionError('must not load')):
                with self.assertRaises(ValueError):wrapper.run(execute=True)


if __name__=='__main__':unittest.main()
