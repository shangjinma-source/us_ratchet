from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest
from scripts import ndx_registered_scoring_first_task_independent_readback_20261003 as m
from test_ndx_registered_scoring_result_inspection_research import fixture as numeric_fixture


def fixture(root):
    args=numeric_fixture();job=args['assembled']['job_id'];refs={};docs={};sources={};inputrefs={'budget':args['assembled']['budget_reference'],'rolling_fitter_manifest':args['assembled']['fitter_reference']};runtime={'python':'synthetic','numpy':'synthetic','pandas':'synthetic','scipy':'synthetic'};environment=dict(PYTHONHASHSEED='0',sys_flags_hash_randomization=0)
    def write(role,value):
        p=root/(role+'.json');b=m.enc(value);p.write_bytes(b);refs[role]=m.ref(p,m.sha(b));docs[role]=value
    base=dict(job_id=job,source_hashes=sources,**m.FLAGS)
    write('started',dict(schema='REGISTERED_SCORING_FIRST_TASK_STARTED_V1',started_at_utc='2026-10-03T01:00:00+00:00',registered_task_pointer='/plan/rows/0/mode_plans/1/tasks/0',input_references=inputrefs,runtime=runtime,worker_environment=environment,retry_allowed=False,whole_queue_task_count=19584,**base))
    write('inputs',dict(schema='REGISTERED_SCORING_FIRST_TASK_INPUTS_DOCUMENT_V1',assembled=args['assembled'],input_references=inputrefs,**base))
    for stage in ('fit','score'):
        write('raw_'+stage,dict(schema='REGISTERED_SCORING_RAW_'+stage.upper()+'_V1',stage=stage,call_invoked=True,returned=True,returned_call_count=1,internal_optimizer_call_count=None,result=args['saved_'+stage],error=None,inputs_reference=refs['inputs'],runtime=runtime,worker_environment=environment,result_preserved_as_json=True,**base))
    write('score_inspection',dict(schema='REGISTERED_SCORING_SCORE_INSPECTION_DOCUMENT_V1',inspection=args['saved_score_inspection'],inputs_reference=refs['inputs'],raw_fit_reference=refs['raw_fit'],raw_score_reference=refs['raw_score'],inspector_reference=m.ref(m.ROOT/m.CODES['inspector'][0],m.CODES['inspector'][1]),**base))
    write('postcheck',dict(schema='REGISTERED_SCORING_FIRST_TASK_POSTCHECK_V1',outcome='SCORED_PENDING_INDEPENDENT_READBACK',inputs_reference=refs['inputs'],raw_fit_reference=refs['raw_fit'],raw_score_reference=refs['raw_score'],score_inspection_reference=refs['score_inspection'],saved_references=[refs[k] for k in ('started','inputs','raw_fit','raw_score','score_inspection')],runtime=runtime,worker_environment=environment,retry_allowed=False,whole_queue_task_count=19584,attempted_job_count=1,**base))
    parents={'rolling_fitter_manifest':dict(runtime_versions=runtime,source_hashes=args['numerical_source_hashes']),'original8_inputs':{'scoring_inputs':args['original8_inputs']},'target_inputs':args['target_inputs']}
    return args,docs,refs,inputrefs,sources,parents


class Tests(unittest.TestCase):
    def test_full_physical_six_file_readback_without_fit(self):
        with TemporaryDirectory() as temp:
            root=Path(temp);parent=root/'parent';parent.mkdir();args,d,r,ir,s,parents=fixture(parent)
            with patch.object(m,'PARENT',parent),patch.object(m,'OUTPUT',root/'audit'),patch.object(m,'TASK_ID',args['assembled']['job_id']),patch.object(m,'POSTCHECK_SHA',r['postcheck']['sha256']),patch.object(m,'load_context',return_value=(parents,ir,s,args['channel_bindings'],args['assembled']['registered_job_preserved'])):
                out=m.readback(execute=True);report=m.loads(Path(out['path']).read_bytes());self.assertEqual(report['status'],'PASS');self.assertFalse(report['fit_called']);self.assertEqual(report['inspection']['window_count'],13)
                with self.assertRaises(ValueError):m.readback(execute=True)

    def test_runtime_closure_body_and_false_flags(self):
        with TemporaryDirectory() as temp:
            a,d,r,ir,s,p=fixture(Path(temp))
            with patch.object(m,'TASK_ID',a['assembled']['job_id']):
                m.inspect_envelopes(d,r,ir,s,p['rolling_fitter_manifest'])
                for mutate in (lambda x:x['raw_fit'].update(result=None),lambda x:x['raw_score'].update(returned_call_count=True),lambda x:x['postcheck']['worker_environment'].update(sys_flags_hash_randomization=1),lambda x:x['inputs'].update(source_hashes={'extra':'a'*64}),lambda x:x['score_inspection'].update(point_in_time_verified=0),lambda x:x['postcheck']['saved_references'].reverse()):
                    bad=deepcopy(d);mutate(bad)
                    with self.assertRaises(ValueError):m.inspect_envelopes(bad,r,ir,s,p['rolling_fitter_manifest'])

    def test_pending_before_io_and_failure_markers(self):
        with patch.object(m,'POSTCHECK_SHA',None),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaises(ValueError):m.readback(execute=True)
        with TemporaryDirectory() as temp:
            parent=Path(temp);p=parent/'x';p.write_bytes(b'original');(parent/'failure.json').write_bytes(b'{}')
            with self.assertRaises(ValueError):m.take(m.ref(p,m.sha(b'original')), {})


if __name__=='__main__':unittest.main()
