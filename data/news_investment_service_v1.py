"""Asynchronous, account-bound AI opinions; never writes financial state or orders."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import Thread, Lock
from time import monotonic
from uuid import uuid4

from core.news_investment_review_v1 import build_review_proposal, moment
from data.news_risk_plan_v1 import build_risk_plan
from data.news_refresh_service import owner_alive, process_identity

_workers = set()
_workers_lock = Lock()


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class NewsInvestmentService:
    def __init__(self, *, cache, context, preview, validate=lambda: None,
                 collector=None, model=None, source_builder=None, clock=None, risk_plan_provider=None):
        self.cache = Path(cache)
        self.risk_plan_provider = risk_plan_provider
        self.context, self.preview, self.validate = context, preview, validate
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.collector, self.model, self.source_builder = collector, model, source_builder

    def connection(self):
        self.cache.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.cache/'investment_jobs_v1.sqlite3', timeout=5)
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, document TEXT NOT NULL)')
        return connection

    @staticmethod
    def save(connection, job):
        connection.execute('INSERT OR REPLACE INTO jobs VALUES (?,?)',
                           (job['job_id'], json.dumps(job, ensure_ascii=False)))

    def bound_context(self, binding):
        self.validate()
        account, target, names = self.context()
        if (account['revision'] != binding['expected_revision'] or
                target['target_id'] != binding['target_id'] or
                target['proposal_id'] != binding['expected_proposal_id']):
            raise ValueError('STALE_ACCOUNT_OR_TARGET')
        return deepcopy(account), deepcopy(target), dict(names)

    def news_generation(self):
        path = self.cache/'observations_v1.sqlite3'
        if not path.exists():
            return 0
        with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro', uri=True)) as connection:
            return connection.execute('SELECT COALESCE(MAX(sequence),0) FROM batches').fetchone()[0]

    def validate_event_control(self, pending):
        guard = getattr(self, 'event_guard', None)
        if guard is None or not guard(pending):
            raise ValueError('EVENT_PIPELINE_DISABLED_OR_RESTARTED')
        if not moment(pending['execution_window']['not_before']) <= self.clock() < moment(pending['opinion_valid_until']):
            raise ValueError('EVENT_OUTSIDE_FIRST_EXECUTION_WINDOW')

    def start_event(self, binding, pending):
        self.validate_event_control(pending)
        from data.news_event_model_v1 import project_event
        from data.news_investment_model_v1 import _validate
        if pending['binding'] != binding or self.clock() >= moment(pending['opinion_valid_until']):
            raise ValueError('EVENT_OPINION_STALE')
        answer = pending['answer']
        if answer.get('schema') != 'SOURCE_ONLY_EVENT_OPINION_V1' or answer.get('status') not in ('SUCCEEDED', 'CACHED'):
            raise ValueError('SOURCE_ONLY_OPINION_REQUIRED')
        from data.news_investment_sources_v1 import build_sources
        rebuilt = build_sources(pending['snapshot'], self.cache, pending['positions'], max_chars=110000)
        if rebuilt['fingerprint'] != pending['source_fingerprint']:
            raise ValueError('EVENT_SOURCE_CHANGED')
        payload, _ = project_event(list(rebuilt['sources'].values()), pending['positions'])
        rows = deepcopy(answer['rows'])
        for row in rows:
            for evidence in row['evidence']:
                evidence.pop('source_sha256', None)
        _validate(dict(rows=rows), payload)
        return self.start(binding, event_pending=deepcopy(pending))

    def start(self, binding, *, event_pending=None):
        self.bound_context(binding)
        now = self.clock()
        with closing(self.connection()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            rows = [json.loads(row[0]) for row in connection.execute('SELECT document FROM jobs')]
            for row in rows:
                if row['status'] == 'RUNNING':
                    alive = owner_alive(row['worker_pid'], row['worker_created_at'])
                    if row['worker_pid'] == process_identity()[0]:
                        with _workers_lock:
                            alive = alive and row['job_id'] in _workers
                    if alive:
                        return 409, dict(status='RUNNING', job_id=row['job_id'], error='ANALYSIS_ALREADY_RUNNING')
                    row.update(status='FAILED', error='WORKER_STOPPED', finished_at=now.isoformat())
                    self.save(connection, row)
            recent = [row for row in rows if (now-moment(row['started_at'])).total_seconds() < 86400]
            if any(moment(row['started_at']) > now for row in rows):
                raise ValueError('CLOCK_REVERSED')
            if any((now-moment(row['started_at'])).total_seconds() < 60 for row in recent):
                return 429, dict(status='FAILED', error='ONE_MINUTE_COOLDOWN')
            if len(recent) >= 24:
                return 429, dict(status='FAILED', error='DAILY_REVIEW_BUDGET_EXHAUSTED')
            pid, created = process_identity()
            job = dict(job_id=uuid4().hex, status='RUNNING', started_at=now.isoformat(),
                       binding=dict(binding), worker_pid=pid, worker_created_at=created)
            if event_pending is not None:
                job['event_pending'] = event_pending
            self.save(connection, job)
            with _workers_lock:
                _workers.add(job['job_id'])
        worker = Thread(target=self.run, args=(job,), daemon=True, name='investment-review')
        try:
            worker.start()
        except Exception:
            with _workers_lock:
                _workers.discard(job['job_id'])
            job.update(status='FAILED', error='WORKER_START_FAILED')
            with closing(self.connection()) as connection, connection:
                self.save(connection, job)
            raise
        return 202, dict(status='RUNNING', job_id=job['job_id'], started_at=job['started_at'])

    @staticmethod
    def normalize_preview(value):
        result = deepcopy(value)
        if result.get('effective_target_quantities') is None:
            result['effective_target_quantities'] = result.get('daily_gate', {}).get('effective_target_quantities')
        if result.get('status') not in ('READY', 'HOLD') or not isinstance(result.get('effective_target_quantities'), dict):
            raise ValueError('CURRENT_STRATEGY_PREVIEW_UNAVAILABLE')
        return result

    def run(self, job):
        run_started = monotonic()
        stages, stage_lock = {}, Lock()
        def measured(name, callback, *args, **kwargs):
            began = monotonic()
            outcome = 'FAILED'
            try:
                value = callback(*args, **kwargs)
                outcome = 'COMPLETE'
                return value
            finally:
                with stage_lock:
                    stages[name] = dict(seconds=max(0.0, monotonic()-began), status=outcome)
        job['stage_timings'] = stages
        try:
            from data.news_desk import collect
            from data.news_investment_model_v1 import analyze_review
            from data.news_investment_sources_v1 import build_sources
            binding = job['binding']
            if job.get('event_pending'):
                self.validate_event_control(job['event_pending'])
            account, target, names = measured('initial_bound_context', self.bound_context, binding)
            # News capture does not wait for a potentially slow market preview.
            def parallel_inputs():
                with ThreadPoolExecutor(max_workers=2) as executor:
                    capture = executor.submit(measured, 'news_capture',
                                              (lambda *args, **kwargs: deepcopy(job['event_pending']['snapshot'])) if job.get('event_pending') else (self.collector or collect),
                                              self.cache, limit=20)
                    initial = executor.submit(measured, 'initial_preview', self.preview, **binding)
                    snapshot = capture.result()
                    original = self.normalize_preview(initial.result())
                    return snapshot, original
            snapshot, original = measured('parallel_capture_preview', parallel_inputs)
            self.bound_context(binding)
            quantities = original['effective_target_quantities']
            positions = [dict(security_id=sid, ticker=names.get(sid, ''),
                              original_qty=account['shares'].get(sid, 0), target_qty=quantities.get(sid, 0))
                         for sid in sorted(set(account['shares']) | set(quantities))
                         if account['shares'].get(sid,0)>0 or quantities.get(sid,0)>0]
            source_result = measured('source_builder', self.source_builder or build_sources, snapshot, self.cache, positions, max_chars=110000)
            generation = self.news_generation()
            sources = source_result['sources']
            if not sources:
                raise ValueError('NO_COMPLETE_CURRENT_SOURCE_BODY')
            analysis_started = self.clock()
            remaining_seconds = 360 - (analysis_started-moment(job['started_at'])).total_seconds()
            model_timeout = min(120, int(remaining_seconds))
            if model_timeout <= 0:
                raise ValueError('REVIEW_DEADLINE_EXCEEDED')
            def lookup():
                if job.get('event_pending'):
                    pending = job['event_pending']
                    self.validate_event_control(pending)
                    if self.clock() >= moment(pending['opinion_valid_until']):
                        raise ValueError('EVENT_OPINION_EXPIRED')
                    actual_domain = {(row['security_id'], row['ticker']) for row in positions}
                    opinion_domain = {(row['security_id'], row['ticker']) for row in pending['positions']}
                    if actual_domain != opinion_domain or source_result['fingerprint'] != pending['source_fingerprint']:
                        raise ValueError('EVENT_REVIEW_DOMAIN_CHANGED')
                    return deepcopy(pending['answer'])
                return (self.model or analyze_review)(list(sources.values()), positions,
                    self.cache/'investment_analysis', timeout=model_timeout, max_chars=120000)
            answer = measured('current_analysis_lookup', lookup)
            analysis_attempt_finished = self.clock()
            job['analysis_receipt'] = answer.get('receipt')
            if answer.get('status') not in ('SUCCEEDED', 'CACHED'):
                raise ValueError('MODEL_REVIEW_UNAVAILABLE')
            # No account lock is held during model execution. Re-read and re-quote.
            account, target, names = self.bound_context(binding)
            fresh = self.normalize_preview(measured('post_analysis_preview', self.preview, **binding))
            if fresh['effective_target_quantities'] != quantities:
                raise ValueError('STRATEGY_TARGET_CHANGED_DURING_ANALYSIS')
            finished = self.clock()
            if (finished-moment(job['started_at'])).total_seconds() > 360:
                raise ValueError('REVIEW_DEADLINE_EXCEEDED')
            deadline = min(finished+timedelta(minutes=5), moment(fresh['risk_valid_until']))
            if job.get('event_pending'):
                deadline = min(deadline, moment(job['event_pending']['opinion_valid_until']))
            for quote in fresh.get('reference_quotes', {}).values():
                deadline = min(deadline, moment(quote['reference_valid_until']))
            review = dict(schema='NEWS_INVESTMENT_REVIEW_V1', review_id=job['job_id'],
                          created_at=finished.isoformat(), valid_until=deadline.isoformat(),
                          account_revision=account['revision'], target_id=target['target_id'],
                          proposal_id=target['proposal_id'], rows=answer['rows'])
            proposal = build_review_proposal(review=review, original_preview=fresh, account=account,
                                             sources=sources, now=finished.isoformat())
            for row in proposal['rows']:
                row['ticker'] = names.get(row['security_id'], row['security_id'])
                for source in row['evidence']:
                    source['publication_age_seconds'] = (finished-moment(source['published_at'])).total_seconds()
                    source['discovery_delay_seconds'] = (moment(source['observed_at'])-moment(source['published_at'])).total_seconds()
            proposal.update(coverage=source_result['coverage'], model=answer.get('model'),
                timeliness=dict(requested_at=job['started_at'], analysis_started_at=analysis_started.isoformat(),
                    analysis_completed_at=(answer.get('receipt') or {}).get('finished_at', finished.isoformat()),
                    revalidated_at=finished.isoformat(), cached=bool(job.get('event_pending')) or answer.get('status')=='CACHED',
                    analysis_seconds=(answer.get('receipt') or {}).get('elapsed_seconds'),
                    current_analysis_lookup_seconds=stages['current_analysis_lookup']['seconds'],
                    current_analysis_attempt_completed_at=analysis_attempt_finished.isoformat(),
                    original_model_started_at=(answer.get('receipt') or {}).get('started_at'),
                    original_model_completed_at=(answer.get('receipt') or {}).get('finished_at'),
                    original_model_elapsed_seconds=(answer.get('receipt') or {}).get('elapsed_seconds'),
                    total_seconds=(finished-moment(job['started_at'])).total_seconds(),
                    mode='EVENT_SOURCE_PREANALYSIS_FINALIZED' if job.get('event_pending') else 'ON_DEMAND_FRESH_CAPTURE', continuous_monitoring=bool(job.get('event_pending')),
                    source_opinion_generated_at=(answer.get('receipt') or {}).get('finished_at') if job.get('event_pending') else None,
                    first_execution_window=deepcopy(job['event_pending']['execution_window']) if job.get('event_pending') else None,
                    source_discovered_at=min(event['discovered_at'] for event in job['event_pending']['snapshot']['events']) if job.get('event_pending') and job['event_pending']['snapshot']['events'] else None,
                    pre_move_detection_verified=False,
                    note='Publication and discovery delays are measured; reading after a price move is not evidence of avoiding that move.'),
                original_preview_sha256=digest(fresh), original_preview=deepcopy(fresh))
            def project_risk_plan():
                if self.risk_plan_provider is not None:
                    return self.risk_plan_provider(original=deepcopy(fresh), proposal=deepcopy(proposal),
                                                   account=deepcopy(account), target=deepcopy(target),
                                                   now=self.clock().isoformat())
                return build_risk_plan(proposal=proposal, original_preview=fresh, account=account,
                                       now=self.clock().isoformat())
            proposal['risk_plan'] = measured('risk_plan_projection', project_risk_plan)
            def final_validation():
                if job.get('event_pending'):
                    self.validate_event_control(job['event_pending'])
                self.bound_context(binding)
                if self.news_generation() != generation:
                    raise ValueError('NEWS_UPDATED_DURING_ANALYSIS')
                # Potentially blocking context/source checks happen before the
                # final clock sample. No quote or total-job deadline is renewed.
                final_now = self.clock()
                elapsed = (final_now-moment(job['started_at'])).total_seconds()
                if not 0 <= elapsed <= 360:
                    raise ValueError('REVIEW_DEADLINE_EXCEEDED')
                if final_now >= moment(proposal['review_valid_until']):
                    raise ValueError('REVIEW_EXPIRED')
                risk_plan = proposal.get('risk_plan', {})
                if risk_plan.get('status') == 'READY' and final_now >= moment(risk_plan['valid_until']):
                    raise ValueError('RISK_PLAN_EXPIRED')
            measured('final_validation', final_validation)
            job.update(status='COMPLETE', proposal=proposal, source_fingerprint=source_result['fingerprint'],
                       news_generation=generation)
        except Exception as error:
            reason = str(error)
            job.update(status='FAILED', error=reason if reason.isupper() and len(reason)<120 else 'INVESTMENT_REVIEW_FAILED')
        finally:
            job['finished_at'] = self.clock().isoformat()
            try:
                job['worker_elapsed_before_persistence_seconds'] = max(0.0, monotonic()-run_started)
                job['request_to_result_ready_wall_seconds'] = (moment(job['finished_at'])-moment(job['started_at'])).total_seconds()
                job['timing_scope'] = 'Worker monotonic duration excludes queue wait and persistence; request-to-ready UTC duration includes queue wait but excludes persistence. Neither is full user-visible completion time.'
                if job.get('proposal'):
                    job['proposal']['timeliness']['stage_timings'] = deepcopy(stages)
                    for key in ('worker_elapsed_before_persistence_seconds','request_to_result_ready_wall_seconds','timing_scope'):
                        job['proposal']['timeliness'][key] = job[key]
                with closing(self.connection()) as connection, connection:
                    self.save(connection, job)
            finally:
                with _workers_lock:
                    _workers.discard(job['job_id'])

    def status(self, job_id):
        with closing(self.connection()) as connection:
            row = connection.execute('SELECT document FROM jobs WHERE id=?', (job_id,)).fetchone()
        if row is None:
            return dict(status='FAILED', error='UNKNOWN_JOB')
        job = json.loads(row[0])
        if job['status'] == 'RUNNING':
            if (self.clock()-moment(job['started_at'])).total_seconds() > 360:
                return dict(status='FAILED', job_id=job_id, error='REVIEW_DEADLINE_EXCEEDED')
            # Non-financial progress must not wait for the preview snapshot lock.
            # Completed proposals still pass every binding/expiry/news check below.
            return {key: job[key] for key in ('status', 'job_id', 'started_at') if key in job}
        try:
            if job.get('event_pending'):
                self.validate_event_control(job['event_pending'])
            self.bound_context(job['binding'])
            if job['status'] == 'COMPLETE' and self.clock() >= moment(job['proposal']['review_valid_until']):
                raise ValueError('REVIEW_EXPIRED')
            risk_plan = job.get('proposal', {}).get('risk_plan', {})
            if job['status'] == 'COMPLETE' and risk_plan.get('status') == 'READY' and self.clock() >= moment(risk_plan['valid_until']):
                raise ValueError('RISK_PLAN_EXPIRED')
            if job['status'] == 'COMPLETE' and self.news_generation() != job['news_generation']:
                raise ValueError('NEWS_UPDATED')
        except Exception:
            timing = {key: job[key] for key in ('stage_timings','worker_elapsed_before_persistence_seconds','request_to_result_ready_wall_seconds','timing_scope') if key in job}
            return dict(status='STALE', job_id=job_id, error='REFRESH_ACCOUNT_AND_REVIEW', **timing)
        return {key: job[key] for key in ('status','job_id','started_at','finished_at','proposal','error','stage_timings','worker_elapsed_before_persistence_seconds','request_to_result_ready_wall_seconds','timing_scope') if key in job}
