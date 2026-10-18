"""Strict compact routes for the separate intraday manual paper account."""
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import sqlite3
from fastapi import APIRouter,Body,Request
from fastapi.responses import JSONResponse
from data.current_research_intraday_paper_service import IntradayPaperService
from data.current_research_intraday_execution import SERVICE as REFERENCE_SERVICE
from data.current_research_snapshot_resolver import read_known_research_snapshot

ROOT=Path(__file__).resolve().parents[1]
SERVICE=IntradayPaperService(root=ROOT,directory=ROOT/'data/research_paper_intraday',
                           reference_service=REFERENCE_SERVICE,snapshot_reader=read_known_research_snapshot)
router=APIRouter(prefix='/api/research_paper/intraday_paper')
FLAGS=dict(research_only=True,execution_blocked=True,real_account=False)


def _keys(value,keys):
    if not isinstance(value,dict) or set(value)!=set(keys):raise ValueError('EXACT_REQUEST_FIELDS_REQUIRED')


def compact_proposal(proposal):
    if proposal is None:return None
    if proposal.get('schema') == 'INTRADAY_SAME_MONTH_BUY_CONTINUATION_PROPOSAL_V1':
        causal=proposal['causal_inputs']; reference=causal['reference']
        output={key:deepcopy(proposal[key]) for key in ('proposal_id','research_id','security','quantity','limit_price','notional','residual_cash','accept_before','reference_valid_until','time_in_force','action','target_quantity','held_quantity','available_cash')}
        output.update(proposal_kind='CONTINUATION',account_revision=causal['account_revision'],proposal_created_at=causal['proposal_created_at'],selection_asof=reference['research_snapshot']['as_of'],market_session={key:reference['market_session'][key] for key in ('date','timezone','open_at','close_at')})
        return output
    fields=('proposal_id','research_id','account_revision','security','quantity','limit_price','notional','residual_cash',
            'proposal_created_at','accept_before','reference_valid_until','market_session','time_in_force','action')
    output={key:deepcopy(proposal[key]) for key in fields}
    output['market_session']={key:proposal['market_session'][key] for key in ('date','timezone','open_at','close_at')}
    output.update(available_cash=proposal['causal_inputs']['available_cash'],
                  selection_asof=proposal['causal_inputs']['research_snapshot']['as_of'])
    return output


def compact_account(state):
    proposal=state['acceptance']['proposal']
    fields=('revision','acceptance_id','order','cash','shares','reserved_cash','fees','filled_quantity','closed')
    output={key:deepcopy(state[key]) for key in fields}
    output.update(target_quantity=proposal['quantity'],original_acceptance_id=state['acceptance_id'],current_order_acceptance_id=state['order']['order_id'].split(':')[0],
                  initial_cash=proposal['causal_inputs']['available_cash'],
                  recorded_buy_notional=str(sum((event['quantity']*Fraction(event['price']) for event in state['events'] if event['kind']=='FILL'),Fraction(0))),
                  account_id=state['account_id'],proposal_id=proposal['proposal_id'],research_id=proposal['research_id'],
                  security=deepcopy(proposal['security']),selection_asof=proposal['causal_inputs']['research_snapshot']['as_of'],
                  events=[{k:deepcopy(v) for k,v in event.items() if k in
                           {'event_id','kind','order_id','quantity','price','fees','executed_at','cancelled_at','recorded_at','expected_revision'}} for event in state['events'][-20:]],
                  event_count=len(state['events']),has_more_events=len(state['events'])>20,
                  fee_scope=dict(commission='0',other_fees='UNKNOWN_NOT_RESERVED'))
    return output


def _account_response(research_id,state):
    account=compact_account(state)
    if account['research_id']!=research_id:raise ValueError('RESPONSE_RESEARCH_MISMATCH')
    return dict(FLAGS,status='ACCOUNT',research_id=research_id,account_id=state['account_id'],account=account,proposal=None)


def _invoke(operation):
    try:return operation()
    except (ValueError,KeyError,TypeError,OSError,ArithmeticError,sqlite3.Error) as error:
        return JSONResponse(status_code=400,content=dict(FLAGS,status='UNAVAILABLE',message='盘中纸面请求未完成：'+str(error)))


@router.post('/preview')
def preview(body:dict=Body(...)):
    def run():
        _keys(body,{'research_id'});result=SERVICE.preview(body['research_id'])
        if result['status']=='EXISTING_ACCOUNT':
            output=_account_response(body['research_id'],result['state']);output['status']='EXISTING_ACCOUNT';return output
        return dict(FLAGS,status='PROPOSAL',research_id=body['research_id'],account_id=result['account_id'],proposal=compact_proposal(result['proposal']),account=None)
    return _invoke(run)


@router.post('/accept')
def accept(body:dict=Body(...)):
    def run():
        _keys(body,{'research_id','proposal_id','operation_id'})
        return _account_response(body['research_id'],SERVICE.accept(body['research_id'],body['proposal_id'],body['operation_id']))
    return _invoke(run)


@router.get('/account')
def account(request:Request,research_id:str):
    def run():
        if set(request.query_params)!={'research_id'} or len(request.query_params.multi_items())!=1:
            raise ValueError('EXACT_ACCOUNT_QUERY_REQUIRED')
        return _account_response(research_id,SERVICE.account(research_id))
    return _invoke(run)


@router.post('/event')
def event(body:dict=Body(...)):
    def run():
        _keys(body,{'research_id','event'});event=body['event']
        if not isinstance(event,dict):raise ValueError('EVENT_OBJECT_REQUIRED')
        extras={'FILL':{'quantity','price','fees','executed_at'},'CANCEL':{'cancelled_at'},'EXPIRE':set()}
        if event.get('kind') not in extras:raise ValueError('EVENT_KIND_UNSUPPORTED')
        _keys(event,{'event_id','kind','expected_revision','order_id'}|extras[event['kind']])
        return _account_response(body['research_id'],SERVICE.record_event(body['research_id'],event))
    return _invoke(run)


@router.post('/continuation/preview')
def continuation_preview(body:dict=Body(...)):
    def run():
        _keys(body,{'research_id'})
        result=SERVICE.continuation_preview(body['research_id'])
        output=_account_response(body['research_id'],result['state'])
        if result['status']=='PENDING_UNIT_REVIEW':
            output.update(status='PENDING_UNIT_REVIEW',proposal=None,review_reference={key:result['review_reference'][key] for key in ('event_sha256','checked_at','accept_before')})
        else:
            output.update(status='CONTINUATION_PROPOSAL',proposal=compact_proposal(result['proposal']))
        return output
    return _invoke(run)


@router.post('/continuation/accept')
def continuation_accept(body:dict=Body(...)):
    def run():
        _keys(body,{'research_id','proposal_id','operation_id','expected_revision'})
        return _account_response(body['research_id'],SERVICE.accept_continuation(body['research_id'],body['proposal_id'],body['operation_id'],body['expected_revision']))
    return _invoke(run)
