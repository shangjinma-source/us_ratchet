"""Real worker entrypoint/IO; inert synthetic domain and evaluator only."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts import ndx_double_replacement_compressed_worker_20261008 as worker


class Tests(unittest.TestCase):
    def fixture(self, root, mode):
        bound = {}
        def put(path, value, raw=False):
            path = root/path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(value if raw else worker.encode(value))
            return worker.ref(path, worker.filehash(path))
        def bind(role, path, value):
            reference = put(path, value, True)
            bound[role] = (str(Path(path)), reference['sha256'])
            return reference
        for role in ('codec', 'decoder', 'raw_io'):
            original = worker.ROOT/worker.BOUND[role][0]
            bind(role, 'code/'+original.name, original.read_bytes())
        lifecycle = put('backtest/ndx_double_replacement_batch_lifecycle_research.py', (worker.ROOT/'backtest/ndx_double_replacement_batch_lifecycle_research.py').read_bytes(), True)
        for role in ('math', 'naive', 'preparation_reader'):
            bind(role, 'code/'+role+'.py', b'# inert synthetic fixture\n')
        bind('domain', 'code/domain.py', b"def task_page(prepared, *, start, limit):\n stop=min(start+limit,prepared['document']['integer_count'])\n return dict(stop=stop,domain_truncated=False,tasks=[dict(synthetic_id=i) for i in range(start,stop)])\n")
        evaluator = """from pathlib import Path
def evaluate_explicit_double_replacement_plans_cached(*, prepared, registered_plans, max_evaluations):
 marker=Path(__file__).with_name('synthetic_calls.jsonl')
 with marker.open('a') as stream:stream.write(str([p['global_ordinal'] for p in registered_plans])+'\\n')
 DRIFT
 return dict(results=[dict(supplied_index=i,plan=p,status='FEASIBLE') for i,p in enumerate(registered_plans)])
""".replace('DRIFT', "Path(__file__).with_name('math.py').write_bytes(b'# changed synthetic source')" if mode == 'drift' else 'pass')
        bind('evaluator', 'code/evaluator.py', evaluator.encode())
        inspector = """def inspect_explicit_evaluations(*,prepared,registered_plans,max_evaluations,saved_result):
 CHECK
 assert saved_result == dict(results=[dict(supplied_index=i,plan=p,status='FEASIBLE') for i,p in enumerate(registered_plans)])
 return dict(status='PASS_SAVED_RESULT_EVIDENCE',supplied_plan_count=len(registered_plans))
