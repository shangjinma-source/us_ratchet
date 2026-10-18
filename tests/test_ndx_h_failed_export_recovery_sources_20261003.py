import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import ndx_h_failed_export_recovery_sources_20261003 as m


def physical_fixture(root):
    parent=root/'failed'; data=root/'data'; parent.mkdir();data.mkdir()
    digest=lambda b:hashlib.sha256(b).hexdigest()
    def put(p,v):
        p.parent.mkdir(parents=True,exist_ok=True)
        b=v if type(v) is bytes else json.dumps(v,ensure_ascii=False).encode()
        p.write_bytes(b);return {'path':str(p),'sha256':digest(b)}
    codes={}
    for role,(rel,h) in m.CODE.items():
        payload=(m.ROOT/rel).read_bytes() if role in ('plan','machine') else b'synthetic code not executed'
        p=root/rel;put(p,payload);codes[role]=(rel,digest(payload))
    refs={}; flags={k:False for k in ('formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','economics_recomputed','risk_recomputed','fit_performed','account_executed','independent_export_readback_passed','visual_acceptance_passed','workbook_delivered')}
    raw=b''; rows=[]; ids=[]
    for i in range(1632):
        tid=f'{i:064x}'; ids.append(tid);line=(json.dumps(dict(schema='DATED_WORKBOOK_TASK_EXTENSION_TABLES_V1',task_ordinal=i,numerical_task_id=tid,series={k:{'status':'AVAILABLE'} for k in ('candidate_integer','candidate_continuous')}))+'\n').encode()
        rows.append(dict(task_ordinal=i,numerical_task_id=tid,status='DISPLAY_PROJECTED',jsonl_record=dict(record_index=i,byte_start=len(raw),byte_stop=len(raw)+len(line),row_sha256=digest(line))))
        raw+=line
    refs['tasks']=put(data/'tasks.jsonl',raw)
    dflags={k:False for k in m.DATA_FALSE}
    allcode={k:{'path':str(root/p),'sha256':h} for k,(p,h) in codes.items()}
    shared={'schema':'DATED_WORKBOOK_EXTENSION_SHARED_DATA_V1'}
    classification={'schema':'DATED_WORKBOOK_CLASSIFICATION_TABLE_V1','rows':[{}]*101}
    refs['shared']=put(data/'shared_display.json',shared)
    refs['classification']=put(data/'classification.json',classification)
    index=dict(schema='SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1',planned_task_count=1632,
               projected_task_count=1632,not_supplied_task_count=0,full_new_cutoff_task_denominator='6222659648236112670',
               delivery_status='DISPLAY_DATA_ONLY_NOT_H_WORKBOOK_DELIVERY',
               task_index=rows,task_jsonl_reference={**refs['tasks'],'record_count':1632,'byte_count':len(raw)},
               shared_display_reference=refs['shared'],classification_reference=refs['classification'],
               source_hashes={allcode['data_producer']['path']:allcode['data_producer']['sha256']},**dflags)
    refs['index']=put(data/'index.json',index)
    pub=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_PUBLICATION_V1',status='PUBLISHED_DISPLAY_DATA_NOT_WORKBOOK_DELIVERY',index_reference=refs['index'],source_hashes=index['source_hashes'],**dflags)
    for k in ('task_jsonl_reference','shared_display_reference','classification_reference'):pub[k]=index[k]
    refs['publication']=put(data/'publication.json',pub)
    audit=dict(schema='DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1',status='PASS',index_reference=refs['index'],publication_reference=refs['publication'],reader_sha256=allcode['data_reader']['sha256'],producer_called=False,pure_projection_called=False,detail=dict(planned_tasks=1632,projected_tasks=1632,missing_tasks=0),classification_rows_verified=101,verified_jsonl_sha256=refs['tasks']['sha256'],verified_jsonl_bytes=len(raw),source_hashes={r['path']:r['sha256'] for r in [*refs.values(),allcode['data_producer'],allcode['data_reader']]},**dflags)
    refs['audit']=put(root/'audit/independent_readback.json',audit)
    put(data/'started.json',{})
    for role,obj in (('index',index),('publication',pub),('audit',audit),('shared',shared),('classification',classification)):put(parent/'sources'/(role+'.json'),obj)
    put(parent/'tasks.jsonl',raw);put(parent/'machine/tasks-00000.jsonl',raw)
    put(parent/'shared_display.json',shared);put(parent/'classification.json',classification)
    put(parent/'navigation_expected_cells.jsonl',b'{}\n');put(parent/'attempts/navigation-artifact.xlsx',b'synthetic nav')
    original_roles=('index','publication','audit','tasks','shared','classification','data_producer','data_reader','core','path_component','risk_component','navigation_component','native_helper')
    allrefs={**refs,**{k:{'path':str(root/p),'sha256':h} for k,(p,h) in codes.items()}}
    claims={allrefs[k]['path']:allrefs[k]['sha256'] for k in (*original_roles,'publisher')};claims.update(index['source_hashes']);claims.update(audit['source_hashes'])
    refs['started']=put(parent/'started.json',dict(schema='DATED_H_WORKBOOK_EXTENSION_STARTED_V1',default_task_id=ids[0],input_references={k:allrefs[k] for k in original_roles},source_hashes=claims,**flags))
    refs['failure']=put(parent/'failure.json',dict(schema='DATED_H_WORKBOOK_EXTENSION_FAILURE_V1',status='FAILED_DO_NOT_CONSUME',retry_allowed=False,stream_completed=True,all_attempts_retained=True,error='Full ordered task link cells',**flags))
    d=parent/'attempts/attempt-00000';identity=dict(attempt_index=0,start_task_ordinal=0,stop_task_ordinal=1632,task_ids=ids)
    put(d/'started.json',dict(**identity,status='PENDING_EXPORT_ATTEMPT',**flags))
    artifact=put(d/'artifact.xlsx',b'original workbook');put(parent/'package-0001.xlsx',b'original workbook')
    cells=put(d/'expected_cells.jsonl',b'{}\n');chart=put(d/'chart_source_index.json',dict(schema='DATED_H_PACKAGE_CHART_SOURCE_INDEX_V1',**identity,source_jsonl_records=[dict(numerical_task_id=r['numerical_task_id'],task_ordinal=r['task_ordinal'],source_record=r['jsonl_record']) for r in rows],**flags))
    previews=[dict(**put(d/f'preview-{i}.png',b'png'),worksheet=w,range=r) for i,(w,r) in enumerate((('路径查看','A1:G46'),('风险查看','A1:N43')))]
    put(d/'pending.json',dict(schema='DATED_H_EXPORT_ATTEMPT_V1',**identity,status='PENDING_COMPLETE_STREAM_AND_SOURCE_PUBLICATION',bytes=17,sha256=artifact['sha256'],reference=artifact,expected_cells_reference=cells,chart_source_index_reference=chart,previews=previews,costs=dict(missing=False,taskCount=1632,taskIds=ids,dataRows=10000),**flags))
    return refs,codes,parent


