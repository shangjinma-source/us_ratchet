from copy import deepcopy
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch
import tempfile
import unittest
from backtest import ndx_double_replacement_domain_research as domain
from backtest import ndx_double_replacement_compressed_batch_research as codec
from backtest import ndx_double_replacement_compressed_raw_inspection_research as decoder
from backtest import ndx_double_stream_selection_research as pure
from backtest import ndx_double_stream_selection_inspection_research as checker
from scripts import ndx_double_stream_selection_sources_20261008 as io
from scripts import ndx_double_stream_selection_20261008 as publisher
from scripts import ndx_double_stream_selection_independent_readback_20261008 as reader
from test_ndx_double_replacement_domain_research import fixture as original_fixture

def fixture(cases=2,expanded=False):
    source=original_fixture();first=source['original_rows'][0];source['original_rows']=[];source['action_contract']['expected_scenario_ids']=[]
    if expanded:
        r=first['input_row'];r['holdings']['E']=1;r['execution_prices'].update(E='5',F='5');r['target_weights']['F']='0.1'
        r['allowed_buy_security_ids']=sorted(r['target_weights'])
        for sid in ('E','F'):r['securities'][sid]=dict(ticker=sid,issuer_id='issuer:'+sid,risk_chain='chain:'+sid)
    for i in range(cases):
        item=deepcopy(first);item['input_row']['scenario_id']=f'case{i}';item['input_reference']['json_pointer']=f'/rows/{i}';source['original_rows'].append(item);source['action_contract']['expected_scenario_ids'].append(f'case{i}')
    prep=domain.prepare_double_replacement_domain(**source);records=[]
    for ordinal in range(prep['document']['integer_count']):
        task=domain.unrank(prep,ordinal);ci=task['scenario_index'];target=source['original_rows'][ci]['input_row']['target_weights'];weights={'C':'1/2','D':'1/2'}
        l1=sum((abs(Fraction(weights.get(s,'0'))-Fraction(target.get(s,'0')))for s in set(weights)|set(target)),Fraction())
        feasible=ci%2==0;checks=dict(zip(('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT'),[feasible,True,True,True,True]));status='FEASIBLE'if feasible else'INFEASIBLE'
        evaluation=dict(status=status,feasible=feasible,risk=dict(weights=weights,checks=checks,all_passed=feasible),financial_checks=dict(NONNEGATIVE_CASH=True,CASH_BUFFER=True),issuer_conflicts={},original_target_stock_l1=str(l1),total_fee_usd='3',sell_fee_usd='1',buy_fee_usd='2')
        records.append(dict(raw=dict(supplied_index=ordinal,plan=dict(global_ordinal=ordinal,task=task),status=status,evaluation=evaluation),locator=dict(synthetic_ordinal=ordinal)))
    counts=dict.fromkeys(pure.KINDS,0);counts['inspected_feasible']=sum(r['raw']['status']=='FEASIBLE'for r in records);counts['inspected_infeasible']=len(records)-counts['inspected_feasible']
    audit=dict(schema='DOUBLE_REPLACEMENT_C_STREAM_INDEPENDENT_READBACK_V1',status='PASS_FULL_DOMAIN',inspection=dict(full_domain_complete=True,status='FULL_NUMERIC_DOMAIN',original_integer_count=len(records),next_undispatched_ordinal=len(records),counts=counts))
    return prep,records,audit

