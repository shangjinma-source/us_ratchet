import copy
import json
from datetime import datetime, timezone
from datetime import date, timedelta
from hashlib import sha256
import tempfile
import unittest
from pathlib import Path
from scripts.research.prepare_roa_fixed_domain_training import validate_bindings, read_reference, write_outputs


class AdapterTests(unittest.TestCase):
    def fixture(self):
        row = dict(ticker="X", security_id="sid:X", issuer_id="issuer:1")
        prior = dict(decision_date="2026-09-30", candidates=[row])
        domain = dict(securities=[row.copy()])
        request = {k: dict(path=k, sha256=k+"hash") for k in ("prior_manifest", "fixed_domain", "session_calendar", "capture_plan")}
        plan = dict(previous_manifest_path="prior_manifest", previous_manifest_sha256="prior_manifesthash", domain_path="fixed_domain", domain_source_hashes={"fixed_domain":"fixed_domainhash"}, calendar_path="session_calendar", calendar_source_hashes={"session_calendar":"session_calendarhash"}, session="2026-10-30", securities=[row.copy()])
        index = dict(session="2026-10-30", plan_sha256="capture_planhash", entries=[row.copy()])
        day=date(2025,1,1);dates=[]
        while day<=date(2026,11,2):
            if day.weekday()<5: dates.append(dict(date=day.isoformat()))
            day+=timedelta(days=1)
        return [prior,domain,plan,index,dict(sessions=dates),request]

    def test_good_and_date_domain_sid_rejections(self):
        args=self.fixture()
        self.assertEqual(validate_bindings(*args)[-1],"2026-10-30")
        for position,key,value,reason in ((3,"session","2026-10-29","DATE_OR_PLAN"),(2,"session","2026-10-29","DATE_OR_PLAN")):
            bad=copy.deepcopy(args);bad[position][key]=value
            with self.assertRaisesRegex(ValueError,reason):validate_bindings(*bad)
        bad=copy.deepcopy(args);bad[1]["securities"][0]["issuer_id"]="issuer:2"
        with self.assertRaisesRegex(ValueError,"IDENTITY_MISMATCH"):validate_bindings(*bad)
        bad=copy.deepcopy(args);bad[3]["entries"][0]["security_id"]="sid:wrong"
        with self.assertRaisesRegex(ValueError,"SID_MISMATCH"):validate_bindings(*bad)
        bad=copy.deepcopy(args);bad[2]["session"]=bad[3]["session"]="2026-10-29"
        with self.assertRaisesRegex(ValueError,"MONTH_END"):validate_bindings(*bad)

    def test_source_drift_and_duplicate_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/"source.json";source.write_bytes(b"{}")
            ref=dict(path="source.json",sha256=sha256(b"{}").hexdigest())
            self.assertEqual(read_reference(root,ref,{}),{})
            source.write_bytes(b"[]")
            with self.assertRaisesRegex(ValueError,"SOURCE_CHANGED"):read_reference(root,ref,{})
            report={"status":"PREPARED_CONDITIONAL_NOT_ACTIVATED","binding_inputs":{}}
            output=root/"out";write_outputs(output,{"original":True},report)
            before=(output/"manifest.json").read_bytes()
            with self.assertRaises(FileExistsError):write_outputs(output,{"original":False},report)
            self.assertEqual(before,(output/"manifest.json").read_bytes())
            completion=json.loads((output/"completion.json").read_bytes())
            self.assertEqual(completion["result"]["status"],"READY_CONDITIONAL")
            self.assertLessEqual(datetime.fromisoformat(completion["at"]),datetime.now(timezone.utc))
            for name,digest in completion["output_hashes"].items():
                self.assertEqual(sha256(Path(name).read_bytes()).hexdigest(),digest)
            self.assertEqual(completion["binding"]["inputs"],report["binding_inputs"])


if __name__=="__main__":unittest.main()
