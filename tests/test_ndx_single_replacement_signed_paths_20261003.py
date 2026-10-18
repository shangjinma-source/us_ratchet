from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
import json,tempfile,unittest
from scripts import ndx_single_replacement_signed_paths_20261003 as m
from backtest import ndx_single_replacement_evaluation_research as evaluator
from test_ndx_single_replacement_path_requests_research import fixture as request_fixture


@contextmanager
def physical(root,*,blocked=False):
    a=request_fixture();refs={};source={};saved={}
    def put(role,name,value=None,raw=None):
        p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw if raw is not None else m.enc(value));r=m.ref(p,m.filehash(p));refs[role]=r;saved[role]=value;return r
    for role in ('prepared_reader','paired_reader','selection_reader'):put(role,role+'.py',raw=b'# sealed synthetic reader identity\n')
    put('paired_readback_note','paired_note.md',raw=b'# Synthetic completed whole Markdown audit\n')
    # Full saved original requests/prices, never substitute a fake account API.
    if blocked:del a['old_paired_rows'][0]['paths']['candidate']['accounting_inputs']['sessions'][1]['open_prices']['Z']
    paired=put('paired','paired/accounts.json',dict(schema='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1',scenario_count=40,new_account_path_count=80,source_hashes={},rows=a['old_paired_rows']))
    put('paired_publication','paired/publication.json',dict(schema='OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS',account_reference=paired,source_hashes={},**dict.fromkeys(('point_in_time_verified','orders_executed','promotion_allowed','selected_plans_reselected','full_transitive_source_closure_reverified'),False)))
    (root/'paired/started.json').write_bytes(b'{}')
    prep=put('prepared','prepared/preparation.json',dict(schema='SOURCE_BOUND_SINGLE_REPLACEMENT_PREPARATION_V1',preparation=a['prepared']))
    pp=put('prepared_publication','prepared/publication.json',dict(schema='SINGLE_REPLACEMENT_PREPARATION_PUBLICATION_V1',preparation_reference=prep))
    (root/'prepared/started.json').write_bytes(b'{}');(root/'prepared/raw_preparation.json').write_bytes(b'{}')
    put('prepared_audit','prepared_audit/independent_readback.json',dict(schema='SINGLE_REPLACEMENT_PREPARATION_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=refs['prepared_reader']['sha256'],preparation_reference=prep,publication_reference=pp));(root/'prepared_audit/started.json').write_bytes(b'{}')
    s=a['selection']['document'];s['preparation_reference']=prep
    journal=root/'original_journal/journal.jsonl';journal.parent.mkdir();chunks=[];offset=0;previous='0'*64;rawlocs=[]
    for i,row in enumerate(s['rows']):
        chosen=row['selected'];task=chosen['task'];value=evaluator.evaluate_one(a['prepared']['document']['cases'][i]['identity']['original_input_row'],task);self_feasible=value['feasible'];assert self_feasible
        chosen['evaluation']=value
        for stage,payload in [('START',dict(task=task,dispatch_may_have_occurred=True)),('RAW_RETURNED',dict(call_invoked=True,call_count=1,returned=True,result=value,error=None,result_preserved_as_json=True)),('POSTCHECK',dict(outcome='FEASIBLE',validation_error=None))]:
            body=dict(schema='SINGLE_REPLACEMENT_JOURNAL_RECORD_V1',context_sha256='a'*64,sequence=len(chunks),previous_sha256=previous,global_ordinal=chosen['global_ordinal'],task_id=task['task_id'],stage=stage,payload=payload)
            h=m.sha(m.enc(body));line=m.enc(dict(body=body,record_sha256=h))+b'\n'
            if stage=='RAW_RETURNED':rawlocs.append(dict(sequence=len(chunks),byte_start=offset,byte_stop=offset+len(line),record_sha256=h,stage=stage,global_ordinal=chosen['global_ordinal']))
            chunks.append(line);previous=h;offset+=len(line)
    journal.write_bytes(b''.join(chunks));jr=m.ref(journal,m.filehash(journal));source[jr['path']]=jr['sha256']
    for i,row in enumerate(s['rows']):row['selected']['source_reference']=dict(journal_reference=jr,record_locator=rawlocs[i],json_pointer='/body/payload/result')
    if blocked:
        r=s['rows'][1];r.update(selected=None,status='NO_FEASIBLE',feasible_count=0,infeasible_count=r['integer_count']);s.update(feasible_count=39,infeasible_count=s['integer_count']-39,selected_case_count=39,no_feasible_case_count=1)
    a['selection']['content_sha256']=m.sha(m.enc(s));sr=put('selection_registration','selection_registration.json',dict(schema='SYNTHETIC_ALREADY_REGISTERED_SOURCE'))
    selection_flags=dict.fromkeys(('point_in_time_verified','full_ndx_certified','cross_family_winner_selected','account_executed','fit_executed','evaluation_reperformed','future_returns_used','execution_authorized','promotion_allowed','automatic_retry_allowed'),False)
    rawref=put('selection_raw','selection/raw_selection.json',dict(returned=True,result=a['selection']))
    startref=put('selection_started','selection/started.json',dict(schema='SINGLE_REPLACEMENT_SELECTION_STARTED_V1',registration_reference=sr,input_references={},source_hashes=source))
    selected=put('selection','selection/selection.json',dict(schema='SOURCE_BOUND_SINGLE_REPLACEMENT_SELECTION_V1',selection=a['selection'],raw_reference=rawref,registration_reference=sr,input_references={},source_hashes=source,**selection_flags))
    pub=put('selection_publication','selection/publication.json',dict(schema='SINGLE_REPLACEMENT_SELECTION_PUBLICATION_V1',status='PUBLISHED_PENDING_INDEPENDENT_READBACK',selection_reference=selected,started_reference=startref,raw_reference=rawref,registration_reference=sr,input_references={},source_hashes=source,**selection_flags))
    claims={**source,**{r['path']:r['sha256']for r in (rawref,startref,selected,pub,sr)}}
    put('selection_audit','selection_audit/independent_readback.json',dict(schema='SINGLE_REPLACEMENT_SELECTION_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=refs['selection_reader']['sha256'],selector_called=False,scope='INDEPENDENT_SAVED_FRACTION_RANKING_SHARED_AUTHENTICATED_JOURNAL_PARSER_NOT_REEVALUATION',registration_reference=sr,selection_reference=selected,publication_reference=pub,counts=dict(scenario_count=40,integer_count=s['integer_count']),source_hashes=claims,**selection_flags));(root/'selection_audit/started.json').write_bytes(b'{}')
    refs.pop('selection_raw');refs.pop('selection_started')
    rr=put('registration','registration.json',dict(schema='SINGLE_REPLACEMENT_SIGNED_PATH_SOURCE_REGISTRATION_V1',status='REGISTERED_SELECTED_SIGNED_PATHS_ONLY',scenario_count=40,integer_count=s['integer_count'],input_references=deepcopy(refs),**m.FLAGS));refs.pop('registration')
    with patch.multiple(m,BOUND={k:(r['path'],r['sha256'])for k,r in refs.items()if k in m.BOUND},SELECTION_PATHS={k:refs[k]['path']for k in m.SELECTION_PATHS},SELECTION_READER_SHA=refs['selection_reader']['sha256'],TOTAL=s['integer_count'],OUTPUT=root/'new_paths'),patch.object(m,'resource'):
        yield rr


class Tests(unittest.TestCase):
    def test_complete_physical_source_private_real40_accounts_and_inspection(self):
        with tempfile.TemporaryDirectory()as t,physical(Path(t))as rr:
            result=m.run(registration_reference=rr,execute=True);d=json.loads(Path(result['result']['path']).read_bytes())
            self.assertEqual(d['outcome_counts']['ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK'],40)
            self.assertEqual(len(d['rows']),40)
            for row in d['rows']:
                raw=json.loads(Path(row['raw_reference']['path']).read_bytes());self.assertTrue(raw['returned']);self.assertEqual(raw['result']['schema'],'SIGNED_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1')
                self.assertEqual(json.loads(Path(row['inspection_reference']['path']).read_bytes())['status'],'PASS')
            with self.assertRaises(ValueError):m.run(registration_reference=rr,execute=True)

    def test_original_blocks_and_full_eof_before_dispatch(self):
        with tempfile.TemporaryDirectory()as t,physical(Path(t),blocked=True)as rr:
            result=m.run(registration_reference=rr,execute=True);d=json.loads(Path(result['result']['path']).read_bytes());self.assertEqual(d['outcome_counts']['NO_FEASIBLE'],1);self.assertEqual(d['outcome_counts']['BLOCKED_TEMPLATE_PRICE_GAP'],1);self.assertEqual(d['outcome_counts']['ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK'],38)
        with tempfile.TemporaryDirectory()as t,physical(Path(t))as rr:
            c=m.load_inputs(rr);p=Path(c['refs']['paired']['path']);p.write_bytes(p.read_bytes()+b'junk')
            with patch.object(m,'load_inputs',return_value=c),patch.object(c['modules']['account'],'account_path',side_effect=AssertionError('No account before EOF')),self.assertRaises(ValueError):m.run(registration_reference=rr,execute=True)
            self.assertTrue((m.OUTPUT/'failure.json').exists());self.assertFalse((m.OUTPUT/'scenario-00').exists())

    def test_interrupt_and_late_output_drift_raw_preserved(self):
        for mode in ('interrupt','source','output'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory()as t,physical(Path(t))as rr:
                c=m.load_inputs(rr);account=c['modules']['account'].account_path;save=m.save
                def call(**kw):
                    if mode=='interrupt':raise KeyboardInterrupt('original synthetic interrupt')
                    result=account(**kw)
                    if mode=='source':Path(c['registration_reference']['path']).write_bytes(b'late drift')
                    return result
                def changed(path,value,**kw):
                    r=save(path,value,**kw)
                    if mode=='output'and Path(path).name=='publication.json':(m.OUTPUT/'started.json').write_bytes(b'drift')
                    return r
                with patch.object(m,'load_inputs',return_value=c),patch.object(c['modules']['account'],'account_path',call),patch.object(m,'save',changed),self.assertRaises(BaseException):m.run(registration_reference=rr,execute=True)
                self.assertTrue((m.OUTPUT/'scenario-00/raw_result.json').exists());self.assertTrue((m.OUTPUT/'failure.json').exists())
                if mode!='output':
                    d=json.loads((m.OUTPUT/'result.json').read_bytes());self.assertEqual(d['outcome_counts']['UNDISPATCHED'],39)
                    self.assertEqual(d['rows'][0]['outcome'],'ACCOUNT_EXCEPTION'if mode=='interrupt'else'VALIDATION_FAILURE')

    def test_pending_and_selected_original_raw_mismatch(self):
        with patch.object(Path,'read_bytes',side_effect=AssertionError('No IO')):
            with self.assertRaises(ValueError):m.run(execute=True)
        with tempfile.TemporaryDirectory()as t,physical(Path(t))as rr:
            c=m.load_inputs(rr,compile_numerical=False);self.assertEqual(set(c['modules']),{'stream'})
            p=Path(t)/'original_journal/journal.jsonl';p.write_bytes(p.read_bytes()+b'late')
            with self.assertRaises(ValueError):m.load_inputs(rr)


if __name__=='__main__':unittest.main()
