from copy import deepcopy
from hashlib import sha256
import json
import unittest
from pathlib import Path
from unittest.mock import patch
from datetime import datetime, timezone

import test_strategy_daily_continuity_normalizer as fixtures
from data.strategy_daily_source_runner import run_daily_sources, RUNNER_CODE_PATHS
from core.strategy_account_ledger import canonical


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixtures.ContinuityTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f=self.fixture
        pins=[]
        for name in RUNNER_CODE_PATHS:
            raw=(fixtures.ROOT/name).read_bytes()
            file=f.root/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(raw)
            pins.append(dict(path=name,sha256=sha256(raw).hexdigest()))
        capture_raw=canonical(f.capture.configuration)
        (f.root/"capture-config.json").write_bytes(capture_raw)
        self.config=dict(schema="SERVER_DAILY_SOURCE_PIPELINE_V1",first_execution_date="2026-10-20",
            capture_configuration=dict(path="capture-config.json",sha256=sha256(capture_raw).hexdigest()),
            parent_reference=f.parent,source_pins=pins,runs_root="runs",
            account_id=f.accounts.read()["account_id"])
        self.calls=[]

    def run_pipeline(self, **options):
        f=self.fixture
        raw=canonical(self.config)
        def daily(*args):
            self.calls.append("daily");return dict(status=200,body=f.capture.daily)
        def official():
            self.calls.append("official");return dict(status=200,body=f.capture.official)
        arguments=dict(root=f.root,configuration_bytes=raw,configuration_sha256=sha256(raw).hexdigest(),
            execute=True,account_reader=f.accounts.read,target_reader=lambda:f.target,
            fetch_daily=daily,fetch_official=official,clock=lambda:f.now)
        arguments.update(options)
        return run_daily_sources(**arguments)

    def test_capture_normalize_archive_repeat_checks_receipt_without_network(self):
        f=self.fixture
        before=f.accounts.path.read_bytes()
        result=self.run_pipeline()
        self.assertEqual(result["status"],"DAILY_CONDITIONAL_PACKET_SAVED",result)
        self.assertEqual(self.calls,["daily","official"])
        self.assertEqual(f.accounts.path.read_bytes(),before)
        receipt=json.loads((f.root/result["receipt_reference"]["path"]).read_bytes())
        self.assertIsNone(receipt["release_sha256"])
        manifest=json.loads((f.root/result["manifest_reference"]["path"]).read_bytes())
        self.assertEqual(set(manifest),set(receipt["source_sha256"]))
        self.assertEqual(self.run_pipeline()["status"],"EXISTING_DAILY_PACKET_VERIFIED")
        self.assertEqual(len(self.calls),2)
        first=next(iter(manifest.values()))
        (f.root/first["path"]).write_bytes(b"tampered")
        with self.assertRaisesRegex(ValueError,"SOURCE_HASH_CHANGED"):
            self.run_pipeline()

    def test_first_date_and_dry_run_never_capture(self):
        self.config["first_execution_date"]="2026-10-21"
        self.assertEqual(self.run_pipeline()["status"],"WAIT_FIRST_EXECUTION_DATE")
        self.config["first_execution_date"]="2026-10-20"
        self.assertEqual(self.run_pipeline(execute=False)["status"],"DRY_RUN_NO_HTTP_NO_FILES")
        self.assertEqual(self.calls,[])
        self.assertFalse((self.fixture.root/"runs").exists())

    def test_failure_preserved_and_not_retried(self):
        self.fixture.capture.daily=b"broken-json"
        result=self.run_pipeline()
        self.assertEqual(result["status"],"NEEDS_RECOVERY")
        self.assertEqual(result["http_calls"],2)
        before=len(self.calls)
        self.assertEqual(self.run_pipeline()["status"],"NEEDS_RECOVERY")
        self.assertEqual(len(self.calls),before)

    def test_snapshot_change_blocks_packet_publication(self):
        f=self.fixture;reads=[0]
        def reader():
            reads[0]+=1
            value=f.accounts.read()
            if reads[0]>1:
                value=deepcopy(value);value["revision"]="changed"
            return value
        result=self.run_pipeline(account_reader=reader)
        self.assertEqual(result["reason"],"PIPELINE_SNAPSHOT_CHANGED")
        self.assertFalse((f.root/"runs/2026-10-20/receipt.json").exists())

    def test_archive_write_race_blocks_receipt(self):
        f=self.fixture;changed=[False];original=Path.open
        def opened(path,*args,**kwargs):
            if "runs" in path.parts and "files" in path.parts and args and args[0]=="xb":
                changed[0]=True
            return original(path,*args,**kwargs)
        def reader():
            value=deepcopy(f.accounts.read())
            if changed[0]: value["revision"]="changed-during-archive"
            return value
        with patch.object(Path,"open",opened):
            result=self.run_pipeline(account_reader=reader)
        self.assertEqual(result["reason"],"PIPELINE_SNAPSHOT_CHANGED")
        self.assertEqual(result["http_calls"],2)
        self.assertFalse((f.root/"runs/2026-10-20/receipt.json").exists())

    def test_close_during_manifest_write_blocks_success_terminal(self):
        f=self.fixture;closed=[False];original=Path.open
        def opened(path,*args,**kwargs):
            if path.name=="source-paths.json" and args and args[0]=="xb":closed[0]=True
            return original(path,*args,**kwargs)
        def clock():
            return datetime(2026,10,20,20,0,tzinfo=timezone.utc) if closed[0] else f.now
        with patch.object(Path,"open",opened):
            result=self.run_pipeline(clock=clock)
        self.assertEqual(result["reason"],"PIPELINE_PUBLICATION_WINDOW_CHANGED")
        self.assertEqual(result["status"],"NEEDS_RECOVERY")
        self.assertTrue((f.root/"runs/2026-10-20/receipt.json").exists())
        self.assertEqual(json.loads((f.root/"runs/2026-10-20/terminal.json").read_bytes())["status"],"NEEDS_RECOVERY")


if __name__=="__main__":
    unittest.main()
