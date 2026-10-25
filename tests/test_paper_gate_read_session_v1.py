import json
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from data.paper_gate_read_session_v1 import PaperGateReadSessionV1


class GateReadTests(unittest.TestCase):
    def test_dedup_final_recheck_and_cross_call_freshness(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"x";path.write_bytes(b"old");digest=sha256(b"old").hexdigest()
            gate=PaperGateReadSessionV1(folder)
            for _ in range(9):self.assertEqual(gate.bind("x",digest)[1],b"old")
            result=gate.finish();self.assertEqual(result["unique_files"],1)
            self.assertEqual(result["reused_binds"],8)
            self.assertEqual(gate.cache,{})
            with self.assertRaisesRegex(ValueError,"CLOSED"):gate.bind("x",digest)
            path.write_bytes(b"new")
            with self.assertRaisesRegex(ValueError,"CHANGED"):PaperGateReadSessionV1(folder).bind("x",digest)

    def test_mid_gate_mutation_conflict_budget(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"x";path.write_bytes(b"old");digest=sha256(b"old").hexdigest()
            gate=PaperGateReadSessionV1(folder);gate.bind("x",digest)
            with self.assertRaisesRegex(ValueError,"CONFLICT"):gate.bind("x","0"*64)
            path.write_bytes(b"new")
            with self.assertRaisesRegex(ValueError,"FINAL_CHANGED"):gate.finish()
            self.assertFalse(gate.cache)
            with self.assertRaisesRegex(ValueError,"BYTE_BUDGET"):
                PaperGateReadSessionV1(folder,maximum_total=2).bind("x",sha256(b"new").hexdigest())

    def test_registered_closure_real_fixture_and_account_unchanged(self):
        from test_run_registered_paper_automation import setup
        from scripts.run_registered_quantity_v2_paper_simulation import load_bundle
        with tempfile.TemporaryDirectory() as folder:
            args,now,store=setup(folder);before=store.path.read_bytes()
            descriptor=json.loads(Path(args["descriptor_path"]).read_bytes())
            checked=load_bundle(root=Path(folder),registration_directory=descriptor["registration_directory"],expected_request_sha256=descriptor["request_sha256"],now=now)
            request=checked["request"]
            gate=PaperGateReadSessionV1(folder);seen=set();binds=[0]
            def bind(p,h):binds[0]+=1;return gate.bind(p,h)
            def walk(value):
                if isinstance(value,list):
                    for item in value:walk(item)
                elif isinstance(value,dict):
                    if "path" in value and "sha256" in value:read(value)
                    for key,item in value.items():
                        if key in ("source_hashes","original_source_hashes","fixed_source_hashes"):
                            for p,h in item.items():bind(p,h)
                        else:walk(item)
            def read(ref):
                path,blob=bind(ref["path"],ref["sha256"])
                if path.suffix.lower()==".json" and path not in seen:
                    seen.add(path);walk(json.loads(blob))
            for ref in request["refs"].values():read(ref)
            walk({"source_hashes":request["source_hashes"]})
            self.assertEqual({str(p):h for p,h,raw in gate.cache.values()},checked["verified_source_hashes"])
            stats=gate.finish();self.assertGreater(binds[0],stats["unique_files"])
            print(json.dumps(dict(original_recursive_binds=binds[0],optimized=stats)))
            self.assertEqual(store.path.read_bytes(),before)