""".replace('CHECK', "raise ValueError('synthetic inspection rejection')" if mode == 'postcheck' else 'pass')
        bind('inspector', 'code/inspector.py', inspector.encode())
        counts = dict(scenario_count=1, pair_count=1, integer_count=513, financial_integer_count_before_issuer=513, structurally_excluded_integer_count=0)
        content = '2'*64
        prepared = dict(content_sha256=content, document=counts)
        started = put('prep/started.json', dict(synthetic=True))
        raw = put('prep/raw_preparation.json', dict(result=prepared))
        prep = put('prep/preparation.json', dict(schema='SOURCE_BOUND_DOUBLE_REPLACEMENT_PREPARATION_V1', input_references={}, raw_preparation_reference=raw, preparation=prepared))
        publication = put('prep/publication.json', dict(schema='DOUBLE_REPLACEMENT_PREPARATION_PUBLICATION_V1', status='PUBLISHED_UNEVALUATED_DOMAIN_ONLY', preparation_reference=prep))
        put('audit/started.json', dict(synthetic=True))
        reader_path, reader_sha = bound['preparation_reader']
        audit = put('audit/independent_readback.json', dict(schema='DOUBLE_REPLACEMENT_PREPARATION_INDEPENDENT_READBACK_V1', status='PASS', preparation_reference=prep, publication_reference=publication, reader_sha256=reader_sha, consumed_authenticated_sources={str(root/reader_path):reader_sha}, producer_started_reference=started))
        for key, reference in (('preparation', prep), ('publication', publication), ('audit', audit)):
            bound[key] = (str(Path(reference['path']).relative_to(root)), reference['sha256'])
        proof = put('resource-proof.json', dict(synthetic=True))
        envelope = dict(max_compressed_bytes=2**20, max_uncompressed_bytes=2**20, memory_bytes=2**20, disk_bytes=2**20)
        refs = {key:worker.ref(root/path, sha) for key,(path,sha) in bound.items()}
        refs['lifecycle'] = lifecycle
        registration = put('registration.json', dict(schema='DOUBLE_REPLACEMENT_COMPRESSED_BATCH_REGISTRATION_V1', input_references=refs, worker_reference=worker.ref(worker.SOURCE, worker.LOADED), domain_counts=counts, flags=worker.FLAGS, output_directory=str(root/'output'), resource_envelope=envelope, resource_proof_reference=proof, request_index=0, prior_request_reference=None, batch_size=512, request_batch_limit=2))
        patches = dict(ROOT=root, OUTPUT=root/'output', BOUND=bound, COUNTS=counts, CONTENT=content, LIFECYCLE_SHA=lifecycle['sha256'], RESOURCE_PROOF_SHA=proof['sha256'], RESOURCE_ENVELOPE=envelope)
        return registration, patches

    def test_entrypoint_success_complete_physical_chain_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); registration, constants=self.fixture(root, 'success')
            with patch.multiple(worker, **constants), patch.object(worker, 'resource_gate'):
                reference=worker.execute(registration_path=registration['path'], registration_sha256=registration['sha256'], execute=True)
                result=json.loads(Path(reference['path']).read_bytes())
                self.assertEqual(result['partition']['counts']['inspected_feasible'], 513)
                self.assertTrue(result['partition']['full_domain_complete'])
                self.assertEqual((result['evaluator_call_count'], result['returned_batch_count']), (2,2))
                inventory=result['output_inventory_before_result']
                self.assertEqual(len(inventory), 13)
                for item in inventory:
                    path=root/'output'/item['path']
                    self.assertEqual(worker.filehash(path), item['sha256'])
                    self.assertEqual(path.stat().st_size, item['byte_count'])
                for path, sha in result['source_hashes'].items():
                    self.assertEqual(worker.filehash(path), sha)
                self.assertFalse(json.loads((root/'output/publication.json').read_bytes())['independent_full_execution_readback_passed'])
                before={str(p):worker.filehash(p) for p in (root/'output').rglob('*') if p.is_file()}
                with self.assertRaisesRegex(ValueError, 'Create-only'):
                    worker.execute(registration_path=registration['path'], registration_sha256=registration['sha256'], execute=True)
                self.assertEqual(before,{str(p):worker.filehash(p) for p in (root/'output').rglob('*') if p.is_file()})
                lines=(root/'code/synthetic_calls.jsonl').read_text().splitlines()
                self.assertEqual(len(lines),2)
                self.assertEqual(json.loads(lines[0]),list(range(512)))
                self.assertEqual(json.loads(lines[1]),[512])

    def test_entrypoint_postcheck_failure_and_source_drift_preserve_raw(self):
        for mode in ('postcheck','drift'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as directory:
                root=Path(directory); registration, constants=self.fixture(root,mode)
                with patch.multiple(worker, **constants), patch.object(worker,'resource_gate'):
                    if mode=='drift':
                        with self.assertRaisesRegex(ValueError,'Source drift'):
                            worker.execute(registration_path=registration['path'],registration_sha256=registration['sha256'],execute=True)
                        result=json.loads((root/'output/requests/request-000000/failure.json').read_bytes())
                    else:
                        reference=worker.execute(registration_path=registration['path'],registration_sha256=registration['sha256'],execute=True)
                        result=json.loads(Path(reference['path']).read_bytes())
                    self.assertEqual(result['partition']['counts']['validation_failure_returned'],512)
                    self.assertEqual(result['partition']['counts']['undispatched'],1)
                    self.assertEqual(result['evaluator_call_count'],1)
                    folder=root/'output/batches/000/000000000'
                    for name in ('started.json','raw_return.json.gz','raw_receipt.json','raw_byte_inspection.json','failure.json'):
                        self.assertTrue((folder/name).is_file(),name)
                    self.assertFalse((folder/'result.json').exists())
                    self.assertFalse((root/'output/publication.json').exists())
                    self.assertEqual(len((root/'code/synthetic_calls.jsonl').read_text().splitlines()),1)


if __name__=='__main__':
    unittest.main()
