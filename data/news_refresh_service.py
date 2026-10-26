"""Explicit, single-flight news refresh with a durable daily attempt budget."""
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import Lock, Thread
from uuid import uuid4
from zoneinfo import ZoneInfo


class NewsRefreshService:
    def __init__(self, cache, *, runner=None, clock=None):
        self.cache = Path(cache)
        self.runner = runner or self._run
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.lock = Lock()
        self.job = dict(status='IDLE', message='尚未启动新闻更新。')

    def status(self):
        with self.lock:
            return dict(self.job)

    def start(self):
        with self.lock:
            if self.job['status'] == 'RUNNING':
                return 409, dict(self.job)
            now = self.clock()
            history = self.cache / 'requests'
            history.mkdir(parents=True, exist_ok=True)
            receipts = []
            for path in history.glob('*.json'):
                try:
                    receipts.append(json.loads(path.read_bytes()))
                except (OSError, ValueError):
                    return 503, dict(status='FAILED', message='更新记录无法核验，请稍后再试。')
            try:
                starts = [datetime.fromisoformat(row['started_at']) for row in receipts]
                if any(stamp.tzinfo is None for stamp in starts):
                    raise ValueError('AWARE_TIME_REQUIRED')
            except (KeyError, TypeError, ValueError):
                return 503, dict(status='FAILED', message='更新记录无法核验，请稍后再试。')
            today = now.astimezone(ZoneInfo('Asia/Shanghai')).date()
            if sum(stamp.astimezone(ZoneInfo('Asia/Shanghai')).date() == today for stamp in starts) >= 4:
                return 429, dict(status='FAILED', message='今日4次分析预算已用完，仍可读取已保存结果。')
            if any((now - stamp).total_seconds() < 600 for stamp in starts):
                return 429, dict(status='FAILED', message='两次采集分析至少间隔10分钟，请读取已有结果。')
            job = dict(status='RUNNING', message='正在采集官方来源并分析最多4条事件。',
                       started_at=now.isoformat(), finished_at=None, id=uuid4().hex)
            path = history / (job['id'] + '.json')
            path.write_text(json.dumps(job, ensure_ascii=False), encoding='utf-8')
            self.job = job
            self.worker = Thread(target=self._complete, args=(path,), daemon=True,
                                 name='bounded-news-refresh')
            self.worker.start()
            return 202, dict(job)

    def _run(self):
        from data.news_desk import collect, analyze, save_snapshot
        snapshot = collect(self.cache, limit=20)
        snapshot = analyze(snapshot, self.cache, limit=4, timeout=180)
        save_snapshot(snapshot, self.cache)
        return snapshot.get('analysis_summary', {}).get('status') in ('ANALYZED', 'CACHED')

    def _complete(self, path):
        try:
            success = self.runner()
            message = '新闻已更新，可查看分析与原文依据。' if success else '已结束本次更新；分析未完成，请查看来源和失败状态。'
        except Exception:
            success, message = False, '本次新闻更新失败，已保留此前结果。'
        with self.lock:
            self.job = dict(self.job, status='SUCCEEDED' if success else 'FAILED',
                            message=message, finished_at=self.clock().isoformat())
            pending = path.with_suffix('.pending')
            pending.write_text(json.dumps(self.job, ensure_ascii=False), encoding='utf-8')
            pending.replace(path)