def physical(root):
    prep,records,audit=fixture();total=len(records);out=root/'original';request=out/'requests/request-000000';request.mkdir(parents=True);aroot=root/'audit';aroot.mkdir();sources={}
    for folder in (request,aroot):io.save(folder/'started.json',{})
    mlines=[];alines=[];mprev=aprev=None
    for bi,start in enumerate(range(0,total,4)):
        folder=out/f'batches/{bi//1000:03d}/{bi:09d}';folder.mkdir(parents=True);span=dict(batch_index=bi,start=start,stop=min(start+4,total),point_count=min(4,total-start));descriptor=dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_DESCRIPTOR_V1',plan_sha256='a'*64,**span)
        items=deepcopy([r['raw']for r in records[start:span['stop']]])
        for index,item in enumerate(items):item['supplied_index']=index
        raw=dict(status='ALL_SUPPLIED_EVALUATED',results=items);packed,metadata=codec.encode_canonical_gzip(raw,max_compressed_bytes=45050408,max_uncompressed_bytes=45036633);(folder/'raw_return.json.gz').write_bytes(packed)
        rawref=dict(**io.ref(folder/'raw_return.json.gz'),byte_count=len(packed));decoded=decoder.inspect_gzip_raw(compressed_bytes=packed,metadata=metadata,max_compressed_bytes=45050408,max_uncompressed_bytes=45036633)
        io.save(folder/'raw_receipt.json',dict(descriptor=descriptor,raw_reference=rawref,codec_metadata=metadata))
        for name in ('started.json','raw_byte_inspection.json','inspection.json','result.json'):io.save(folder/name,{})
        files=[dict(filename=p.name,sha256=io.filehash(p),byte_count=p.stat().st_size)for p in sorted(folder.iterdir())];terminal=dict(**io.ref(folder/'result.json'),byte_count=(folder/'result.json').stat().st_size)
        envelope=io.save(folder/'stream_result.json',dict(descriptor=descriptor,terminal_reference=terminal,files=files))
        counts=dict.fromkeys(pure.KINDS,0)
        for item in items:counts['inspected_feasible'if item['status']=='FEASIBLE'else'inspected_infeasible']+=1
        m=dict(schema='DOUBLE_REPLACEMENT_STREAM_BATCH_REFERENCE_V1',sequence=bi,previous_record_sha256=mprev,context_sha256='b'*64,descriptor=span,batch_result_reference=envelope,counts=counts,terminal_status='COMPLETE_NUMERIC_BATCH');mprev=io.digest(m);mlines.append(io.encode(dict(record=m,record_sha256=mprev))+b'\n')
        a=dict(schema='DOUBLE_REPLACEMENT_STREAM_BATCH_READBACK_V1',sequence=bi,previous_record_sha256=aprev,source_manifest_record_sha256=mprev,batch_reference=envelope,descriptor=descriptor,inspection=dict(inspection_error=None,original_failure_preserved=False,arithmetic_inspection=dict(status='PASS_SAVED_RESULT_EVIDENCE',all_supplied_plans_numerically_checked=True),raw_byte_inspection=decoded['inspection']),**dict.fromkeys(io.FALSE,False));aprev=io.digest(a);alines.append(io.encode(dict(record=a,record_sha256=aprev))+b'\n')
    def stream_ref(path,lines,last):
        path.write_bytes(b''.join(lines));return dict(**io.ref(path),byte_count=path.stat().st_size,record_count=len(lines),last_record_sha256=last)
    mref=stream_ref(request/'batch_manifest.jsonl',mlines,mprev);aref=stream_ref(aroot/'batch_readback.jsonl',alines,aprev)
    flags=dict.fromkeys(io.FALSE,False);prep_ref=io.save(root/'preparation.json',dict(preparation=prep));reg=io.save(root/'registration.json',dict(input_references=dict(preparation=prep_ref)))
    worker=io.save(root/'worker.json',{});auditreader=io.save(root/'reader.json',{})
    for r in (worker,auditreader):sources[r['path']]=r['sha256']
    result=dict(schema='DOUBLE_REPLACEMENT_C_STREAM_REQUEST_RESULT_V1',stopped=None,registration_reference=reg,manifest_reference=mref,inspection=audit['inspection'],context=dict(content_sha256='b'*64,document=dict(prepared_content_sha256=prep['content_sha256'])),source_hashes=sources,started_reference=io.ref(request/'started.json'),batch_folder_count=len(mlines),**flags)
    resultref=io.save(request/'result.json',result);pubref=io.save(out/'publication.json',dict(schema='DOUBLE_REPLACEMENT_C_STREAM_EXECUTION_PUBLICATION_V1',full_domain_complete=True,result_reference=resultref,registration_reference=reg,manifest_reference=mref,**flags))
    audit.update(registration_reference=reg,request_reference=resultref,publication_reference=pubref,source_manifest_reference=mref,batch_readback_reference=aref,source_hashes=sources,**flags);auditref=io.save(aroot/'independent_readback.json',audit)
    refs=dict(preparation=prep_ref,request=resultref,publication=pubref,audit=auditref,reader=auditreader,worker=worker,registration=reg,decoder=io.ref(Path(decoder.__file__)))
    constants=dict(TOTAL=total,SCENARIOS=2,PAIRS=2,PREPARATION_SHA=prep_ref['sha256'],READER_SHA=auditreader['sha256'],WORKER_SHA=worker['sha256'])
    return refs,constants

