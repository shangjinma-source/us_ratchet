import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
from scripts.research import run_roa_monthly_capture as module


class RunnerTests(unittest.TestCase):
    def test_wait_and_dryrun_never_fetch(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ("plan", "calendar"):(root/name).write_text("{}")
            request={"plan":{"path":"plan","sha256":module.digest(root/"plan")},"training_calendar":{"path":"calendar","sha256":module.digest(root/"calendar")},"output_directory":"out"}
            def forbidden(*args,**kwargs):raise AssertionError("HTTP_CALLED")
            for ready,capture,status in ((False,False,"WAIT_COMPLETED_MONTH_END"),(False,True,"WAIT_COMPLETED_MONTH_END"),(True,False,"DRY_RUN_READY_NO_HTTP")):
                with patch.object(module,"validate_plan",return_value=({}, {"ready_after_close":ready})):
                    result=module.run(root=root,request=request,capture=capture,fetch=forbidden)
                self.assertEqual(result["status"],status)
                self.assertFalse((root/"out").exists())

    def test_orchestration_fake_transport_reuse_and_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name in ("plan","calendar","prior","domain"):(root/name).write_text("{}")
            request={"plan":{"path":"plan","sha256":module.digest(root/"plan")},"training_calendar":{"path":"calendar","sha256":module.digest(root/"calendar")},"output_directory":"out"}
            plan={"output_directory":"capture","previous_manifest_path":"prior","previous_manifest_sha256":module.digest(root/"prior"),"domain_path":"domain","domain_source_hashes":{"domain":module.digest(root/"domain")},"calendar_path":"calendar","calendar_source_hashes":{"calendar":module.digest(root/"calendar")}}
            calls=[]
            def fetch():calls.append(1);return b"{}"
            def capture(*args,**kwargs):
                self.assertIs(kwargs["plan_validator"],module.validate_plan)
                (root/"capture").mkdir();(root/"capture/completion_index.json").write_bytes(kwargs["fetch"]())
                return {"status":"EXPERIMENTAL_DOMAIN_CAPTURED_NOT_ADMITTED","http_calls":1}
            (root/"official.pdf").write_bytes(b"official calendar bytes")
            report={"status":"PREPARED_CONDITIONAL_NOT_ACTIVATED","binding_inputs":{},"source_hashes":{"official.pdf":module.digest(root/"official.pdf")}}
            with patch.object(module,"validate_plan",return_value=(plan,{"ready_after_close":True})),patch.object(module,"capture_domain",side_effect=capture),patch.object(module,"prepare",return_value=({},report)),patch.object(module,"completed_previous") as replay:
                first=module.run(root=root,request=request,capture=True,fetch=fetch)
                second=module.run(root=root,request=request,capture=True,fetch=fetch)
                self.assertEqual(first["status"],"PREPARED_VERIFIED_NOT_ACTIVATED")
                self.assertEqual(second["status"],"VERIFIED_COMPLETION_REUSED")
                self.assertEqual(len(calls),1);self.assertEqual(replay.call_count,2)
                (root/"official.pdf").write_bytes(b"altered official source")
                with self.assertRaisesRegex(ValueError,"REUSED_ADAPTER_SOURCE_CHANGED"):
                    module.run(root=root,request=request,capture=True,fetch=fetch)
                self.assertEqual(len(calls),1)
                (root/"official.pdf").write_bytes(b"official calendar bytes")
                (root/"out/manifest.json").write_text("[]")
                with self.assertRaisesRegex(ValueError,"SOURCE_CHANGED"):module.run(root=root,request=request,capture=True,fetch=fetch)
            request["output_directory"]="blocked"
            with patch.object(module,"validate_plan",return_value=(plan,{"ready_after_close":True})),patch.object(module,"capture_domain",return_value={"status":"EXPERIMENTAL_DOMAIN_CAPTURED_NOT_ADMITTED","http_calls":1}):
                for reason in ("UNREVIEWED_COORDINATE_EVENT:X","FIXED_DOMAIN_IDENTITY_MISMATCH"):
                    with patch.object(module,"prepare",side_effect=ValueError(reason)):
                        with self.assertRaisesRegex(ValueError,reason):module.run(root=root,request=request,capture=True,fetch=fetch)
                    self.assertFalse((root/"blocked/completion.json").exists())
            (root/"failed").mkdir();request["output_directory"]="failed"
            with patch.object(module,"validate_plan",return_value=(plan,{"ready_after_close":True})):
                with self.assertRaisesRegex(ValueError,"INCOMPLETE_OUTPUT"):module.run(root=root,request=request,capture=True,fetch=fetch)


if __name__=="__main__":unittest.main()
