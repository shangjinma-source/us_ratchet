"""Physical synthetic double-selection/paired-price sources, never real points."""
from copy import deepcopy
from pathlib import Path
from contextlib import ExitStack
from unittest.mock import patch
import json,tempfile,unittest
from scripts import ndx_double_replacement_signed_paths_20261008 as source
from scripts import ndx_double_replacement_signed_paths_independent_readback_20261008 as reader
from backtest import ndx_double_replacement_compressed_batch_research as codec
from backtest import ndx_double_replacement_compressed_raw_inspection_research as decoder
from test_ndx_double_replacement_signed_paths_20261008 import fixture

def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(source.enc(value));return source.ref(path,source.filehash(path))

def physical(root):
    args=fixture();selection=args['selection'];prepdir=root/'prepared';pairdir=root/'paired';seldir=root/'selection';auditdir=root/'selection_audit';origin=root/'original';origin.mkdir()
    prepared=write(prepdir/'preparation.json',dict(preparation=args['prepared']))
    for name in ('started.json','raw_preparation.json','publication.json'):write(prepdir/name,{})
    paired=write(pairdir/'accounts.json',dict(schema='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1',scenario_count=40,new_account_path_count=80,source_hashes={},rows=args['old_paired_rows']))
    pp=write(pairdir/'publication.json',dict(schema='OLD_HOLDING_TOPUP_PAIRED_ACCOUNT_PUBLICATION_V1',status='PUBLISHED_CONDITIONAL_PRICE_ONLY_PAIRED_PATHS',account_reference=paired,source_hashes={}));write(pairdir/'started.json',{})
    note=root/'old_readback.md';note.write_text('Synthetic old readback only.');oldreader=write(root/'old_reader.json',{});selreader=write(root/'selection_reader.json',{})
    manifest=b'';auditlines=b'';locators=[]
    for i,row in enumerate(selection['rows']):
        chosen=row['selected'];raw=chosen['raw'];folder=origin/f'batches/{i:03d}';folder.mkdir(parents=True)
        packed,meta=codec.encode_canonical_gzip(dict(results=[raw]),max_compressed_bytes=45050408,max_uncompressed_bytes=45036633);(folder/'raw_return.json.gz').write_bytes(packed);rawref=dict(path=str(folder/'raw_return.json.gz'),sha256=source.filehash(folder/'raw_return.json.gz'),byte_count=len(packed))
        decoded=decoder.inspect_gzip_raw(compressed_bytes=packed,metadata=meta,max_compressed_bytes=45050408,max_uncompressed_bytes=45036633)
        write(folder/'raw_receipt.json',dict(raw_reference=rawref,codec_metadata=meta))
        for name in ('started.json','raw_byte_inspection.json','inspection.json','result.json'):write(folder/name,{})
        files=[dict(filename=p.name,sha256=source.filehash(p),byte_count=p.stat().st_size)for p in sorted(folder.iterdir())]
        evidence=write(folder/'stream_result.json',dict(files=files))
        m=dict(sequence=i,batch_result_reference=evidence);mh=source.sha(source.enc(m));mb=source.enc(dict(record=m,record_sha256=mh))+b'\n'
        a=dict(sequence=i,source_manifest_record_sha256=mh,batch_reference=evidence,inspection=dict(raw_byte_inspection=decoded['inspection']));ah=source.sha(source.enc(a));ab=source.enc(dict(record=a,record_sha256=ah))+b'\n'
        locators.append(dict(raw_reference=rawref,json_tokens=['results',0],manifest=dict(line_index=i,byte_start=len(manifest),byte_stop=len(manifest)+len(mb),record_sha256=mh),independent_audit=dict(line_index=i,byte_start=len(auditlines),byte_stop=len(auditlines)+len(ab),record_sha256=ah)))
        manifest+=mb;auditlines+=ab
    mpath=origin/'manifest.jsonl';mpath.write_bytes(manifest);apath=origin/'readback.jsonl';apath.write_bytes(auditlines)
    mref=dict(path=str(mpath),sha256=source.filehash(mpath));aref=dict(path=str(apath),sha256=source.filehash(apath))
    for row,loc in zip(selection['rows'],locators):loc['manifest']['reference']=mref;loc['independent_audit']['reference']=aref;row['selected']['locator']=loc
    original=write(origin/'audit/independent_readback.json',dict(schema='DOUBLE_REPLACEMENT_C_STREAM_INDEPENDENT_READBACK_V1',status='PASS_FULL_DOMAIN',source_manifest_reference=mref,batch_readback_reference=aref,request_reference=dict(path=str(origin/'requests/request-000000/result.json'),sha256='a'*64)))
    flags=dict.fromkeys(('evaluation_reperformed','account_executed','orders_executed','fit_executed','future_returns_used','cross_family_winner_selected','point_in_time_verified','promotion_allowed','full_ndx_certified','execution_authorized'),False)
    inputrefs=dict(preparation=prepared,audit=original)
    sel=write(seldir/'selection.json',dict(schema='DOUBLE_STREAM_SELECTION_DOCUMENT_V1',selection=selection,input_references=inputrefs,**flags));sp=write(seldir/'publication.json',dict(schema='DOUBLE_STREAM_SELECTION_PUBLICATION_V1',selection_reference=sel,input_references=inputrefs,**flags));write(seldir/'started.json',{})
    hashes={r['path']:r['sha256']for r in (sel,sp,selreader,original)}
    sa=write(auditdir/'independent_readback.json',dict(schema='DOUBLE_STREAM_SELECTION_INDEPENDENT_READBACK_V1',status='PASS_COMPLETE_DOMAIN',selection_reference=sel,publication_reference=sp,input_references=inputrefs,source_hashes=hashes,**flags));write(auditdir/'started.json',{})
    refs=dict(prepared=prepared,paired=paired,paired_publication=pp,paired_readback_note=source.ref(note,source.filehash(note)),paired_reader=oldreader,selection=sel,selection_publication=sp,selection_audit=sa,selection_reader=selreader)
    bound={k:(r['path'],r['sha256'])for k,r in refs.items()if k in source.BOUND};paths={k:refs[k]['path']for k in source.SELECTION_PATHS};code=deepcopy(source.CODE);p,h=code['requests'];code['requests']=(p,source.filehash(source.ROOT/p))
    reg=write(root/'registration.json',dict(schema='DOUBLE_REPLACEMENT_SIGNED_PATH_SOURCE_REGISTRATION_V1',status='REGISTERED_SELECTED_SIGNED_PATHS_ONLY',scenario_count=40,integer_count=selection['integer_count'],input_references=refs,**source.FLAGS))
    return reg,dict(BOUND=bound,SELECTION_PATHS=paths,SELECTION_READER_SHA=selreader['sha256'],TOTAL=selection['integer_count'],CODE=code,OUTPUT=root/'signed')

