"""Temporary physical eight-anchor integration; no writer/audit execution or live sources."""
import copy,sys,tempfile,unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
from scripts import ndx_prospective_observation_independent_readback_v2_20261003 as m
import test_ndx_prospective_observation_independent_readback_v2_20261003 as fixture_module

@contextmanager
def physical_fixture(root):
    # Existing synthetic fixture builds payload values only; it does not run a writer/audit.
    a=fixture_module.fixture(True,True);oldrefs=copy.deepcopy(a['refs']);paths={};hashes={};leafs=set()
    def collect(v):
        if isinstance(v,dict):
            if set(('path','sha256'))<=set(v):leafs.add(v['path'])
            for k,x in v.items():
                if k in ('source_hashes','source_hash_claims','source_reference_claims'):leafs.update(x)
                collect(x)
        elif isinstance(v,list):
            for x in v:collect(x)
    collect(a)
    for pair in (m.WRITER,m.CORE,m.CAPTURE_PRODUCER,m.CAPTURE_CORE):leafs.add(pair[0])
    for i,p in enumerate(sorted(leafs)):paths[p]=root/'evidence'/f'leaf-{i}.bin'
    for role,name in (('parent','history'),('capture','capture')):
        for key,filename in (('reference',name+'.json'),('publication_reference','publication.json'),('readback_reference',role+'-audit.json'),('reader_reference',role+'-reader.py')):
            paths[oldrefs[role][key]['path']]=root/(role if key in ('reference','publication_reference')else 'audits')/filename
    cap=a['docs']['capture']['document']
    for t,r in cap['captured_artifacts'].items():paths[r['path']]=root/'capture'/('New_York.tzif'if t=='tzif'else t+'.csv')
    live={str(ROOT/'data/cache'/f'{t}.csv'):root/'data/cache'/f'{t}.csv'for t in ('QQQ','SPY')}
    paths.update(live)
    documents={oldrefs[r][k]['path']for r in oldrefs for k in ('reference','publication_reference','readback_reference')}
    for old,p in paths.items():
        if old in live or old in documents:continue
        p.parent.mkdir(parents=True,exist_ok=True);blob=a['blobs'].get(old,('synthetic immutable '+old).encode());p.write_bytes(blob);hashes[old]=m.sha(blob)
    # Live locators retain snapshot hashes but are not permanent dependencies.
    for t in ('QQQ','SPY'):hashes[str(ROOT/'data/cache'/f'{t}.csv')]=cap['captured_artifacts'][t]['sha256']
    def convert(v):
        if isinstance(v,dict):
            if set(('path','sha256'))<=set(v):return {k:(str(paths[v['path']])if k=='path'else hashes[v['path']]if k=='sha256'else convert(x))for k,x in v.items()}
            out={}
            for k,x in v.items():
                if k in ('source_hashes','source_hash_claims','source_reference_claims'):out[k]={str(paths[p]):hashes[p]for p in x}
                else:out[k]=convert(x)
            return out
        if isinstance(v,list):return [convert(x)for x in v]
        return v
    docs={}
    for role in ('parent','capture'):
        docs[role]={}
        for key,rkey in (('document','reference'),('publication','publication_reference'),('readback','readback_reference')):
            value=convert(a['docs'][role][key])
            if key=='readback':value['reader_sha256']=hashes[oldrefs[role]['reader_reference']['path']]
            blob=m.enc(value);old=oldrefs[role][rkey]['path'];p=paths[old];p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob);hashes[old]=m.sha(blob);docs[role][key]=value
        docs[role].update(convert(oldrefs[role]));(root/role/'started.json').write_bytes(b'{}')
    refs=convert(oldrefs)
    sources={str(paths[p]):hashes[p]for p,h in (m.WRITER,m.CORE)}
    for env in docs.values():
        for role in oldrefs['parent']:m.ref(env[role],sources)
        for obj in ('document','publication','readback'):m.merge_claims(sources,env[obj])
    p=convert(a['payload']);p['observation_id']=m.sha(m.enc(p['observation_identity']));p['source_hashes']=sources
    base=root/'observation';base.mkdir();payload_path=base/'observation_payload.json';payload_path.write_bytes(m.enc(p));pr=dict(path=str(payload_path),sha256=m.sha(payload_path.read_bytes()))
    # Receipt external payload anchor is finalized after the newly mapped payload.
    r=copy.deepcopy(a['receipt']);r.pop('payload_reference');r=convert(r);r.update(payload_reference=pr,observation_id=p['observation_id'],source_hashes=sources)
    receipt_path=base/'receipt.json';receipt_path.write_bytes(m.enc(r));started=convert(a['started']);started['source_hashes']=sources;(base/'started.json').write_bytes(m.enc(started))
    overrides=dict(ROOT=root,BASE=base,PARENT_BOUND=refs['parent'],CAPTURE_BOUND=refs['capture'],PAYLOAD_SHA=pr['sha256'],RECEIPT_SHA=m.sha(receipt_path.read_bytes()))
    for name in ('WRITER','CORE','CAPTURE_PRODUCER','CAPTURE_CORE'):
        old,h=getattr(m,name);overrides[name]=(str(paths[old]),hashes[old])
    with patch.multiple(m,**overrides):yield dict(base=base,refs=refs,docs=docs,source_count=len(sources),live=list(live.values()),drift_path=Path(overrides['CORE'][0]))

class Tests(unittest.TestCase):
    def test_real_load_guard_readback_and_live_refresh_is_not_read(self):
        with tempfile.TemporaryDirectory()as td,physical_fixture(Path(td))as f:
            # None of load_inputs/guard/consume/inspect/readback is mocked.
            for path in f['live']:path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'normal refreshed unrelated live cache')
            original=Path.read_bytes;reads=[]
            def reading(path):
                self.assertNotIn(path,f['live'],'Permanent reader must never consume live cache');reads.append(path);return original(path)
            with patch.object(Path,'read_bytes',reading):
                docs,refs,blobs,sources=m.load_inputs();self.assertEqual(len(sources),f['source_count']);m.guard(sources)
                for path in f['live']:path.write_bytes(b'normal cache refresh after parent verification')
                output=m.readback(execute=True)
            report=m.decode(Path(output['path']).read_bytes());self.assertEqual(report['status'],'PASS');self.assertEqual(report['counts']['parent_observed_count'],62)
            self.assertEqual(report['parent_history_reference'],f['refs']['parent']['reference']);self.assertFalse(report['started_external_sha_authenticated'])
            self.assertTrue(all(Path(r['path'])in reads for table in f['refs'].values()for r in table.values()))
            self.assertEqual({p.name for p in f['base'].iterdir()},{'started.json','observation_payload.json','receipt.json','independent_readback.json'})
    def test_real_final_guard_retains_partial_output_after_source_drift(self):
        with tempfile.TemporaryDirectory()as td,physical_fixture(Path(td))as f:
            save=m.save
            def after_save(path,obj):
                ref=save(path,obj)
                if path.name=='independent_readback.json':f['drift_path'].write_bytes(b'changed after report persisted')
                return ref
            with patch.object(m,'save',side_effect=after_save):
                with self.assertRaisesRegex(ValueError,'Pinned bytes'):m.readback(execute=True)
            self.assertTrue((f['base']/'failure.json').exists());self.assertTrue((f['base']/'independent_readback.json').exists());self.assertTrue((f['base']/'observation_payload.json').exists())
            with self.assertRaises(ValueError):m.readback(execute=True)
if __name__=='__main__':unittest.main()
