"""Read-only news desk. HTTP requests never collect news or invoke a model."""
import json
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse
from data.news_refresh_service import NewsRefreshService
from data.news_observation_history import read_history


def create_router(root, validate=lambda: None):
    root = Path(root)
    router = APIRouter()
    headers = {'Cache-Control': 'no-store'}
    refresh = NewsRefreshService(root / 'data/cache/news')

    @router.get('/api/news/job')
    def job():
        return JSONResponse(refresh.status(), headers=headers)

    @router.post('/api/news/refresh')
    async def start_refresh(request: Request):
        validate()
        origin = request.headers.get('origin')
        if origin is not None and origin != str(request.base_url).rstrip('/'):
            return JSONResponse({'message': '仅允许从本机新闻页面启动。'}, status_code=403, headers=headers)
        if request.headers.get('content-type', '').split(';')[0] != 'application/json':
            return JSONResponse({'message': '请求格式不支持。'}, status_code=415, headers=headers)
        raw = bytearray()
        async for chunk in request.stream():
            raw.extend(chunk)
            if len(raw) > 128:
                return JSONResponse({'message': '请求过大。'}, status_code=400, headers=headers)
        try:
            if json.loads(raw) != {} or request.query_params:
                raise ValueError('EMPTY_REQUEST_REQUIRED')
        except ValueError:
            return JSONResponse({'message': '不接受自定义模型、提示或采集地址。'}, status_code=400, headers=headers)
        code, payload = refresh.start()
        return JSONResponse(payload, status_code=code, headers=headers)

    @router.get('/news')
    def page():
        validate()
        return FileResponse(root / 'web/news.html', headers=headers)

    @router.get('/news.js')
    def script():
        validate()
        return FileResponse(root / 'web/news.js', media_type='application/javascript', headers=headers)

    @router.get('/api/news/latest')
    def latest():
        validate()
        path = root / 'data/cache/news/latest.json'
        if not path.exists():
            return JSONResponse(dict(schema_version='news-desk-v1', status='empty', events=[],
                message='尚未采集新闻，当前交易策略不受影响。'), headers=headers)
        try:
            with path.open('rb') as stream:
                raw = stream.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                raise ValueError('NEWS_RESULT_TOO_LARGE')
            value = json.loads(raw)
            if (not isinstance(value, dict) or value.get('schema_version') != 'news-desk-v1'
                    or not isinstance(value.get('events'), list)):
                raise ValueError('NEWS_RESULT_INVALID')
            return JSONResponse(value, headers=headers)
        except (OSError, ValueError):
            return JSONResponse(dict(status='unavailable', events=[],
                message='新闻结果暂时无法读取，当前交易策略不受影响。'), status_code=503, headers=headers)

    @router.get('/api/news/history')
    def history():
        validate()
        try:
            return JSONResponse(read_history(root / 'data/cache/news'), headers=headers)
        except Exception:
            return JSONResponse(dict(status='unavailable', message='历史读取失败，不能视作没有历史。'), status_code=503, headers=headers)

    return router
