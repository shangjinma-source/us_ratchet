from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_delta_selected_input_probe_research as runner


class SelectedPlanTests(unittest.TestCase):
    def test_actual_hard_cohort_first_task_has_selected_dependency(self):
        classified=runner.prior.original.read(runner.prior.CLASSIFICATION,runner.prior.CLASSIFICATION_SHA)
        inventory=runner.prior.original.read(runner.prior.INVENTORY,runner.prior.INVENTORY_SHA)
        rows=classified['buckets']['2023-04-03|DELTA|SELECTED_INPUT_CHANGED']
        first=min(rows,key=lambda x:x['task']['job_id'])
        descriptor,=[x for x in inventory['summaries'] if x['coordinate']['selection_date']=='2023-04-03']
        summary=runner.prior.original.read(descriptor['path'],descriptor['sha256'])
        reference=runner.prior.task_context_reference(first,summary['source_hashes'])
        context=runner.prior.original.read(reference['context_path'],reference['context_sha256'])
        inputs={k:runner.adapter._restore_input(v) for k,v in context['prepared_inputs'].items()}
        runner.check_selected(first['task'],inputs)
        corrected=runner.corrected(inputs)
        self.assertEqual(int((corrected['returns']!=inputs['returns']).to_numpy().sum()),3)
        self.assertEqual(classified['counts']['DELTA|SELECTED_INPUT_CHANGED'],11254)
        bad=deepcopy(first['task']);bad['tickers']='ADI;AMAT;AVGO;CDNS;SNPS';bad['holding_count']=5
        with self.assertRaisesRegex(ValueError,'dependency absent'):runner.check_selected(bad,inputs)

    def test_self_resigned_plan_checkpoint_context_flags_and_subset_never_authorize_fit(self):
        original=dict(dates=[dict(tasks=[dict(checkpoint_sha256='original',context_sha256='original')])],promotion_allowed=False)
        for defect in ('checkpoint_sha256','context_sha256','flag','subset'):
            with tempfile.TemporaryDirectory() as directory:
                bad=deepcopy(original)
                if defect=='flag':bad['promotion_allowed']=True
                elif defect=='subset':bad['dates'][0]['tasks']=[]
                else:bad['dates'][0]['tasks'][0][defect]='resigned'
                path=Path(directory)/'plan.json';raw=json.dumps(bad).encode();path.write_bytes(raw)
                with (patch.object(runner,'build_plan',return_value=original),
                      patch.object(runner.adapter,'evaluate_selected_delta') as evaluate):
                    with self.assertRaisesRegex(ValueError,'hard-source reconstruction'):
                        runner.load_plan(path,hashlib.sha256(raw).hexdigest())
                    evaluate.assert_not_called()

    def test_existing_probe_rejected_without_plan_reconstruction_or_trace(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'probe.json';path.write_text('{}')
            with (patch.object(runner,'build_plan') as prepare,patch.object(runner.adapter,'evaluate_selected_delta') as evaluate):
                with self.assertRaises(FileExistsError):runner.run_first_probe(plan_path='absent',plan_sha256='0'*64,output=path)
                prepare.assert_not_called();evaluate.assert_not_called()

    def test_wrong_hard_denominator_rejected_before_source_or_fit(self):
        value=dict(errors=[dict(ticker=t,session=d,old=a,new=b) for t,d,a,b in runner.adapter.CORRECTIONS],counts={'DELTA|SELECTED_INPUT_CHANGED':11253})
        with (patch.object(runner.prior.original,'read',return_value=value),patch.object(runner.adapter,'evaluate_selected_delta') as evaluate):
            with self.assertRaisesRegex(ValueError,'11254'):runner.build_plan()
            evaluate.assert_not_called()


if __name__=='__main__':unittest.main()
