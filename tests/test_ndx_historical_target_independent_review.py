"""Historical fit-input/attempt tests using saved source fixtures, no actual fit."""
import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from test_ndx_twenty_historical_single_target_20260919 import fixture
from scripts import ndx_twenty_historical_single_target_20260919 as m


class IndependentTargetReview(unittest.TestCase):
    def test_future_half_changes_do_not_enter_historical_fit(self):
        state,result,document,row=fixture()
        original=state['fit_returns'].copy(deep=True)
        for prices in document['prices']['returns']['data'][126:]:
            for i in range(len(prices)):prices[i]=999.
        fit,task,calendar=m.historical_view(document,row)
        self.assertTrue(fit.equals(original));self.assertEqual(task['task_id'],state['task']['task_id'])
        bad=copy.deepcopy(state);bad['fit_returns']=m.typed.decode(document['prices']['returns']).iloc[-126:]
        with self.assertRaises(ValueError):m.validate_fit(result,bad)
        wrong=copy.deepcopy(row);wrong['task']['extra_unbound_field']=True
        with self.assertRaises(ValueError):m.historical_view(document,wrong)

    def test_marker_modified_in_fitter_preserves_raw_but_refuses_target_and_retry(self):
        state,result,_,_=fixture()
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            def verify(sources):
                for path,expected in sources.items():
                    if m.hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:raise ValueError('source changed')
                return {}
            def altered(**kwargs):
                (folder/'started.json').write_text('{}')
                return result
            with patch.object(m,'prepare',return_value=state),patch.object(m,'verify_sources',side_effect=verify),patch.object(m.fitter,'refit_dynamic_cutoff_weights',side_effect=altered) as fit:
                with self.assertRaises(ValueError):m.run(folder,execute=True)
                self.assertTrue((folder/'raw_fit_receipt.json').exists())
                self.assertFalse((folder/'target.json').exists())
                with self.assertRaises(ValueError):m.run(folder,execute=True)
                self.assertEqual(fit.call_count,1)


if __name__=='__main__':unittest.main()