class Tests(unittest.TestCase):
    def test_pending_before_any_io(self):
        pending={k:dict(v) for k,v in m.BOUND.items()};pending['failure']['sha256']=None
        with patch.object(m,'BOUND',pending),patch.object(Path,'lstat',side_effect=AssertionError('IO')),patch.object(Path,'read_bytes',side_effect=AssertionError('IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):m.load_sources()

    def test_complete_physical_closed_sources_and_machine_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp); refs,codes,parent=physical_fixture(root)
            with patch.multiple(m,ROOT=root,PARENT=parent,BOUND=refs,CODE=codes):
                result=m.load_sources();self.assertEqual(result['machine']['record_count'],1632)
                self.assertEqual(result['plan']['package_count'],1);m.guard(result)
                (parent/'machine/tasks-00000.jsonl').write_bytes(b'drift')
                with self.assertRaisesRegex(ValueError,'bytes changed'):m.guard(result)

    def test_missing_original_role_and_unexpected_parent_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);refs,codes,parent=physical_fixture(root)
            with patch.multiple(m,ROOT=root,PARENT=parent,BOUND=refs,CODE=codes):
                c=m.load_sources();(parent/'new-unknown').write_bytes(b'x')
                with self.assertRaisesRegex(ValueError,'inventory changed'):m.guard(c)


if __name__=='__main__':unittest.main()
