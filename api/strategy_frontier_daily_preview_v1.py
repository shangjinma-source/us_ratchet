"""Proposal-bound daily route, mounted only by a frontier-aware server builder."""
import json
import re
from xml.etree.ElementTree import ParseError

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool


def create_router(*, service):
    router = APIRouter()

    @router.post('/api/strategy-daily-v3/preview')
    async def preview(request: Request):
        try:
            if request.query_params:
                raise ValueError('UNSUPPORTED_PARAMETERS')
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 4096:
                    raise ValueError('BODY_TOO_LARGE')

            def unique_fields(items):
                value = {}
                for key, item in items:
                    if key in value:
                        raise ValueError('DUPLICATE_JSON_FIELD')
                    value[key] = item
                return value

            body = json.loads(raw, object_pairs_hook=unique_fields)
            if type(body) is not dict or set(body) != {
                    'expected_revision', 'target_id', 'expected_proposal_id'}:
                raise ValueError('FRONTIER_BODY_FIELDS')
            if not all(type(value) is str and re.fullmatch('[a-f0-9]{64}', value)
                       for value in body.values()):
                raise ValueError('FRONTIER_BINDING_REQUIRED')
            result = await run_in_threadpool(service.preview, **body)
            # Never publish a response produced for another proposal, even when
            # the original monthly target and account revision are unchanged.
            if (type(result) is not dict
                    or result.get('account_revision') != body['expected_revision']
                    or result.get('target_id') != body['target_id']
                    or result.get('proposal_id') != body['expected_proposal_id']):
                raise ValueError('FRONTIER_RESPONSE_BINDING_MISMATCH')
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except ParseError:
            reason = 'OFFICIAL_ACTION_SOURCE_UNAVAILABLE'
        except (ValueError, KeyError, TypeError, OSError) as error:
            message = str(error)
            known_failures = {
                'SUPPLEMENT_REVIEW_FAILED:WAIT_KNOWN_ACTION_REVIEW': 'WAIT_KNOWN_ACTION_REVIEW',
            }
            reason = known_failures.get(message) or (
                message if re.fullmatch('[A-Z][A-Z0-9_]{0,99}', message)
                else 'DAILY_PREVIEW_UNAVAILABLE')
        return JSONResponse(status_code=409, headers={'Cache-Control': 'no-store'}, content=dict(
            status='WAIT', detail_status='UNAVAILABLE', reason=reason,
            new_orders=[], reference_quotes={}, orders_created=False))

    return router
