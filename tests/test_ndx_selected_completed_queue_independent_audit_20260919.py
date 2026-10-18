from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import test_ndx_selected_delta_drift_snapshot_research as fixtures
from backtest import ndx_selected_delta_drift_snapshot_research as producer
from scripts import ndx_selected_completed_queue_independent_audit_20260919 as audit


class IndependentQueueTests(unittest.TestCase):
    def fixture(self,folder,stack,nonanchor=False):
        path,sha,manifest,params,probe,probe_sha=fixtures.SelectedSnapshotTests().setup_fixture(folder,stack)
        stack.enter_context(patch.object(audit,'MANIFEST',path))
        stack.enter_context(patch.object(audit,'MANIFEST_SHA',sha))
        stack.enter_context(patch.object(audit,'CORRECTIONS',producer.selected.CORRECTIONS))
        snapshot=producer.begin(manifest_path=path,manifest_sha256=sha)
        value=producer.evaluate(snapshot,'1') if nonanchor else producer.import_probe(snapshot,probe,probe_sha)
        producer.finish(snapshot)
        row=manifest['tasks'][1 if nonanchor else 0]
        context=producer.read(row['context_path'],row['context_sha256'])
        checkpoint=producer.read(row['checkpoint_path'],row['checkpoint_sha256'])
        return value,row,context,checkpoint,manifest

    def test_all_windows_twenty_metrics_and_decimal_close_without_fitter(self):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            args=self.fixture(Path(d),stack)
            with patch.object(producer.selected.trace,'evaluate_with_window_trace',side_effect=AssertionError('No fitter')):
                report=audit.audit_task(*args)
            self.assertEqual(len(report['checked_metric_fields']),20)
            self.assertEqual(report['scalar_max_error'],0.)
            self.assertFalse(report['saved_non20_fields_independently_recomputed'])

    def test_nan_bool_wrong_task_relabel_and_wrong_typed_digest_rejected(self):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            original=self.fixture(Path(d),stack)
            for defect in ('nan','bool','task','disclosure','typed','old_count','mode'):
                args=deepcopy(original);v=args[0]
                if defect=='nan':v['result']['result']['return_p50']=float('nan')
                elif defect=='bool':v['result']['new_windows'][0]['cost']=False
                elif defect=='task':v['original']['task']['tickers']='WRONG'
                elif defect=='disclosure':v['non20_risk_projection_fields_independently_recomputed']=True
                elif defect=='typed':v['result']['new_input_sha256']='0'*64
                elif defect=='old_count':v['result']['old_input_numerical_evaluation_count']=False
                else:v['mode']='ONE_NEW_INPUT_FULL_V3_EVALUATION_NO_OLD_WINDOW_REUSE'
                with self.assertRaises(ValueError,msg=defect):audit.audit_task(*args)

    def test_nonanchor_trace_uses_zero_despite_nonzero_contract(self):
        with tempfile.TemporaryDirectory() as d,ExitStack() as stack:
            args=self.fixture(Path(d),stack,nonanchor=True)
            contract=audit.scalar.decode(args[2]['prepared_inputs']['contract']['payload'])
            self.assertGreater(contract['turnover_anchor_strength'],0)
            self.assertTrue(all(w['turnover_anchor_strength']==0. for w in args[0]['result']['historical_window_weights']))
            with patch.object(producer.selected.trace,'evaluate_with_window_trace',side_effect=AssertionError('No fitter')):
                self.assertLessEqual(audit.audit_task(*args)['scalar_max_error'],1e-12)
                for wrong in (contract['turnover_anchor_strength'],False,float('nan')):
                    bad=deepcopy(args)
                    bad[0]['result']['historical_window_weights'][0]['turnover_anchor_strength']=wrong
                    with self.assertRaises(ValueError):audit.audit_task(*bad)

    def test_finalized_index_count_status_flags_and_duplicates(self):
        manifest={'tasks':[{'new_job_id':'0'},{'new_job_id':'1'},{'new_job_id':'2'}]}
        flags=dict(historical_full_source_closure_verified=False,original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
        final=dict(flags,schema='ndx_selected_delta_exact_gap_finalization_v1',planned=3,completed=2,status='PARTIAL',immutable_numerical_source_closure_verified=True)
        index=dict(flags,schema='ndx_selected_delta_exact_gap_completion_index_v1',manifest=dict(path=str(audit.MANIFEST),sha256=audit.MANIFEST_SHA),planned=3,status='PARTIAL',
                   completed=[dict(path='0',sha256='a'),dict(path='1',sha256='b')],finalization=final)
        self.assertEqual(audit.check_index(index,manifest,['0','1']),['0','1'])
        for defect in ('missing','count','complete','flag','duplicate'):
            value=deepcopy(index)
            if defect=='missing':value['finalization']=None
            elif defect=='count':value['finalization']['completed']=1
            elif defect=='complete':value['status']='COMPLETE'
            elif defect=='flag':value['promotion_allowed']=0
            else:value['completed'][1]=value['completed'][0]
            with self.assertRaises(ValueError,msg=defect):audit.check_index(value,manifest,['0','1'])


if __name__=='__main__':unittest.main()
