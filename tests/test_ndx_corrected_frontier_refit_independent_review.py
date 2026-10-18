from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, main
from unittest.mock import patch
from scripts import ndx_corrected_frontier_single_refit_archive_research as runner
from scripts import ndx_corrected_frontier_cutoff_refit_archive_research as adapter
from test_ndx_corrected_frontier_single_refit_archive_research import Tests as RunnerFixture
from test_ndx_corrected_frontier_cutoff_refit_archive_research import context_fixture


class Tests(TestCase):
    def test_changed_started_attempt_must_reject_before_official_publication(self):
        with TemporaryDirectory() as folder:
            args=RunnerFixture().setup_queue(folder);target=Path(folder)/'result.json'
            def simulated_fit(**unused):
                Path(str(target)+'.started.json').write_text('{}')
                return {'status':'FITTED_FIVE_RISKS_FAILED'}
            with patch.object(runner.adapter,'verify'),patch.object(runner.adapter,'run_one',side_effect=simulated_fit) as fit:
                with self.assertRaises(ValueError):runner.run(**args,output=target,execute=True)
                self.assertEqual(fit.call_count,1)
                self.assertFalse(target.exists())
                with self.assertRaises(FileExistsError):runner.run(**args,output=target,execute=True)
                self.assertEqual(fit.call_count,1)

    def test_original_incumbent_universe_and_contract_are_bound_not_only_returns(self):
        for changed in ('incumbent_weights','universe','contract','target_returns'):
            context,report,inputs=context_fixture()
            if changed=='incumbent_weights':inputs[changed]['GOOG']=.9
            elif changed=='universe':inputs[changed].loc[0,'risk_chain']='wrong-chain'
            elif changed=='contract':inputs[changed]['transaction_cost_bps']+=1
            else:inputs[changed].iloc[0]+=.01
            context['prepared_inputs']={k:adapter.typed.encoding._panel_context(v) for k,v in inputs.items()}
            with self.subTest(changed=changed),self.assertRaises(ValueError):adapter.correct_context(context,report,'2022-07-29')


if __name__=='__main__':main()
