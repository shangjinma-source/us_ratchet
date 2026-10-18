from copy import deepcopy
import unittest
from scripts import ndx_dynamic_training_plan as index
from test_ndx_joint_weight_runner import prepared


class TrainingPlanTests(unittest.TestCase):
    def fixture(self):
        tasks,_=prepared()
        coordinate={key:tasks[0][key] for key in ('source_batch','universe_track','selection_date',
            'decision_data_end','holding_count','child_manifest_sha256')}
        empty=dict(coordinate, source_batch='separate_source_segment')
        plans=[dict(coordinate=coordinate,tasks=tasks,child_path='one',child_sha256=coordinate['child_manifest_sha256']),
               dict(coordinate=empty,tasks=[],child_path='two',child_sha256=empty['child_manifest_sha256'])]
        versioned=dict(plan=dict(plans=plans,planned=len(tasks)),namespace_sha256='n',capture_destination='root/n')
        report=dict(namespace_sha256='n',completed=1,pending=len(tasks)-1,
            coordinates=[dict(coordinate=coordinate,planned=len(tasks),completed=1,pending=len(tasks)-1,status='PARTIAL',context_sha256='c'),
                         dict(coordinate=empty,planned=0,completed=0,pending=0,status='NO_DELTA')],
            evaluated_results=[dict(coordinate=coordinate,job_id=tasks[0]['job_id'],
                tickers=tasks[0]['tickers'],weight_spec=tasks[0]['weight_spec'])])
        return versioned,report

    def test_no_delta_partial_and_source_segments_retained(self):
        versioned,report=self.fixture(); result=index._index(versioned,report)
        self.assertEqual(result['summary']['coordinate_count'],2)
        self.assertEqual(result['summary']['status_counts'],{'PARTIAL':1,'NO_DELTA':1})
        self.assertEqual(len(result['summary']['source_batches']),2)
        self.assertEqual([row['status'] for row in result['coordinates'][0]['tasks']],['EVALUATED','MISSING_CHECKPOINT'])
        self.assertIsNone(result['coordinates'][1]['context_sha256'])

    def test_coordinate_and_task_mismatches_rejected(self):
        versioned,report=self.fixture(); report['evaluated_results'][0]['weight_spec']='wrong'
        with self.assertRaises(ValueError): index._index(versioned,report)
        versioned,report=self.fixture(); report['coordinates'][1]['coordinate']=deepcopy(report['coordinates'][0]['coordinate'])
        with self.assertRaises(ValueError): index._index(versioned,report)
        versioned,report=self.fixture(); report['namespace_sha256']='wrong'
        with self.assertRaises(ValueError): index._index(versioned,report)

    def test_duplicate_result_and_missing_context_rejected(self):
        versioned,report=self.fixture(); report['evaluated_results'].append(deepcopy(report['evaluated_results'][0]))
        with self.assertRaises(ValueError): index._index(versioned,report)
        versioned,report=self.fixture(); report['coordinates'][0].pop('context_sha256')
        with self.assertRaises(ValueError): index._index(versioned,report)


if __name__=='__main__': unittest.main()
