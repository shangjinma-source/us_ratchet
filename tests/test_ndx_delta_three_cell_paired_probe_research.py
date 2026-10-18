from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from test_ndx_candidate_input_equivalence_research import fixture
from scripts import ndx_delta_three_cell_paired_probe_research as runner


class ProbePlanTests(unittest.TestCase):
    def test_real_april_46_tasks_keep_seven_original_contexts_read_only(self):
        classified=runner.original.read(runner.CLASSIFICATION,runner.CLASSIFICATION_SHA)
        inventory=runner.original.read(runner.INVENTORY,runner.INVENTORY_SHA)
        descriptor,=[entry for entry in inventory['summaries'] if entry['coordinate']['selection_date']=='2023-04-03']
        summary=runner.original.read(descriptor['path'],descriptor['sha256'])
        rows=classified['buckets']['2023-04-03|DELTA|PAIRED_ONLY_NO_REFIT']
        references=[runner.task_context_reference(row,summary['source_hashes']) for row in rows]
        self.assertEqual(len(rows),46);self.assertEqual(len({ref['context_path'] for ref in references}),7)
        for row,ref in zip(rows,references):
            context=runner.original.read(ref['context_path'],ref['context_sha256'])
            self.assertIn(row['task'],context['tasks'])
        with self.assertRaises(ValueError):runner.task_context_reference(rows[0],{})

    def test_all_three_cells_exact_and_only_incumbent_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            args=fixture(directory,'joint_weight_v3');inputs=args['inputs'];inputs['returns']=inputs['returns'].rename(columns={'INC':'GOOG'})
            inputs['incumbent_weights']={'GOOG':1.}
            inputs['returns']['FTNT']=.01;inputs['returns']['GOOGL']=.01
            corrections=[dict(ticker=t,session=str(inputs['returns'].index[p].date()),old=float(inputs['returns'].iloc[p][t]),new=.03)
                for t,p in [('GOOG',70),('FTNT',0),('GOOGL',0)]]
            with patch.object(runner,'ERRORS',corrections):
                runner.check_paired(args['task'],inputs)
                changed=runner.apply_three(inputs)
                self.assertEqual(int((changed['returns']!=inputs['returns']).sum().sum()),3)
                bad=deepcopy(inputs);bad['returns'].loc[corrections[0]['session'],'GOOG']=.99
                with self.assertRaises(ValueError):runner.apply_three(bad)
                task=dict(args['task'],tickers='AAA;BBB;CCC;FTNT')
                with self.assertRaisesRegex(ValueError,'not paired-only'):runner.check_paired(task,inputs)

    def test_existing_probe_never_reexecutes_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'probe.json';path.write_text('{}')
            with patch.object(runner.adapter,'recover_paired_delta') as calculate:
                with self.assertRaises(FileExistsError):runner.run_first_probe(plan_path='missing',plan_sha256='0'*64,output=path)
                calculate.assert_not_called()

    def test_three_cell_denominator_rejected_before_source_walk(self):
        with (patch.object(runner.original,'read',return_value=dict(errors=runner.ERRORS,counts={'DELTA|PAIRED_ONLY_NO_REFIT':613})),
             patch.object(runner.adapter,'recover_paired_delta') as calculate):
            with self.assertRaisesRegex(ValueError,'614'):runner.build_plan()
            calculate.assert_not_called()
