import sys,importlib.util,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import datetime,timezone
sys.path.insert(0,str(Path.cwd()))
import api.strategy_account as m
class ProfitTests(unittest.TestCase):
 def test_partial_reentry_correction_readonly(self):
  with TemporaryDirectory() as d:
   svc=m.StrategyAccountService(database_path=Path(d)/"a.db",account_id="a",resolver=lambda t:dict(ticker=t,security_id="A",source_references=["id"],source_hashes={"id":"a"*64}),clock=lambda:datetime(2026,11,13,15,tzinfo=timezone.utc))
   a=svc.initialize({"event_id":"init"})["account"]
   def event(e):
    nonlocal a
    a=svc.append(dict(expected_revision=a["revision"],event=e))["account"]
   event(dict(event_id="cash",kind="CASH_CONFIRM",amount="10000",cash_basis="TOTAL_UNINVESTED"))
   for eid,side,q,p in [("b1","BUY",10,"100"),("s1","SELL",4,"120"),("b2","BUY",4,"80"),("s2","SELL",10,"100"),("b3","BUY",2,"50")]:
    event(dict(event_id=eid,kind="DIRECT_FILL",ticker="AAA",side=side,quantity=q,price=p,fees="1",executed_at="2026-11-13T14:00:00Z"))
   row=a["trade_results"][0]
   self.assertEqual(row["realized_gross"],"160");self.assertEqual(row["gross_cost"],"100");self.assertEqual(row["quantity"],2);self.assertEqual(row["recorded_fees"],"5")
   event(dict(event_id="fix",kind="FILL_PRICE_CORRECTION",fill_id="b1",price="101",previous_price="100",reason="broker confirmation"))
   self.assertEqual(a["trade_results"][0]["realized_gross"],"150")
   before=svc.store.path.read_bytes();self.assertEqual(svc.read()["account"],a);self.assertEqual(svc.store.path.read_bytes(),before)
 def test_closed_chart_requires_recorded_identity(self):
  import json
  from unittest.mock import patch
  from types import SimpleNamespace
  import data.roa_display as display
  fills=[dict(security_id="A",ticker="AAA",executed_at="2026-11-06T15:00:00+00:00")]
  account=SimpleNamespace(store=SimpleNamespace(read=lambda:dict(revision="r",shares={"A":0})),project=lambda state:{"account":{"fills":fills}},resolver=lambda t:dict(security_id="A",ticker=t))
  manifest=dict(candidates=[dict(security_id="A",ticker="AAA",status="READY_CONDITIONAL",training_source="bars")],source_hashes={"bars":"hash"},decision_date="2026-11-06")
  with patch.object(display.StrategyMonthlyTargetCharts,"_read",side_effect=lambda p,h:json.dumps(manifest).encode() if p=="manifest" else b"baseline"),patch.object(display,"LatestDisplayChartsV1",side_effect=lambda **kw:kw):
   result=display.build_display(root=Path.cwd(),account=account,signal=SimpleNamespace(frozen_roster=lambda:[]),specification={"path":"manifest","sha256":"hash"},validate_sources=lambda:None,clock=lambda:None)
   context=result["context_reader"]
   self.assertEqual(context("A")["ticker"],"AAA")
   with self.assertRaisesRegex(ValueError,"DISPLAY_NO_RECORDED_TRADES"):context("B")
   account.resolver=lambda t:dict(security_id="WRONG",ticker=t)
   with self.assertRaisesRegex(ValueError,"DISPLAY_IDENTITY_MISMATCH"):context("A")
if __name__=="__main__":unittest.main()
