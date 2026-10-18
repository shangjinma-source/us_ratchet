"""Synthetic raw/registry/HTTP fixture for browser-free JavaScript tests."""
from tempfile import TemporaryDirectory
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from hashlib import sha256
from datetime import timedelta
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_current_quantity_v2_monthly_research_service import fixture
from test_current_quantity_v2_bounded_unit_review import feed
from data.current_quantity_projection_v2 import project_capital_decision_v2
from data.current_quantity_v2_current_cash_plan import canonical
from data.current_quantity_v2_monthly_factory import attach_monthly_services
from data.current_quantity_v2_monthly_bounded_review import MonthlyBoundedUnitReview
from data.current_quantity_v2_monthly_continuation_sources import QuantityV2MonthlyContinuationSources
from data.current_quantity_v2_monthly_continuation_factory import attach_monthly_continuation
from api.current_quantity_v2_monthly_research import create_router as research_router
from api.current_quantity_v2_paper import create_router,PREFIX


def main():
 with TemporaryDirectory() as folder:
  registry,state,_,old,paper,clock=fixture(folder);aid=state['ledger']['account_id'];original=paper.account(aid)
  research=project_capital_decision_v2(state['ledger']['acceptance']['proposal']['causal_inputs']['capital_decision'])
  research.update(decision_id=original['capital_decision_id'],research_version='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH')
  def account_review(snapshot):
   ledger=snapshot['state']['ledger'];path='account/'+ledger['revision']+'.json'
   raw=canonical(dict(account_id=aid,state_revision=ledger['revision'],pending_rights=[],reviewed_at=clock[0].isoformat(),source_references=[path]))
   return dict(files={path:raw},source_hashes={path:sha256(raw).hexdigest()},account_review_path=path)
  def fetch(ticker):
   value=json.loads(old.fetch(ticker));value['chart']['result'][0]['meta']['regularMarketTime']=int(clock[0].timestamp());return canonical(value)
  def reader():return MonthlyBoundedUnitReview(account_review_reader=account_review,fetch=lambda:dict(status=200,body=feed()),clock=lambda:clock[0])
  paper.clock=lambda:clock[0]
  attach_monthly_services(paper,storage_root=Path(folder)/'monthly',decision_reader=registry.decision_reader,review_reader=reader(),fetch=fetch)
  source=QuantityV2MonthlyContinuationSources(storage_root=Path(folder)/'daily',monthly_blob_root=Path(folder)/'monthly'/'blobs',review_reader=reader(),fetch=fetch,clock=paper.clock)
  paper=attach_monthly_continuation(paper,monthly_sources=source)['paper']
  app=FastAPI();app.include_router(create_router(service=paper));app.include_router(research_router(service=registry))
  with TestClient(app) as client:
   def post(path,body):
    response=client.post(PREFIX+path,json=body);assert response.status_code==200,response.text;return response.json()
   current=client.get(PREFIX+'/monthly/research',params=dict(account_id=aid)).json()
   selected=post('/monthly/research/generate',dict(account_id=aid,expected_revision=original['revision'],retry_failed=False))
   proposal=post('/monthly/preview',dict(account_id=aid,decision_id=selected['decision_id'],expected_revision=original['revision']))
   accepted=post('/monthly/accept',dict(account_id=aid,proposal_id=proposal['proposal_id'],operation_id='month',expected_revision=original['revision']))
   closed=accepted
   for order in accepted['orders']:
    closed=post('/event',dict(account_id=aid,event=dict(type='CANCEL',event_id='close-'+order['order_id'],order_id=order['order_id'],expected_revision=closed['revision'],cancelled_at=clock[0].isoformat())))
   clock[0]+=timedelta(seconds=1)
   daily=post('/continuation/preview',dict(account_id=aid,expected_revision=closed['revision']))
   daily_accepted=post('/continuation/accept',dict(account_id=aid,proposal_id=daily['proposal_id'],operation_id='daily',expected_revision=closed['revision']))
   output=dict(research=research,original=original,current=current,selected=selected,proposal=proposal,accepted=accepted,closed=closed,daily=daily,daily_accepted=daily_accepted,now=clock[0].isoformat())
   output['allcash']=allcash_fixture()
   print(json.dumps(output))

