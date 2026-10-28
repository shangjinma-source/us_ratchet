"""Opt-in local discovery worker. No financial writes or external scheduled jobs."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from threading import Event, Lock, Thread
from zoneinfo import ZoneInfo

from data.news_event_sources_v1 import EventSources, moment
from data.news_event_model_v1 import analyze_event
from data.news_investment_sources_v1 import build_sources
from data.news_observation_history import append_observations


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()




class EventNewsPipeline:
    def __init__(self, service, *, sources_factory=EventSources, analyzer=analyze_event,
                 source_builder=build_sources, clock=None, calendar_window=None):
        self.service, self.cache = service, service.cache
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sources_factory, self.analyzer, self.source_builder = sources_factory, analyzer, source_builder
        self.calendar_window = calendar_window
        self.lock, self.stop_event = Lock(), Event()
        self.worker = None
        self.worker_error = None

    def connection(self):
        self.cache.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.cache/'event_pipeline_v1.sqlite3', timeout=5)
        connection.execute('PRAGMA synchronous=FULL')
        connection.execute('CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, document TEXT)')
        connection.execute('CREATE TABLE IF NOT EXISTS control (id INTEGER PRIMARY KEY, enabled INTEGER, generation INTEGER)')
        connection.execute('CREATE TABLE IF NOT EXISTS lease (id INTEGER PRIMARY KEY, pid INTEGER, created REAL)')
        return connection

    def load(self):
        with closing(self.connection()) as connection:
            row = connection.execute('SELECT document FROM state WHERE id=1').fetchone()
        state = json.loads(row[0]) if row else dict(status='DISABLED', seen={}, consumed=[], pending=None)
        with closing(self.connection()) as connection:
            control = connection.execute('SELECT enabled,generation FROM control WHERE id=1').fetchone()
        state['enabled'] = bool(control and control[0])
        state['control_generation'] = control[1] if control else 0
        return state

    def save(self, state):
        with closing(self.connection()) as connection, connection:
            connection.execute('INSERT OR REPLACE INTO state VALUES (1,?)', (json.dumps(state),))

    def status(self):
        state = self.load()
        if not state['enabled']:
            state['status'] = 'DISABLED'
        keys = ('enabled', 'status', 'checked_at', 'source_status', 'unsupported_tickers', 'error', 'job_id',
                'opinion_generated_at', 'opinion_valid_until', 'request_count', 'triggered_sources')
        worker_alive = bool(self.worker and self.worker.is_alive())
        return dict({key: state[key] for key in keys if key in state}, orders_created=False,
                    automatic_orders=False, worker_alive=worker_alive,
                    last_worker_error=deepcopy(self.worker_error),
                    continuous_monitoring=bool(state['enabled']) and worker_alive,
                    limitation='MRNA/SNDK issuer lists only; unchanged list metadata cannot detect body-only revisions. Source opinions are not trade proposals.')

    def set_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError('BOOLEAN_REQUIRED')
        with closing(self.connection()) as connection, connection:
            connection.execute('BEGIN IMMEDIATE')
            row = connection.execute('SELECT generation FROM control WHERE id=1').fetchone()
            connection.execute('INSERT OR REPLACE INTO control VALUES (1,?,?)', (int(enabled), (row[0] if row else 0)+1))
        return self.status()

    def valid_generation(self, generation):
        current = self.load()
        return (not self.stop_event.is_set() and current['enabled']
                and current['control_generation'] == generation)

    def valid_event(self, pending):
        current = self.load()
        return (self.valid_generation(pending['control_generation'])
                and current.get('source_generation') == pending['source_generation']
                and current.get('source_confirmed') is True)

    def start_worker(self):
        if self.worker and self.worker.is_alive():
            return
        self.stop_event.clear()
        def work():
            while not self.stop_event.wait(60):
                try:
                    self.tick()
                except Exception:
                    # Fail closed and keep the bounded worker available for a later tick.
                    self.worker_error = dict(code='EVENT_WORKER_TICK_FAILED', at=self.clock().isoformat())
        self.worker = Thread(target=work, daemon=True, name='news-event-discovery')
        self.worker.start()

    def stop_worker(self):
        self.stop_event.set()
        if self.worker:
            self.worker.join(timeout=2)

    def domain(self):
        self.service.validate()
        account, target, names = self.service.context()
        quantities = target['payload']['target_quantities']
        identifiers = {sid for sid, quantity in account['shares'].items() if quantity > 0}
        identifiers |= {sid for sid, quantity in quantities.items() if quantity > 0}
        positions = [dict(security_id=sid, ticker=names[sid]) for sid in sorted(identifiers)]
        if len({row['ticker'] for row in positions}) != len(positions):
            raise ValueError('AMBIGUOUS_TICKER_IDENTITY')
        binding = dict(expected_revision=account['revision'], target_id=target['target_id'], expected_proposal_id=target['proposal_id'])
        self.service.bound_context(binding)
        return binding, positions

    def tick(self):
        if not self.lock.acquire(blocking=False):
            return dict(status='BUSY')
        state = None
        claimed = False
        try:
            from data.news_refresh_service import owner_alive, process_identity
            with closing(self.connection()) as connection, connection:
                connection.execute('BEGIN IMMEDIATE')
                owner = connection.execute('SELECT pid,created FROM lease WHERE id=1').fetchone()
                if owner and owner_alive(*owner):
                    return dict(status='BUSY')
                connection.execute('INSERT OR REPLACE INTO lease VALUES (1,?,?)', process_identity())
                claimed = True
            state = self.load()
            now = self.clock()
            if not state['enabled']:
                state.update(status='DISABLED', pending=None)
                return self.status()
            if state.get('checked_at'):
                elapsed = (now-moment(state['checked_at'])).total_seconds()
                if elapsed < 0:
                    raise ValueError('DISCOVERY_CLOCK_REVERSED')
                if elapsed < 60:
                    return self.status()
            state['checked_at'] = now.isoformat()
            state.pop('error', None)
            binding, positions = self.domain()
            domain_hash = digest(dict(binding=binding, positions=positions))
            if state.get('domain_hash') != domain_hash:
                state.update(domain_hash=domain_hash, pending=None, job_id=None)
            pending = state.get('pending')
            collector = self.sources_factory(self.cache, clock=self.clock)
            candidates, statuses, listed = [], [], []
            tickers = sorted({row['ticker'] for row in positions})
            state['unsupported_tickers'] = [ticker for ticker in tickers if ticker not in collector.supported]
            for ticker in tickers:
                if ticker not in collector.supported:
                    continue
                try:
                    rows = collector.discover(ticker)
                    listed.extend(rows)
                    statuses.append(dict(ticker=ticker, status='LIST_OK', count=len(rows)))
                    for row in rows:
                        key = digest({name: row[name] for name in ('ticker', 'url', 'title', 'published_at')})
                        prior = state['seen'].get(key)
                        if prior and (prior['status'] != 'BODY_FAILED' or prior['attempts'] >= 2):
                            continue
                        age = (moment(row['discovered_at'])-moment(row['published_at'])).total_seconds()
                        if not 0 <= age <= 600:
                            state['seen'][key] = dict(status='BASELINE_NOT_TIMELY', attempts=0)
                            continue
                        candidates.append((key, row))
                except Exception:
                    statuses.append(dict(ticker=ticker, status='LIST_FAILED_NO_WATERMARK'))
            events, accepted_keys = [], []
            list_fingerprint = digest([{key: row[key] for key in ('ticker', 'url', 'title', 'published_at')} for row in listed])
            source_confirmed = bool(statuses) and all(row['status'] == 'LIST_OK' for row in statuses)
            if state.get('last_list_fingerprint') != list_fingerprint or state.get('source_confirmed') != source_confirmed:
                state['source_generation'] = state.get('source_generation', 0)+1
            state.update(last_list_fingerprint=list_fingerprint, source_confirmed=source_confirmed)
            self.save(state)  # Inflight finalizers see changes/failures before any body recovery.
            for key, row in sorted(candidates, key=lambda pair: pair[1]['published_at'], reverse=True)[:2]:
                prior = state['seen'].get(key, dict(attempts=0))
                try:
                    event = collector.hydrate(row)
                    body_key = digest(dict(ticker=row['ticker'], body=event['content_sha256']))
                    if body_key in state['consumed']:
                        state['seen'][key] = dict(status='BODY_ALREADY_CONSUMED', attempts=prior['attempts']+1)
                        continue
                    events.append(event)
                    accepted_keys.append((key, body_key))
                    state['seen'][key] = dict(status='BODY_READY', attempts=prior['attempts']+1)
                except Exception:
                    state['seen'][key] = dict(status='BODY_FAILED', attempts=prior['attempts']+1)
            state.update(source_status=statuses, request_count=collector.request_count)
            self.service.bound_context(binding)
            if events:
                snapshot = dict(generated_at=self.clock().isoformat(), events=events, source_receipts=collector.receipts)
                source_result = self.source_builder(snapshot, self.cache, positions, max_chars=110000)
                if len(source_result['sources']) != len(events):
                    raise ValueError('COMPLETE_EVENT_SOURCE_REQUIRED')
                append_observations(self.cache, events)
                state['pending'] = None
                state['consumed'].extend(body_key for _, body_key in accepted_keys)
                state['status'] = 'ANALYZING_PUBLIC_SOURCES'
                self.save(state)  # Reserve this body even if worker exits during inference.
                if not self.valid_generation(state['control_generation']):
                    raise ValueError('EVENT_PIPELINE_DISABLED')
                answer = self.analyzer(list(source_result['sources'].values()), positions,
                                       self.cache/'event_analysis', timeout=120, max_chars=120000)
                self.service.bound_context(binding)
                if not self.valid_generation(state['control_generation']):
                    raise ValueError('EVENT_PIPELINE_DISABLED')
                if answer['status'] == 'DEFERRED':
                    for key, body_key in accepted_keys:
                        state['consumed'].remove(body_key)
                        state['seen'][key] = dict(status='BODY_FAILED', attempts=0)
                    state['status'] = 'WAIT_SHARED_MODEL_BUDGET'
                    self.save(state)
                    return self.status()
                if answer['status'] not in ('SUCCEEDED', 'CACHED'):
                    raise ValueError('SOURCE_ANALYSIS_FAILED_ABSTAIN')
                generated = moment(answer['receipt']['finished_at'])
                if self.calendar_window is None:
                    raise ValueError('EVENT_CALENDAR_UNAVAILABLE_SOURCE_ONLY')
                execution_window = self.calendar_window(min(event['discovered_at'] for event in events))
                valid_until = moment(execution_window['valid_until'])
                state.update(status='SOURCE_OPINION_READY', opinion_generated_at=generated.isoformat(),
                             opinion_valid_until=valid_until.isoformat(), triggered_sources=len(events),
                             pending=dict(snapshot=snapshot, answer=answer, positions=positions,
                                          source_fingerprint=source_result['fingerprint'], binding=binding,
                                          control_generation=state['control_generation'], source_generation=state['source_generation'], list_fingerprint=list_fingerprint,
                                          opinion_valid_until=valid_until.isoformat(), execution_window=execution_window))
            elif pending:
                execution_window = pending['execution_window']
                fresh_window = self.calendar_window(min(event['discovered_at'] for event in pending['snapshot']['events']))
                if fresh_window != execution_window or now >= moment(pending['opinion_valid_until']):
                    state.update(pending=None, status='SOURCE_OPINION_EXPIRED_OR_CALENDAR_CHANGED')
                elif pending.get('job_id'):
                    result = self.service.status(pending['job_id'])
                    state['status'] = 'REVIEW_'+result['status']
                    if result['status'] != 'RUNNING':
                        state['pending'] = None
                elif any(row['status'] != 'LIST_OK' for row in statuses):
                    state['status'] = 'WAIT_SOURCE_RECONFIRMATION'
                elif list_fingerprint != pending['list_fingerprint']:
                    state['status'] = 'WAIT_CHANGED_SOURCE_LIST'
                elif any(not any(row['url'] == event['url'] and row['title'] == event['title'] and moment(row['published_at']) == moment(event['published_at']) for row in listed) for event in pending['snapshot']['events']):
                    state.update(pending=None, status='SOURCE_LIST_CHANGED')
                elif now < moment(execution_window['not_before']):
                    state['status'] = 'SOURCE_OPINION_WAIT_FIRST_OPEN'
                else:
                    self.service.bound_context(binding)
                    if not self.valid_generation(state['control_generation']):
                        raise ValueError('EVENT_PIPELINE_DISABLED')
                    code, result = self.service.start_event(binding, pending)
                    if code == 202:
                        pending['job_id'] = result['job_id']
                        state.update(job_id=result['job_id'], status='REVIEW_RUNNING')
                    else:
                        state['status'] = 'WAIT_REVIEW_BUDGET'
            elif not state.get('pending') and not state.get('status', '').startswith('REVIEW_'):
                state['status'] = 'NO_NEW_TIMELY_BODY'
        except Exception as error:
            message = str(error)
            if state is not None:
                state.update(status='ABSTAIN', error=message if message.isupper() and len(message)<100 else 'EVENT_PIPELINE_UNAVAILABLE')
        finally:
            try:
                if claimed:
                    try:
                        if state is not None:
                            self.save(state)
                    finally:
                        with closing(self.connection()) as connection, connection:
                            connection.execute('DELETE FROM lease WHERE id=1 AND pid=? AND created=?', process_identity())
            finally:
                self.lock.release()
        return self.status()
