import json
from threading import Thread, Event
import tempfile
import unittest
from pathlib import Path
from hashlib import sha256
from unittest.mock import patch
from scripts.research import run_roa_monthly_pipeline as module


class PipelineTests(unittest.TestCase):
    def test_scheduler_exit_status(self):
        for status in ("FAILED_NOT_ACTIVATED", "BUSY_OR_NEEDS_LOCK_RECONCILIATION", "UNKNOWN"):
            self.assertEqual(module.exit_code({"status":status}),1)
        for status in ("WAIT_COMPLETED_MONTH_END", "DRY_RUN_NO_PREPARATION", "VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED"):
            self.assertEqual(module.exit_code({"status":status}),0)

    def test_phase_chain_and_failures(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"active").write_text("{}")
            ref={"path":"active","sha256":sha256(b"{}").hexdigest()}
            request=dict(capture={"training_calendar":ref,"output_directory":"capture"},active=ref,
                         package=dict(session_calendar=ref,training_calendar=ref,expected_month="2026-12"),
                         coordination_directory="coordinate",publication_directory="publication")
            with patch.object(module,"run_capture",return_value={"status":"WAIT_COMPLETED_MONTH_END"}),patch.object(module,"coordinate") as co,patch.object(module,"publish") as pub:
                self.assertEqual(module.run(root=root,request=request,execute=True)["formal_gate_calls"],0)
                co.assert_not_called();pub.assert_not_called()
            (root/"capture").mkdir();raw=b'{"decision_date":"2026-11-30"}'
            (root/"capture/manifest.json").write_bytes(raw)
            (root/"capture/runner_receipt.json").write_text(json.dumps({"output_hashes":{"capture/manifest.json":sha256(raw).hexdigest()}}))
            calls=[]
            def fakefetch():calls.append("fetch")
            def capture(**kwargs):
                if kwargs["capture"]:kwargs["fetch"]()
                return {"status":"VERIFIED_COMPLETION_REUSED","http_calls":0}
            def coordinate(**kwargs):
                calls.append("coordinate");self.assertEqual(kwargs["request"]["package"]["manifest"]["sha256"],sha256(raw).hexdigest())
                return {"status":"PREPARED_REGISTRATION_NOT_ACTIVATED","registration":ref}
            def publish(**kwargs):calls.append("gate");return {"status":"VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED"}
            with patch.object(module,"run_capture",side_effect=capture),patch.object(module,"coordinate",side_effect=coordinate),patch.object(module,"publish",side_effect=publish):
                self.assertEqual(module.run(root=root,request=request,fetch=fakefetch)["status"],"DRY_RUN_NO_PREPARATION")
                self.assertEqual(calls,[])
                result=module.run(root=root,request=request,execute=True,fetch=fakefetch)
                self.assertEqual(calls,["fetch","coordinate","gate"])
                self.assertEqual(result["status"],"VALIDATED_MONTH_REGISTRATION_NOT_ACTIVATED")
                self.assertFalse(result["activated"])
            with patch.object(module,"run_capture",return_value={"status":"VERIFIED_COMPLETION_REUSED"}),patch.object(module,"coordinate",side_effect=ValueError("NEW_SPLIT_UNREVIEWED")),patch.object(module,"publish") as pub:
                result=module.run(root=root,request=request,execute=True)
                self.assertEqual(result["stage"],"MONTH_PACKAGE_AND_REGISTRATION")
                self.assertEqual(result["status"],"FAILED_NOT_ACTIVATED");pub.assert_not_called()
            (root/"active").write_text("[]")
            with patch.object(module,"run_capture") as cap:
                result=module.run(root=root,request=request,execute=True)
                self.assertEqual(result["stage"],"REQUEST");cap.assert_not_called()

    def test_exclusive_run_failure_release_and_abandoned_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            request=dict(capture={"output_directory":"prepared"},coordination_directory="coord")
            entered=Event();release=Event();results=[]
            def blocked(**kwargs):
                entered.set();release.wait(3)
                return dict(status="FAILED_NOT_ACTIVATED",stage="CAPTURE_AND_TRAINING",error="fake transport error")
            with patch.object(module,"_run",side_effect=blocked) as inner:
                thread=Thread(target=lambda:results.append(module.run(root=root,request=request,execute=True)))
                thread.start();self.assertTrue(entered.wait(2))
                second=module.run(root=root,request=request,execute=True)
                self.assertEqual(second["status"],"BUSY_OR_NEEDS_LOCK_RECONCILIATION")
                self.assertEqual(inner.call_count,1)
                release.set();thread.join(3);self.assertFalse(thread.is_alive())
            lock=root/"tmp/roa_monthly_pipeline_execution.lock"
            self.assertFalse(lock.exists())
            report=json.loads((root/results[0]["report_path"]).read_bytes())
            self.assertEqual(report["stage"],"CAPTURE_AND_TRAINING")
            lock.write_text('{"token":"previous-run"}')
            with patch.object(module,"_run") as inner:
                result=module.run(root=root,request=request,execute=True)
                self.assertEqual(result["status"],"BUSY_OR_NEEDS_LOCK_RECONCILIATION")
                inner.assert_not_called()
            self.assertEqual(json.loads(lock.read_bytes())["token"],"previous-run")
            lock.unlink()
            with patch.object(module,"_run",side_effect=RuntimeError("unexpected")):
                self.assertEqual(module.run(root=root,request=request,execute=True)["status"],"FAILED_NOT_ACTIVATED")
            self.assertFalse(lock.exists())


if __name__=="__main__":unittest.main()
