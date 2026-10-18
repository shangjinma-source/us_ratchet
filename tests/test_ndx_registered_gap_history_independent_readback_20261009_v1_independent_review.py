"""Independent attacks against immutable registered gap readback (temporary IO only)."""
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from scripts import ndx_registered_gap_history_independent_readback_20261009_v1 as reader
from test_ndx_registered_gap_history_independent_readback_20261009_v1 import published_context,read_context

class IndependentGapReadbackReview(unittest.TestCase):
    def test_resigned_authority_history_and_source_closure_rejected_before_output(self):
        with TemporaryDirectory(prefix='SYNTHETIC_AUDITOR_GAP_READER_META_')as folder:
            context,result=published_context(Path(folder));research=context[0]
            history_path=Path(result['history_reference']['path']);pub_path=Path(result['publication_reference']['path'])
            history_raw=history_path.read_bytes();pub_raw=pub_path.read_bytes()
            for index,attack in enumerate(('authority','history_count','missing_source','invented_source')):
                with self.subTest(attack=attack):
                    document=reader.decode(history_raw);publication=reader.decode(pub_raw)
                    if attack=='authority':document['clock_authenticity_verified']=True
                    elif attack=='history_count':document['history']['gap_count']+=1
                    elif attack=='missing_source':
                        path=next(iter(document['source_hashes']));del document['source_hashes'][path];publication['source_hashes'].pop(path)
                    else:
                        path=str(context[3]['QQQ']);document['source_hashes'][path]='a'*64;publication['source_hashes'][path]='a'*64
                    raw=reader.encode(document);history_path.write_bytes(raw)
                    forged=deepcopy(result);forged['history_reference']['sha256']=reader.digest(raw)
                    publication['history_reference']=deepcopy(forged['history_reference']);raw=reader.encode(publication);pub_path.write_bytes(raw)
                    forged['publication_reference']['sha256']=reader.digest(raw)
                    original=Path.read_bytes
                    def deny_live(path):
                        if path in context[3].values():raise AssertionError('Mutable claim read')
                        return original(path)
                    with patch.object(Path,'read_bytes',deny_live),self.assertRaises(ValueError):read_context(context,forged,'rejected_meta_'+str(index))
                    self.assertFalse((research/('rejected_meta_'+str(index))).exists())
                    history_path.write_bytes(history_raw);pub_path.write_bytes(pub_raw)

    def test_ancestor_start_drift_and_own_namespace_extra_detected_at_final_guard(self):
        with TemporaryDirectory(prefix='SYNTHETIC_AUDITOR_GAP_READER_FINAL_')as folder:
            context,result=published_context(Path(folder));research=context[0]
            parent_history=reader.decode(Path(context[1]['reference']['path']).read_bytes())['history']
            targets=[Path(result['history_reference']['path']).parent/'started.json',
                Path(context[2]['readback_reference']['path']).parent/'started.json',
                Path(context[1]['reference']['path']).parent/'started.json',
                Path(parent_history['parent_references']['reference']['path']).parent/'started.json',None]
            for index,target in enumerate(targets):
                with self.subTest(target=str(target)):
                    saved=target.read_bytes()if target else None;original=reader.save;name='failed_final_'+str(index);output=research/name
                    def drift(path,value):
                        item=original(path,value)
                        if path.name=='independent_readback.json':
                            if target:target.write_bytes(saved+b'\n')
                            else:(path.parent/'side_directory').mkdir()
                        return item
                    with patch.object(reader,'save',side_effect=drift),self.assertRaises(ValueError):read_context(context,result,name)
                    self.assertTrue((output/'independent_readback.json').is_file());self.assertTrue((output/'failure.json').is_file())
                    failure=reader.decode((output/'failure.json').read_bytes());self.assertTrue(all(failure[key]is False for key in reader.FLAGS))
                    if target:target.write_bytes(saved)
                    with self.assertRaisesRegex(ValueError,'create-only'):read_context(context,result,name)

    def test_mutable_cache_claim_denied_before_read(self):
        with TemporaryDirectory(prefix='SYNTHETIC_AUDITOR_GAP_READER_LIVE_')as folder:
            path=Path(folder)/'live.csv';path.write_bytes(b'never_read')
            with patch.object(reader,'CURRENT',{'QQQ':path,'SPY':path}),patch.object(Path,'read_bytes',side_effect=AssertionError('Mutable read')):
                with self.assertRaisesRegex(ValueError,'Mutable cache'):reader.consume(reader.reference(str(path),reader.digest(b'never_read')),{})

if __name__=='__main__':unittest.main()
