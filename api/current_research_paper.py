"""Isolated manual paper routes; importing does not create storage."""
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse
from data.current_research_paper_service import SERVICE
from data.current_research_successor_service import SERVICE as SUCCESSOR_SERVICE
from data.current_research_paper_charts import SERVICE as CHART_SERVICE
from data.current_research_intraday_execution import SERVICE as INTRADAY_SERVICE

from data.current_research_paper_performance_service import SERVICE as PERFORMANCE_SERVICE

router = APIRouter(prefix='/api/research_paper')


@router.get('/performance')
def paper_performance(request: Request, account_id: str, expected_revision: str, through_date: str = None):
    def read():
        if (set(request.query_params)-{'account_id','expected_revision','through_date'}
                or len(request.query_params.multi_items())!=len(request.query_params)):
            raise ValueError('绩效接口只接受账户、版本与截止日期，不接受行情或来源路径')
        return PERFORMANCE_SERVICE.performance(account_id,expected_revision,through_date)
    return invoke(read)


@router.get('/intraday')
def intraday_reference(research_id: str):
    return invoke(INTRADAY_SERVICE.preview, research_id)


@router.get('/bars')
def paper_bars(account_id: str, expected_plan_id: str, security_id: str, interval: str = 'day'):
    return invoke(CHART_SERVICE.bars, account_id, expected_plan_id, security_id, interval)


def invoke(operation, *arguments):
    try:
        return operation(*arguments)
    except (ValueError, KeyError, TypeError, OSError) as error:
        return JSONResponse(status_code=400, content=dict(status='UNAVAILABLE',
            message='纸面研究请求未完成：' + str(error), research_only=True, execution_blocked=True))


@router.post('/preview')
def preview(body: dict = Body(...)):
    return invoke(SERVICE.preview, body.get('research_id'))


@router.post('/start')
def start(body: dict = Body(...)):
    return invoke(SERVICE.start, body.get('research_id'), body.get('expected_plan_id'))


@router.get('/account')
def account(account_id: str):
    return invoke(SERVICE.account, account_id)


@router.post('/fill')
def fill(body: dict = Body(...)):
    return invoke(SERVICE.fill, body.get('account_id'), body.get('event'))


@router.get('/review')
def review(account_id: str):
    return invoke(SERVICE.review, account_id)


@router.post('/order')
def order(body: dict = Body(...)):
    return invoke(SERVICE.order, body.get('account_id'), body.get('event'))


def invoke_successor(operation, body, keys):
    def validated():
        if set(body) != set(keys) or any(not isinstance(body[key], str) or not body[key].strip() for key in keys):
            raise ValueError('后续计划仅接受明确的编号与账户版本，不接受计划或行情内容')
        return operation(*(body[key] for key in keys))
    return invoke(validated)


@router.post('/successor/preview')
def successor_preview(body: dict = Body(...)):
    return invoke_successor(SUCCESSOR_SERVICE.preview, body, ('account_id', 'input_id', 'expected_revision'))


@router.get('/successor/input')
def successor_input(account_id: str, expected_revision: str):
    return invoke_successor(SUCCESSOR_SERVICE.available_input,
                            dict(account_id=account_id, expected_revision=expected_revision),
                            ('account_id', 'expected_revision'))


@router.post('/successor/activate')
def successor_activate(body: dict = Body(...)):
    return invoke_successor(SUCCESSOR_SERVICE.activate, body, ('account_id', 'preview_id', 'event_id', 'expected_revision'))
