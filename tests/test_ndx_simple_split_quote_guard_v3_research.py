from copy import deepcopy
import gzip,hashlib,json
from pathlib import Path
import tempfile,unittest
from unittest.mock import patch
from test_ndx_simple_split_quote_guard_v2_research import fixture as old_fixture
from backtest import ndx_simple_split_quote_guard_v3_research as guard

def fixture(directory):
    params,row=old_fixture(directory);params.pop('capture_name');row.pop('name');row['ticker']='AMZN'
    params.update(raw_path=row['raw_path'],raw_sha256=row['raw_sha256'])
    write_manifest(params,[row])
    return params,row

def write_manifest(params,rows):
    path=params['provider_manifest_path'];path.write_text(json.dumps(dict(probes=rows,source_hashes={})))
    params['provider_manifest_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()

class RawAddressGuardTests(unittest.TestCase):
    def test_no_name_original_row_accepted_no_global_or_manifest_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            params,row=fixture(directory);before=params['provider_manifest_path'].read_bytes();loader=guard.previous.load_capture
            result=guard.reconstruct_raw_addressed_nominal_quote(**params)
            self.assertEqual([x['split_factor'] for x in result['reconstruction']['rows']],[20.,1.])
            self.assertEqual(before,params['provider_manifest_path'].read_bytes());self.assertIs(loader,guard.previous.load_capture)
            self.assertFalse(result['original_capture_names_synthesized']);self.assertNotIn('capture_name',result['original_capture_reference'])

    def test_duplicate_same_path_conflicting_hash_and_wrong_selector_reject_before_engine(self):
        for defect in ('duplicate','conflicting_sha','wrong_sha','absent_path','relative_path'):
            with tempfile.TemporaryDirectory() as directory:
                params,row=fixture(directory)
                if defect in ('duplicate','conflicting_sha'):
                    other=deepcopy(row)
                    if defect=='conflicting_sha':other['raw_sha256']='0'*64
                    write_manifest(params,[row,other])
                elif defect=='wrong_sha':params['raw_sha256']='0'*64
                elif defect=='absent_path':params['raw_path']=str(Path(directory)/'absent.bin')
                else:params['raw_path']='raw.bin'
                with patch.object(guard.nominal,'reconstruct_nominal_quote_ticker') as engine:
                    with self.assertRaises(ValueError):guard.reconstruct_raw_addressed_nominal_quote(**params)
                    engine.assert_not_called()

    def test_same_ticker_distinct_raw_requires_the_exact_pair(self):
        with tempfile.TemporaryDirectory() as directory:
            params,row=fixture(directory);other=deepcopy(row)
            decoded=json.loads(gzip.decompress(Path(row['raw_path']).read_bytes()));decoded['chart']['result'][0]['indicators']['quote'][0]['open'][0]=7.
            content=json.dumps(decoded).encode();raw=gzip.compress(content,mtime=0);path=Path(directory)/'other.bin';path.write_bytes(raw)
            other.update(raw_path=str(path.resolve()),raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw),decoded_sha256=hashlib.sha256(content).hexdigest())
            write_manifest(params,[row,other]);result=guard.reconstruct_raw_addressed_nominal_quote(**params)
            self.assertEqual(result['reconstruction']['rows'][0]['nominal_open'],20.)
            params.update(raw_path=other['raw_path'],raw_sha256=other['raw_sha256']);result=guard.reconstruct_raw_addressed_nominal_quote(**params)
            self.assertEqual(result['reconstruction']['rows'][0]['nominal_open'],140.)
            params['raw_sha256']=row['raw_sha256']
            with self.assertRaises(ValueError):guard.reconstruct_raw_addressed_nominal_quote(**params)

    def test_outside_requested_calendar_null_not_filtered(self):
        with tempfile.TemporaryDirectory() as directory:
            params,row=fixture(directory);params['calendar']=['2022-06-03']
            data=json.loads(gzip.decompress(Path(row['raw_path']).read_bytes()));data['chart']['result'][0]['indicators']['quote'][0]['open'][1]=None
            content=json.dumps(data).encode();raw=gzip.compress(content,mtime=0);Path(row['raw_path']).write_bytes(raw)
            row.update(raw_sha256=hashlib.sha256(raw).hexdigest(),raw_bytes=len(raw),decoded_sha256=hashlib.sha256(content).hexdigest());params['raw_sha256']=row['raw_sha256'];write_manifest(params,[row])
            with self.assertRaisesRegex(ValueError,'Finite positive'):guard.reconstruct_raw_addressed_nominal_quote(**params)

    def test_changed_receipt_known_event_and_identity_gates_still_apply(self):
        with tempfile.TemporaryDirectory() as directory:
            params,row=fixture(directory);params['ticker']='LCID'
            with self.assertRaisesRegex(ValueError,'identity transition'):guard.reconstruct_raw_addressed_nominal_quote(**params)
            params['ticker']='AMZN';row['received_at_utc']=None;write_manifest(params,[row])
            with self.assertRaisesRegex(ValueError,'receipt'):guard.reconstruct_raw_addressed_nominal_quote(**params)

if __name__=='__main__':unittest.main()
