import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backtest import ndx_cutoff_lane_dependency_research as core


class LaneTests(unittest.TestCase):
    def save(self,folder,name,value):
        path=Path(folder)/name;raw=json.dumps(value).encode();path.write_bytes(raw)
        return dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest())

    def fixture(self,folder):
        coordinate=dict(selection_date='2023-04-03',source_batch='fixture',universe_track='original_conditioned_pool')
        index=dict(items=[{'timestamp':day+'T00:00:00'} for day in ['2023-03-29','2023-03-30','2023-03-31']])
        panel=dict(payload=dict(mapping=dict(index=index)))
        universe=dict(payload=dict(mapping=dict(columns=dict(items=['ticker','security_id','issuer_id','risk_chain']),
            column_values=dict(items=[dict(items=values) for values in [['AAA','BBB'],['sid-a','sid-b'],['issuer-a','issuer-b'],['one','two']]]))))
        context={'prepared_inputs':dict(returns=panel,nominal_prices=panel,target_returns=panel,universe=universe)}
        metrics=dict(return_p50=0.2,return_p10=0.1,max_drawdown_p50=0.05,max_drawdown_p90=0.08,target_012922_distance=0.1)
        records=[];diagnostics=[]
        for job,names in [('a','AAA'),('b','AAA;BBB')]:
            task=dict(coordinate,job_id=job,decision_data_end='2023-03-31',tickers=names,holding_count=len(names.split(';')),weight_spec='equal_weight')
            result=dict(metrics,**{key:task[key] for key in ('tickers','holding_count','weight_spec')})
            records.append(dict(task=task,result=result,status='AVAILABLE'))
            diagnostics.append(dict(job_id=job,absolute_metrics={key:metrics[key] for key in metrics if key!='target_012922_distance'},
                fractional_risk_liquidity_passed=True,**{key:task[key] for key in ('tickers','holding_count','weight_spec')}))
        complete=dict(coordinate=coordinate,records=records,original_count=2,economic_inputs_complete=True,pending_count=0)
        frontier=dict(schema='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1',coordinate=coordinate,
            original_decision_data_end='2023-03-31',original_count=2,candidate_diagnostics=diagnostics,
            complete_date_artifact=self.save(folder,'complete.json',complete))
        independent=dict(schema='SELECTED_ARCHIVE_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1',date=coordinate['selection_date'],
            output_path=frontier['complete_date_artifact']['path'],output_sha256=frontier['complete_date_artifact']['sha256'],
            original_count=2,whole_date_task_map_verified=True,ordered_full_record_diff_verified=True,
            full_new_results_match_external_checkpoints=True,output_source_partitions_reverified=True)
        frontier['independent_full_diff_artifact']=self.save(folder,'diff.json',independent)
        queue=dict(schema='CORRECTED_FRONTIER_HISTORICAL_CUTOFF_QUEUE_V1',coordinate=coordinate,historical_cutoff='2023-03-31',
            candidate_count=2,original_fourteen_parameter_contract=dict(fit_days=1,window_days=1,step_days=1),
            context=self.save(folder,'context.json',context),frontier=self.save(folder,'frontier.json',frontier))
        context['prepared_inputs']['contract']={'payload':{'mapping':dict(queue['original_fourteen_parameter_contract'])}}
        queue['context']=self.save(folder,'context.json',context)
        return queue,context,frontier,complete

    def test_keep_all_ties_without_cardinality_tiebreak(self):
        with tempfile.TemporaryDirectory() as folder:
            queue,*_=self.fixture(folder);reference=self.save(folder,'queue.json',queue)
            result=core.prepare_lanes([reference])
            for rows in result['decisions'][0]['lanes'].values():
                self.assertEqual([row['holding_count'] for row in rows],[1,2])
            self.assertEqual(len(result['dependencies']),8)
            self.assertFalse(result['continuous_target_schedule_built'])

    def test_future_calendar_rejected_even_if_rehashed(self):
        with tempfile.TemporaryDirectory() as folder:
            queue,context,*_=self.fixture(folder)
            context['prepared_inputs']['returns']['payload']['mapping']['index']['items'][-1]['timestamp']='2023-04-04T00:00:00'
            queue['context']=self.save(folder,'context.json',context)
            with self.assertRaisesRegex(ValueError,'cutoff'):
                core.prepare_lanes([self.save(folder,'queue.json',queue)])

    def test_missing_denominator_and_source_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            queue,_,frontier,complete=self.fixture(folder)
            complete['records'].pop();frontier['complete_date_artifact']=self.save(folder,'complete.json',complete)
            queue['frontier']=self.save(folder,'frontier.json',frontier)
            reference=self.save(folder,'queue.json',queue)
            with self.assertRaisesRegex(ValueError,'denominator|diff'):
                core.prepare_lanes([reference])
            Path(reference['path']).write_text('{}')
            with self.assertRaisesRegex(ValueError,'SHA'):
                core.prepare_lanes([reference])

    def test_duplicate_dates_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            queue,*_=self.fixture(folder);reference=self.save(folder,'queue.json',queue)
            with self.assertRaisesRegex(ValueError,'unordered'):
                core.prepare_lanes([reference,copy.deepcopy(reference)])

    def test_missing_lane_ancestor_blocks_all_later_decisions(self):
        with tempfile.TemporaryDirectory() as folder:
            queue,*_=self.fixture(folder);reference=self.save(folder,'queue.json',queue)
            original=core.prepare_decision(reference)
            decisions=[copy.deepcopy(original) for _ in range(3)]
            for row,cutoff,execution in zip(decisions,['2023-03-31','2023-04-28','2023-05-31'],
                                           ['2023-04-03','2023-05-01','2023-06-01']):
                row.update(cutoff=cutoff,execution_date=execution)
            decisions[0]['lanes']['RETURN']=[]
            with patch.object(core,'prepare_decision',side_effect=decisions):
                result=core.prepare_lanes([reference]*3)
            later=[row for row in result['dependencies'] if row['node_id'].startswith('RETURN:')]
            self.assertEqual(len(later),4)
            self.assertTrue(all(row['dependency_status']=='BLOCKED_UNREACHABLE_PREVIOUS_LANE' for row in later))


if __name__=='__main__':unittest.main()
