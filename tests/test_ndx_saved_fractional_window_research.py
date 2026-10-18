from copy import deepcopy
import tempfile
import unittest
from test_ndx_candidate_input_equivalence_research import fixture
from backtest import ndx_saved_fractional_window_research as recovery


class SavedWindowTests(unittest.TestCase):
    def test_real_small_fitter_output_recovered_without_refitting(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory,'non_equal_fractional_v1')
            saved = recovery.equivalence.previous.fractional.evaluate_non_equal_fractional(task=args['task'],inputs=args['inputs'])
            original = recovery.verify_original(arguments=args,saved=saved)
            changed = deepcopy(args); changed['inputs']['returns'].iloc[64,4] += .02
            new = recovery.recover(arguments=changed,saved=saved)
            for oldrow,newrow in zip(original['windows'],new['windows']):
                for key in ('candidate_return','candidate_drawdown','turnover','cost','target_return','target_drawdown'):
                    self.assertEqual(oldrow[key],newrow[key])
            for key in original['metrics']:
                if not key.startswith('paired_'): self.assertEqual(original['metrics'][key],new['metrics'][key])
            self.assertNotEqual(original['windows'][0]['incumbent_return'],new['windows'][0]['incumbent_return'])

    def test_incomplete_misaligned_or_forged_window_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            args = fixture(directory,'non_equal_fractional_v1')
            saved = recovery.equivalence.previous.fractional.evaluate_non_equal_fractional(task=args['task'],inputs=args['inputs'])
            for fault in ('missing','reverse','fit_end','tickers','bool_weight','sum','anchor','strength','metric','runtime'):
                other=deepcopy(saved); arguments=deepcopy(args)
                if fault=='missing':other['historical_window_weights'].pop()
                if fault=='reverse':other['historical_window_weights'].reverse()
                row=other['historical_window_weights'][0]
                if fault=='fit_end':row['fit_end']='2020-01-01'
                if fault=='tickers':row['tickers'].reverse()
                if fault=='bool_weight':row['weights']['AAA']=True
                if fault=='sum':row['weights']['AAA']+=.01
                if fault=='anchor':row['anchor_weights']=row['weights']
                if fault=='strength':row['turnover_anchor_strength']=True
                if fault=='metric':other['result']['return_p50']+=.01
                if fault=='runtime':arguments['runtime']['numpy']='different'
                with self.assertRaises(ValueError,msg=fault):recovery.verify_original(arguments=arguments,saved=other)