def allcash_fixture():
 import test_current_quantity_v2_current_cash_plan as base
 from test_current_quantity_v2_current_cash_ledger import frozen_fixture
 from test_current_quantity_v2_difference_plan import fixture as old_args
 from test_current_quantity_v2_monthly_retarget import fixture as month_args
 from data.current_quantity_v2_paper_ledger import accept_proposal
 from data.current_quantity_v2_paper_chain import create_chain,record_chain_event,accept_monthly_retarget
 from data.current_quantity_v2_paper_service import compact
 from data.current_quantity_v2_monthly_retarget import build_monthly_retarget
 from data.current_research_capital_decision_v2 import decide_quantity_v2_for_account
 from data.current_quantity_v2_monthly_research_service import QuantityV2MonthlyResearchService
 from copy import deepcopy
 base.CurrentCashTests.setUpClass()
 try:
  initial,args=frozen_fixture(base.CurrentCashTests.args)
  state=create_chain(accept_proposal(initial,account_state=args['account_state'],now=args['now']))
  for oid in list(state['ledger']['orders']):
   state=record_chain_event(state,dict(type='CANCEL',event_id='close-'+oid,order_id=oid,expected_revision=state['ledger']['revision'],recorded_at=args['now'],cancelled_at=args['now']),now=args['now'])
  old=old_args();old['source_hashes'].update(initial['causal_inputs']['frozen_execution_package']['source_hashes'])
  state,inputs,now=month_args((state,old));b=inputs['capital_decision']['binding'];search=deepcopy(b['search_arguments']);search['quote_as_of']=b['decision_date'];search['price_basis']='SYNTHETIC_USD';search['minimum_cash_buffer']='1000000'
  decision=decide_quantity_v2_for_account(decision_date=b['decision_date'],account_state=dict(asof=b['decision_date'],revision=state['ledger']['revision'],cash=state['ledger']['cash'],shares=state['ledger']['shares'],reserved_cash='0'),valuation_quotes=[dict(security_id=sid,**q) for sid,q in b['valuation_quotes'].items()],source_hashes=b['source_hashes'],search_arguments=search)
  assert decision['target_quantities']=={}
  inputs['capital_decision']=decision;inputs['target_mandate']['capital_decision_id']=decision['decision_id']
  for key in ('securities','execution_references','unit_continuity','held_unit_continuity'):inputs[key]={}
  proposal=build_monthly_retarget(state,proposal_inputs=inputs,now=now)
  accepted=accept_monthly_retarget(state,proposal,acceptance_id='allcashmonth',now=now)
  public={k:v for k,v in proposal.items() if k not in ('causal_inputs','binding')}
  public.update(scope='MONTHLY_RETARGET',prior_revision=state['ledger']['revision'],shares=state['ledger']['shares'],securities={},created_at=now,execution_references={},source_bytes_verified=True,orders_created=False,account_mutated=False)
  selected=QuantityV2MonthlyResearchService._public(dict(status='READY',account_id=state['ledger']['account_id'],state_revision=state['ledger']['revision'],target_month='2026-11',registration_id='d'*64,capital_decision=decision),True)
  research=project_capital_decision_v2(initial['causal_inputs']['capital_decision']);research.update(decision_id=initial['capital_decision_id'],research_version='CURRENT_QUANTITY_V2_FAIR_K_CASH_ONLY_RESEARCH')
  return dict(research=research,original=compact(state),selected=selected,proposal=public,accepted=compact(accepted),now=now)
 finally:base.CurrentCashTests.tearDownClass()

if __name__=='__main__':main()
