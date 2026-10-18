import copy
import unittest
from pathlib import PureWindowsPath
from backtest import ndx_h_failed_export_recovery_plan_research as m


def fixture():
    root = 'D:/synthetic/failed_h'; inventory = []
    def add(name, size=1, digest='a'*64):
        inventory.append(dict(path=name, sha256=digest, byte_count=size))
        return dict(path=str(PureWindowsPath(root) / name), sha256=digest)
    flags = {x: False for x in m.FLAGS}
    ids = [f'{i:064x}' for i in range(1632)]
    failure = dict(schema='DATED_H_WORKBOOK_EXTENSION_FAILURE_V1', status='FAILED_DO_NOT_CONSUME',
                   retry_allowed=False, stream_completed=True, all_attempts_retained=True,
                   error='ValueError: Full ordered task link cells', **flags)
    started = dict(schema='DATED_H_WORKBOOK_EXTENSION_STARTED_V1', default_task_id=ids[0], **flags)
    args = dict(parent_root=root, parent_inventory=inventory, failure=failure,
                failure_reference=add('failure.json'), started=started,
                started_reference=add('started.json'), index_reference=add('sources/index.json'),
                index={'task_index': [dict(task_ordinal=i, numerical_task_id=t) for i, t in enumerate(ids)]}, attempts=[])
    for i, (start, stop) in enumerate(((0, 1631), (1631, 1632))):
        directory = f'attempts/attempt-{i:05d}'
        identity = dict(attempt_index=i, start_task_ordinal=start, stop_task_ordinal=stop, task_ids=ids[start:stop])
        pending = dict(schema='DATED_H_EXPORT_ATTEMPT_V1', **identity,
                       status='PENDING_COMPLETE_STREAM_AND_SOURCE_PUBLICATION', bytes=10, sha256='a'*64,
                       reference=add(directory+'/artifact.xlsx', 10),
                       expected_cells_reference=add(directory+'/expected_cells.jsonl'),
                       chart_source_index_reference=add(directory+'/chart_source_index.json'),
                       previews=[dict(**add(directory+f'/preview-{j}.png'), worksheet=w, range=r) for j,(w,r) in enumerate((('路径查看','A1:G46'),('风险查看','A1:N43')))],
                       costs=dict(missing=False, taskCount=stop-start, taskIds=ids[start:stop], dataRows=20000), **flags)
        args['attempts'].append(dict(pending=pending, pending_reference=add(directory+'/pending.json'),
                                     started=dict(**identity, status='PENDING_EXPORT_ATTEMPT', **flags),
                                     started_reference=add(directory+'/started.json')))
        add(f'package-{i+1:04d}.xlsx',10)
    for name in ('tasks.jsonl','shared_display.json','classification.json','navigation_expected_cells.jsonl','attempts/navigation-artifact.xlsx','machine/tasks-00000.jsonl','sources/publication.json','sources/audit.json','sources/shared.json','sources/classification.json'):
        add(name)
    return args


class Tests(unittest.TestCase):
    def test_full_original_partition_and_no_authentication_or_actual_work(self):
        args=fixture(); before=copy.deepcopy(args); result=m.plan_failed_export_recovery(**args)
        self.assertEqual(args,before);self.assertEqual(result['planned_task_count'],1632)
        self.assertEqual(result['singleton_rebuild_count'],1)
        self.assertEqual(result['navigation_links'][-1],dict(worksheet='全部任务',cell='H1633',target='package-0002.xlsx',location="'任务索引'!A2"))
        self.assertFalse(result['source_bytes_authenticated']);self.assertFalse(result['machine_eof_verified'])

    def test_mutated_parent_and_partition_evidence_rejected(self):
        for fault in ('ordinal','flags','foreign','bytes','hash','extra','missing','machine'):
            a=fixture()
            if fault=='ordinal':a['index']['task_index'][0]['task_ordinal']=False
            elif fault=='flags':a['attempts'][0]['pending']['promotion_allowed']=0
            elif fault=='foreign':a['attempts'][0]['pending']['reference']['path']='D:/other/artifact.xlsx'
            elif fault=='bytes':a['attempts'][0]['pending']['bytes']=11
            elif fault=='hash':next(x for x in a['parent_inventory'] if x['path']=='package-0001.xlsx')['sha256']='b'*64
            elif fault=='extra':a['parent_inventory'].append(dict(path='export_manifest.json',sha256='a'*64,byte_count=1))
            elif fault=='missing':a['attempts'].pop()
            else:next(x for x in a['parent_inventory'] if x['path']=='machine/tasks-00000.jsonl')['byte_count']=2
            with self.subTest(fault=fault),self.assertRaises(ValueError):m.plan_failed_export_recovery(**a)

    def test_full_task_ids_cannot_be_reassigned_or_hidden_in_oversize(self):
        for fault in ('task','oversize'):
            a=fixture();p=a['attempts'][0]['pending']
            if fault=='task':p['task_ids'][0]='f'*64
            else:p['status']='OVERSIZE_ATTEMPT_NOT_ACCEPTED'
            with self.subTest(fault=fault),self.assertRaises(ValueError):m.plan_failed_export_recovery(**a)


if __name__=='__main__':unittest.main()