class Tests(unittest.TestCase):
    def test_full_physical_publisher_and_independent_readback(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);reg,constants=physical(root)
            with patch.multiple(source,**constants),patch.object(source,'resource'):
                output=source.run(registration_reference=reg,execute=True)
                with patch.multiple(reader,OUTPUT=root/'readback',PUBLISHER_SHA=source.LOADED):
                    report=reader.readback(registration_reference=reg,result_reference=output['result'],publication_reference=output['publication'],execute=True)
                    value=json.loads(Path(report['path']).read_bytes());self.assertEqual(value['account_checked_count'],40);self.assertEqual(value['status'],'PASS')
    def test_failure_after_first_return_preserves_full_partition_no_retry(self):
        with tempfile.TemporaryDirectory()as temp:
            root=Path(temp);reg,constants=physical(root);original=source.preserve_call;calls=[]
            def fail_second(path,function,kwargs):
                if Path(path).name=='raw_result.json':
                    calls.append(path)
                    if len(calls)==2:
                        def failure(**kwargs):raise RuntimeError('Synthetic account exception')
                        function=failure
                return original(path,function,kwargs)
            with patch.multiple(source,**constants),patch.object(source,'resource'),patch.object(source,'preserve_call',side_effect=fail_second):
                with self.assertRaises(RuntimeError):source.run(registration_reference=reg,execute=True)
                result=json.loads((root/'signed/result.json').read_bytes());self.assertEqual(result['outcome_counts']['ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK'],1);self.assertEqual(result['outcome_counts']['ACCOUNT_EXCEPTION'],1);self.assertEqual(result['outcome_counts']['UNDISPATCHED'],38);self.assertEqual(len(calls),2)
                with self.assertRaises(ValueError):source.run(registration_reference=reg,execute=True)
                self.assertEqual(len(calls),2);self.assertTrue((root/'signed/scenario-01/raw_result.json').exists())

if __name__=='__main__':unittest.main()