class Tests(unittest.TestCase):
    def test_final_reader_pin_required_before_source_io(self):
        with patch.object(io,'READER_SHA',None),patch.object(io,'guard',side_effect=AssertionError('Unexpected source IO')):
            with self.assertRaisesRegex(ValueError,'Pending'):
                io.prepare({key:dict(path='not-read',sha256='a'*64)for key in io.ROLES})
    def test_outpair_inpair_quantity_ties_keep_registered_stable_first(self):
        prep,records,audit=fixture(1,expanded=True)
        self.assertGreater(prep['document']['pair_count'],1)
        result=pure.select(prepared=prep,audit=audit,records=iter(records))
        self.assertEqual(result['rows'][0]['selected'],records[0])
        checker.inspect(prepared=prep,audit=audit,records=iter(records),selection=result)
        for candidate in (next(r for r in records if r['raw']['plan']['task']['identity']['outgoing_security_ids']!=records[0]['raw']['plan']['task']['identity']['outgoing_security_ids']),next(r for r in records if r['raw']['plan']['task']['identity']['incoming_security_ids']!=records[0]['raw']['plan']['task']['identity']['incoming_security_ids'])):
            altered=deepcopy(result);altered['rows'][0]['selected']=candidate
            with self.assertRaises(ValueError):checker.inspect(prepared=prep,audit=audit,records=iter(records),selection=altered)
    def test_full40_and_stable_q1q2_no_feasible(self):
        prep,records,audit=fixture(40);result=pure.select(prepared=prep,audit=audit,records=iter(records));self.assertEqual(len(result['rows']),40)
        self.assertEqual(sum(x['status']=='NO_FEASIBLE'for x in result['rows']),20);self.assertEqual(result['rows'][0]['selected']['raw']['plan']['task']['identity']['buy_quantities'],[1,1])
        report=checker.inspect(prepared=prep,audit=audit,records=iter(records),selection=result);self.assertEqual(report['integer_count'],160)
        changed=deepcopy(result);changed['rows'][0]['selected']=records[1]
        with self.assertRaises(ValueError):checker.inspect(prepared=prep,audit=audit,records=iter(records),selection=changed)
    def test_complete_eof_order_objective_and_partial_rejections(self):
        prep,records,audit=fixture()
        for mode in ('missing','extra','reorder','l1','fee','bool','technical','partial','unknown'):
            rr=deepcopy(records);aa=deepcopy(audit)
            if mode=='missing':rr.pop()
            elif mode=='extra':rr.append(rr[-1])
            elif mode=='reorder':rr[0],rr[1]=rr[1],rr[0]
            elif mode=='l1':rr[0]['raw']['evaluation']['original_target_stock_l1']='99'
            elif mode=='fee':rr[0]['raw']['evaluation']['total_fee_usd']='99'
            elif mode=='bool':rr[0]['raw']['plan']['task']['identity']['buy_quantities'][0]=True
            elif mode=='technical':rr[0]['raw']['status']='EVALUATION_EXCEPTION'
            elif mode=='partial':aa['inspection']['full_domain_complete']=False
            else:aa['inspection']['counts']['unresolved_dispatch_or_raw']=1
            with self.subTest(mode=mode),self.assertRaises(ValueError):pure.select(prepared=prep,audit=aa,records=iter(rr))
    def test_real_gzip_manifest_audit_and_original_locator(self):
        with tempfile.TemporaryDirectory()as tmp:
            refs,constants=physical(Path(tmp))
            with patch.multiple(io,**constants):
                state=io.prepare(refs);result=pure.select(prepared=state['prepared'],audit=state['audit'],records=io.records(state));selected=result['rows'][0]['selected']
                self.assertEqual(selected['locator']['json_tokens'],['results',0]);self.assertEqual(io.filehash(selected['locator']['raw_reference']['path']),selected['locator']['raw_reference']['sha256'])
                checker.inspect(prepared=state['prepared'],audit=state['audit'],records=io.records(state),selection=result)
                list(io.records(state,metadata_only=True));Path(selected['locator']['raw_reference']['path']).write_bytes(b'wrong')
                with self.assertRaises(ValueError):list(io.records(state))
    def test_full_source_publication_independent_readback_and_failed_namespace(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);refs,constants=physical(root);bound={k:(r['path'],r['sha256'])for k,r in refs.items()};iosha=io.filehash(io.__file__);puresha=io.filehash(pure.__file__)
            def publish_module(path,sha):return io if Path(path)==publisher.IO else pure
            def read_module(path,sha):return io if Path(path)==reader.IO else checker
            with patch.multiple(io,**constants),patch.multiple(publisher,OUTPUT=root/'selected',BOUND=bound,IO_SHA=iosha,PURE_SHA=puresha),patch.object(publisher,'module',side_effect=publish_module):
                selection=publisher.run(execute=True)
                with patch.multiple(reader,OUTPUT=root/'selected_audit',BOUND=bound,IO_SHA=iosha,PURE_SHA=puresha,CHECKER_SHA=io.filehash(checker.__file__),PUBLISHER_SHA=publisher.LOADED,SELECTION_REFERENCE=selection,PUBLICATION_REFERENCE=io.ref(root/'selected/publication.json')),patch.object(reader,'module',side_effect=read_module):
                    result=io.read(reader.run(execute=True));self.assertEqual(result['status'],'PASS_COMPLETE_DOMAIN')
                    io.save(root/'selected/failure.json',{})
                    with self.assertRaises(ValueError):reader.run(execute=True)
    def test_audit_eof_unindexed_and_failure_reject(self):
        for mode in ('audit','unindexed','failure'):
            with tempfile.TemporaryDirectory()as tmp:
                refs,constants=physical(Path(tmp))
                with patch.multiple(io,**constants):
                    state=io.prepare(refs)
                    if mode=='audit':
                        with Path(state['audit']['batch_readback_reference']['path']).open('ab')as f:f.write(b'{}\n')
                    elif mode=='unindexed':(state['root']/'batches/000/000000002').mkdir()
                    else:io.save(state['request_folder']/'failure.json',{})
                    with self.assertRaises((ValueError,KeyError)):list(io.records(state))

if __name__=='__main__':unittest.main()
