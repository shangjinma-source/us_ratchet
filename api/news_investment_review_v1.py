"""Same-origin bounded asynchronous investment opinions; no financial mutations."""
import json
import re
from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool


def create_router(*, service, root, validate=lambda: None):
    router = APIRouter()
    headers = {'Cache-Control':'no-store'}

    @router.post('/api/news/investment-review')
    async def start(request: Request):
        try:
            validate()
            if request.headers.get('origin') not in (None, str(request.base_url).rstrip('/')):
                return JSONResponse({'status':'FAILED','error':'SAME_ORIGIN_REQUIRED'}, status_code=403)
            if request.query_params or request.headers.get('content-type','').split(';')[0] != 'application/json':
                raise ValueError('JSON_BODY_REQUIRED')
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw)>1024: raise ValueError('BODY_TOO_LARGE')
            def unique(items):
                result={}
                for key,value in items:
                    if key in result: raise ValueError('DUPLICATE_FIELD')
                    result[key]=value
                return result
            body=json.loads(raw,object_pairs_hook=unique)
            if not isinstance(body,dict) or set(body)!={'expected_revision','target_id','expected_proposal_id'}:
                raise ValueError('BINDING_FIELDS_REQUIRED')
            if not all(isinstance(v,str) and re.fullmatch('[0-9a-f]{64}',v) for v in body.values()):
                raise ValueError('INVALID_BINDING')
            code,value=await run_in_threadpool(service.start,body)
            return JSONResponse(value,status_code=code,headers=headers)
        except (ValueError,KeyError,TypeError,OSError):
            return JSONResponse({'status':'FAILED','error':'REVIEW_REQUEST_UNAVAILABLE'},status_code=409,headers=headers)

    @router.get('/api/news/investment-review/job')
    async def status(request: Request):
        validate()
        query=request.query_params
        if len(query.multi_items())!=1 or set(query)!={'job_id'} or not re.fullmatch('[0-9a-f]{32}',query['job_id']):
            return JSONResponse({'status':'FAILED','error':'JOB_ID_REQUIRED'},status_code=400,headers=headers)
        return JSONResponse(await run_in_threadpool(service.status,query['job_id']),headers=headers)

    @router.get('/static/news_investment_review.js')
    def script():
        validate()
        return FileResponse(root/'web/news_investment_review.js',media_type='application/javascript',headers=headers)

    return router
