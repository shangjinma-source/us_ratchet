"""Physical saved-input fixtures, derived-only publication and independent math."""
from datetime import date,timedelta
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from scripts import ndx_candidate_saved_risk_diagnostic_20261008 as publisher
from scripts import ndx_candidate_saved_risk_diagnostic_independent_readback_20261008 as reader
from backtest import ndx_candidate_daily_risk_projection_research as projection
from backtest import ndx_candidate_saved_risk_inspection_research as checker


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':')).encode()


class Tests(unittest.TestCase):
    def fixture(self,root):
        def put(path,value):
            path=root/path;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(encode(value))
            return dict(path=str(path),sha256=sha(path))
        calendar=[str(date(2020,1,1)+timedelta(days=i))for i in range(120)]
        state=dict(calendar=calendar,closes=dict(index=calendar,columns=['A','B'],data=[[1.1,2.3]for _ in calendar]),internal_columns_by_security={'SID/~A':'A','SID-B':'B'},risk_chains_by_decision={calendar[0]:{'SID/~A':'first','SID-B':'second'},calendar[65]:{'SID/~A':'second'}})
        daily=[dict(session=session,holdings={}if i==0 else{'SID/~A':dict(ticker='A',shares=1.25),'SID-B':dict(ticker='B',shares=.5)})for i,session in enumerate(calendar)]
        inputrows=[dict(fx_mode='FX',lane='L'+str(i),tracks=[dict(track='CONTINUOUS',stateful_input=state),dict(track='WHOLE')])for i in range(8)]
        refs={};executionrows=[];checked=[];trackhashes={}
        for stage in ('inputs','execution'):
            readerref=put(f'{stage}_reader.json',{'inert':True});refs[stage+'_reader']=readerref
            start=put(f'{stage}/started.json',dict(source_hashes={}))
            if stage=='inputs':doc=dict(inputs={'rows':inputrows},source_hashes={},point_in_time_verified=False,promotion_allowed=False)
            else:
                for index in range(16):
                    track='CONTINUOUS'if index%2==0 else'WHOLE';blocked=index<8
                    startref=put(f'execution/tracks/{index:02d}/started.json',{'track_index':index})
                    postref=put(f'execution/tracks/{index:02d}/postcheck.json',{'track_index':index})
                    rawref=None if blocked else put(f'execution/tracks/{index:02d}/raw_result.json',dict(error=None,returned=True,original_return_is_json=True,started_reference=startref,result=dict(daily=daily)))
                    row=dict(track_index=index,fx_mode='FX',lane='L'+str(index//2),track=track,call_invoked=not blocked,returned_call_count=0 if blocked else 1,
                             outcome='BLOCKED_ORIGINAL_INPUT_NO_ACCOUNT'if blocked else'ACCOUNT_RETURNED_PENDING_INDEPENDENT_READBACK',started_reference=startref,postcheck_reference=postref,raw_reference=rawref)
                    executionrows.append(row);saved={key:row[key]for key in ('started_reference','postcheck_reference','raw_reference')}
                    checked.append(dict(track_index=index,coordinate=['FX','L'+str(index//2),track],outcome=row['outcome'],saved_references=saved,inspection={'status':'PASS'}))
                    for ref in saved.values():
                        if ref is not None:trackhashes[ref['path']]=ref['sha256']
                inputrefs=dict(inputs=refs['inputs'],publication=refs['inputs_publication'],readback=refs['inputs_audit'],reader=refs['inputs_reader'])
                doc=dict(rows=executionrows,failure=None,input_references=inputrefs,source_hashes={},point_in_time_verified=False,promotion_allowed=False)
            filename='inputs.json'if stage=='inputs'else'result.json';key='inputs_reference'if stage=='inputs'else'result_reference'
            schema='MULTIDECISION_STATEFUL_ACCOUNT_INPUTS'if stage=='inputs'else'MULTIDECISION_ACCOUNT_EXECUTION'
            doc['schema']=schema+('_DOCUMENT_V1'if stage=='inputs'else'_RESULT_V1')
            refs[stage]=put(f'{stage}/{filename}',doc)
            pub=dict(schema=schema+'_PUBLICATION_V1',status='PUBLISHED_INPUTS_PENDING_INDEPENDENT_READBACK_NOT_ACCOUNTS'if stage=='inputs'else'PUBLISHED_CONDITIONAL_ACCOUNT_RETURNS_PENDING_INDEPENDENT_READBACK',started_reference=start,source_hashes={},point_in_time_verified=False,promotion_allowed=False,**{key:refs[stage]})
            if stage=='execution':pub['input_references']=inputrefs
            refs[stage+'_publication']=put(f'{stage}/publication.json',pub)
            hashes={ref['path']:ref['sha256']for ref in (refs[stage],refs[stage+'_publication'],readerref)}
            if stage=='execution':hashes.update(trackhashes)
            audit=dict(schema=schema+'_INDEPENDENT_READBACK_V1',status='PASS',reader_sha256=readerref['sha256'],publication_reference=refs[stage+'_publication'],source_hashes=hashes,point_in_time_verified=False,promotion_allowed=False,**{key:refs[stage]})
            if stage=='execution':audit['rows']=checked
            refs[stage+'_audit']=put(f'{stage}_audit/independent_readback.json',audit)
            put(f'{stage}_audit/started.json',dict(publication_reference=refs[stage+'_publication'],**{key:refs[stage]}))
        constants=dict(OUTPUT=root/'derived',BOUND={key:(value['path'],value['sha256'])for key,value in refs.items()},IO_SHA=sha(publisher.IO),DIAGNOSTIC_SHA=sha(publisher.DIAGNOSTIC),PROJECTION_SHA=sha(publisher.PROJECTION))
        return constants,state,daily

    def publish(self,constants):
        with patch.multiple(publisher,**constants):return publisher.run(execute=True)

    def inspect(self,constants):
        patches={key:constants[key]for key in ('BOUND','IO_SHA','DIAGNOSTIC_SHA','PROJECTION_SHA')}
        patches.update(PARENT=constants['OUTPUT'],OUTPUT=constants['OUTPUT'].parent/'readback',CHECKER_SHA=sha(reader.CHECKER),PUBLISHER_SHA=sha(reader.PUBLISHER),RESULT_SHA=sha(constants['OUTPUT']/'diagnostics.json'),PUBLICATION_SHA=sha(constants['OUTPUT']/'publication.json'))
        load=reader.module
        def no_producer(path,digest):
            self.assertNotIn(Path(path),(reader.PUBLISHER,reader.DIAGNOSTIC,reader.PROJECTION))
            return load(path,digest)
        with patch.multiple(reader,**patches),patch.object(reader,'module',no_producer),patch.object(publisher,'run',side_effect=AssertionError('producer forbidden')):
            return reader.run(execute=True)

    def test_pending_before_input_io(self):
        with patch.object(publisher,'IO_SHA',None),patch.object(publisher,'module',side_effect=AssertionError('no IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):publisher.run(execute=True)
        with patch.object(reader,'IO_SHA',None),patch.object(reader,'module',side_effect=AssertionError('no IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):reader.run(execute=True)

    def test_full_physical_publication_and_independent_480(self):
        with tempfile.TemporaryDirectory()as directory:
            constants,state,daily=self.fixture(Path(directory));self.publish(constants)
            report=json.loads(Path(self.inspect(constants)['path']).read_bytes())
            self.assertEqual(report['inspection']['path_day_count'],480)
            self.assertEqual(report['inspection']['numeric_day_count'],476)
            self.assertEqual(report['inspection']['undefined_all_cash_day_count'],4)
            self.assertFalse(report['account_executed']);self.assertFalse(report['original_saved_risk'])
            with self.assertRaisesRegex(ValueError,'Create-only'):self.publish(constants)

    def test_resigned_arithmetic_and_locator_rejected(self):
        for mutation in ('value','locator','future'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory()as directory:
                constants,state,daily=self.fixture(Path(directory));self.publish(constants)
                path=constants['OUTPUT']/'diagnostics.json';value=json.loads(path.read_bytes());row=value['paths'][0]['projection']['rows'][1]
                if mutation=='value':row['diagnostic']['metrics']['hhi']['numerator']='1'
                elif mutation=='locator':row['source_locator_tokens']['SID/~A']['quantity_tokens'][-1]='ticker'
                else:row['diagnostic']['label_observations']['SID/~A']['observation_session']='2099-01-01'
                path.write_bytes(encode(value));pubpath=constants['OUTPUT']/'publication.json';pub=json.loads(pubpath.read_bytes());pub['diagnostics_reference']['sha256']=sha(path);pubpath.write_bytes(encode(pub))
                with self.assertRaises(ValueError):self.inspect(constants)
                self.assertTrue((Path(directory)/'readback/failure.json').exists())

    def test_upstream_failure_and_extra_inventory_refused(self):
        for filename in ('failure.json','unexpected.json'):
            with self.subTest(filename=filename),tempfile.TemporaryDirectory()as directory:
                constants,_,_=self.fixture(Path(directory));(Path(directory)/'execution'/filename).write_text('{}')
                with self.assertRaises(ValueError):self.publish(constants)
                self.assertFalse(constants['OUTPUT'].exists())

    def test_independent_fraction_asof_null_and_positive_validation(self):
        with tempfile.TemporaryDirectory()as directory:
            _,state,daily=self.fixture(Path(directory))
            expected=checker.expected_projection(state,daily)
            self.assertEqual(expected,projection.project_path(stateful_input=state,daily=daily))
            self.assertIsNone(expected['rows'][0]['diagnostic']['metrics'])
            self.assertEqual(expected['rows'][65]['diagnostic']['chain_weights'],{'second':{'numerator':'1','denominator':'1'}})
            daily[1]['holdings']['SID/~A']['shares']=True
            with self.assertRaises(ValueError):checker.expected_projection(state,daily)
