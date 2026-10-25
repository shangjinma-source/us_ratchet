"""Read-only research summary, isolated from account and execution routes."""
from pathlib import Path
import logging
from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from data.strategy_followup_summary_v1 import read_summary


def create_router(root):
    root = Path(root)
    router = APIRouter()

    @router.get('/api/strategy-followup-v1/summary')
    def summary():
        try:
            result = read_summary(root / 'data/strategy_advice_followup/results')
            return JSONResponse(result, headers={'Cache-Control': 'no-store'})
        except Exception:
            logging.getLogger(__name__).exception('Followup summary verification failed')
            return JSONResponse({'status': 'UNAVAILABLE', 'reason': 'FOLLOWUP_VERIFICATION_FAILED'},
                                status_code=503, headers={'Cache-Control': 'no-store'})

    @router.get('/static/strategy_followup_summary.js')
    def script():
        return Response((root / 'web/strategy_followup_summary.js').read_bytes(),
                        media_type='application/javascript', headers={'Cache-Control': 'no-cache'})
    return router
