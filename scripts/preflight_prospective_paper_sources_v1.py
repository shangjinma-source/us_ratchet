"""Read-only saved-source inventory. Never registers, captures, or admits orders."""
import argparse
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import time
from data.strategy_account_identity import PinnedStrategyIdentity
from data.strategy_daily_session_capture import reject_links, stamp


class Inventory:
    def __init__(self, root):
        self.root = Path(root).absolute()
        reject_links(self.root)
        self.cache = {}
        self.bytes = 0

    def read(self, reference):
        name, digest = reference['path'], reference['sha256']
        if (not isinstance(name, str) or '\\' in name or ':' in name or
                PurePosixPath(name).is_absolute() or any(p in ('', '.', '..') for p in name.split('/'))):
            raise ValueError('PREFLIGHT_PATH')
        key = (name, digest)
        if key not in self.cache:
            path = self.root / name
            reject_links(path)
            if not path.resolve().is_relative_to(self.root.resolve()):
                raise ValueError('PREFLIGHT_PATH')
            with path.open('rb') as stream:
                raw = stream.read(32 * 1024 * 1024 + 1)
            if len(raw) > 32 * 1024 * 1024 or sha256(raw).hexdigest() != digest:
                raise ValueError('PREFLIGHT_SOURCE_HASH_OR_SIZE')
            self.bytes += len(raw)
            if self.bytes > 512 * 1024 * 1024:
                raise ValueError('PREFLIGHT_TOTAL_BUDGET')
            self.cache[key] = raw
        return self.cache[key]

    def document(self, reference):
        return json.loads(self.read(reference))

    def closure(self, hashes):
        errors = []
        for path, digest in sorted(hashes.items()):
            try:
                self.read(dict(path=path, sha256=digest))
            except (OSError, ValueError) as error:
                errors.append(dict(path=path, reason=str(error)))
        return errors


def preflight(*, root, request, now=None):
    start = time.perf_counter()
    now = stamp(now or datetime.now(timezone.utc))
    inventory = Inventory(root)
    training = inventory.document(request['training'])
    identity = inventory.document(request['identity'])
    calendar = inventory.document(request['calendar'])
    errors = inventory.closure(training['source_hashes'])
    dates = [s['date'] for s in calendar['sessions']]
    if (calendar['schema'] != 'FIXED_EXCHANGE_SESSIONS_V1' or calendar['exchange'] != 'NASDAQ'
            or dates != sorted(set(dates))):
        raise ValueError('PREFLIGHT_CALENDAR')
    for row in calendar['sessions']:
        if not stamp(row['open']) < stamp(row['close']):
            raise ValueError('PREFLIGHT_SESSION')
    calendar_errors = inventory.closure({r['path']: r['sha256'] for r in calendar.get('source_references', [])})
    future = [(s, stamp(s['open']) + timedelta(minutes=30)) for s in calendar['sessions']]
    future = [(s, window) for s, window in future if window > now]
    next_window = None
    if future:
        session, window = future[0]
        next_window = dict(session=session['date'], accept_from=window.isoformat(),
                           accept_until=(window + timedelta(minutes=1)).isoformat(),
                           prior_closed_sessions=len([s for s in calendar['sessions'] if stamp(s['close']) < window]))
    resolver = PinnedStrategyIdentity(inventory.root, request['identity']['path'], request['identity']['sha256'])
    rows = []
    candidates = training['candidates']
    if len({r['security_id'] for r in candidates}) != len(candidates):
        raise ValueError('PREFLIGHT_DUPLICATE_CANDIDATE')
    for candidate in candidates:
        row = dict(ticker=candidate['ticker'], security_id=candidate['security_id'], identity_ok=False,
                   training_rows=len(candidate['raw_close']), daily_parent_candidates=[])
        try:
            checked = resolver(candidate['ticker'])
            if checked['security_id'] != candidate['security_id']:
                raise ValueError('PREFLIGHT_IDENTITY_MISMATCH')
            for path, digest in checked['source_hashes'].items():
                inventory.read(dict(path=path, sha256=digest))
            row['identity_ok'] = True
        except (OSError, ValueError, KeyError) as error:
            row['identity_error'] = str(error)
        rows.append(row)
    by_sid = {row['security_id']: row for row in rows}
    baseline_errors = []
    baseline = None
    if request.get('unit_baseline'):
        try:
            binding = request['unit_baseline']
            baseline = inventory.document(binding['review_reference'])
            if (baseline['schema'] != 'STRATEGY_TARGET_UNIT_REVIEW_V1'
                    or baseline['status'] != 'CONDITIONAL_CURRENT_UNITS_REVIEWED'
                    or baseline['training_manifest_sha256'] != request['training']['sha256']
                    or baseline['unresolved'] != [] or baseline['pending_rights'] != []
                    or stamp(baseline['reviewed_at']) > now):
                raise ValueError('PREFLIGHT_BASELINE_REVIEW')
            for sid, row in by_sid.items():
                unit = baseline['securities'].get(sid)
                if not unit:
                    continue
                try:
                    if unit['training_manifest_sha256'] != request['training']['sha256']:
                        raise ValueError('PREFLIGHT_BASELINE_TRAINING')
                    for name in unit['source_references']:
                        inventory.read(binding['source_mapping'][name])
                    row['saved_unit_baseline'] = dict(review_reference=binding['review_reference'],
                        covered_through=unit['covered_through'], source_count=len(unit['source_references']),
                        byte_closure_verified=True, current_units_verified=False,
                        inherited_account_authority=False)
                except (OSError, ValueError, KeyError) as error:
                    baseline_errors.append(dict(security_id=sid, reason=str(error)))
        except (OSError, ValueError, KeyError) as error:
            baseline_errors.append(dict(reason=str(error)))
    parent_errors = []
    # Explicitly pinned terminals are inventory inputs, not paper registrations.
    for reference in request.get('daily_terminals', []):
        try:
            terminal = inventory.document(reference)
            if terminal['status'] != 'DYNAMIC_DOMAIN_PACKET_SAVED' or stamp(terminal['finished_at']) > now:
                raise ValueError('PREFLIGHT_PARENT_TERMINAL')
            for sid, packet in terminal['packets'].items():
                receipt = inventory.document(packet['receipt_reference'])
                manifest = inventory.document(packet['manifest_reference'])
                if (receipt.get('normalization_reviewed') is not True or receipt.get('unresolved_units') != []
                        or receipt.get('pending_rights') != [] or set(manifest) != set(receipt['source_sha256'])):
                    raise ValueError('PREFLIGHT_PARENT_REVIEW')
                files = {}
                for name, ref in manifest.items():
                    if ref['sha256'] != receipt['source_sha256'][name]:
                        raise ValueError('PREFLIGHT_PARENT_CLOSURE')
                    files[name] = inventory.read(ref)
                normalized = json.loads(files[receipt['normalized_inputs_path']])
                if set(normalized['histories']) != {sid}:
                    raise ValueError('PREFLIGHT_PARENT_SID')
                if sid in by_sid:
                    by_sid[sid]['daily_parent_candidates'].append(dict(receipt_reference=packet['receipt_reference'],
                        manifest_reference=packet['manifest_reference'], session=terminal['session'],
                        signal_date=normalized['signal_date'], byte_closure_verified=True,
                        formal_semantics_verified=False, paper_registered=False))
        except (OSError, ValueError, KeyError, TypeError) as error:
            parent_errors.append(dict(reference=reference, reason=str(error)))
    benchmark = None
    if request.get('benchmark'):
        raw_benchmark = inventory.document(request['benchmark'])
        benchmark = dict(reference=request['benchmark'], saved_input_cpu_seconds=
            raw_benchmark['search_seconds'] + raw_benchmark['validation_seconds'],
            candidate_count=raw_benchmark['candidate_count'], current_whole_pipeline_seconds=None,
            window_feasibility_proven=False, excludes=['network', 'fresh risk review', 'daily normalization', 'archive', 'accept'])
    missing = [r['ticker'] for r in rows if not r['daily_parent_candidates']]
    for row in rows:
        if not row['identity_ok'] or errors:
            row['preparation_class'] = 'INDEPENDENT_SOURCE_REPAIR_REQUIRED'
        elif row['daily_parent_candidates']:
            row['preparation_class'] = 'SAVED_PARENT_REUSABLE_AFTER_CONTINUITY_REVIEW'
        elif row.get('saved_unit_baseline'):
            row['preparation_class'] = 'AUTO_CAPTURE_AND_FIRST_WINDOW_REVIEW_REQUIRED'
        else:
            row['preparation_class'] = 'INDEPENDENT_UNIT_BASELINE_REQUIRED'
    gaps = ['PAPER_DESCRIPTOR_AND_SOURCE_CLOSURE_NOT_REGISTERED', 'CURRENT_SOURCE_AND_FIRST_WINDOW_RUNTIME_NOT_PROVEN']
    if len(rows) != request.get('expected_candidate_count',98):
        gaps.append('CANDIDATE_COUNT_MISMATCH')
    if missing:
        gaps.append('DAILY_PARENT_NOT_IN_SUPPLIED_VERIFIED_BYTE_INVENTORY')
    if errors or calendar_errors or parent_errors or baseline_errors or any(not r['identity_ok'] for r in rows):
        gaps.append('SAVED_SOURCE_INVENTORY_ERRORS')
    if not next_window:
        gaps.append('FIXED_CALENDAR_HAS_NO_FUTURE_FIRST_WINDOW')
    elif next_window['prior_closed_sessions'] < 20:
        gaps.append('FIXED_CALENDAR_INSUFFICIENT_DAILY_HISTORY')
    return dict(schema='PROSPECTIVE_PAPER_READ_ONLY_PREFLIGHT_V1', status='GAPS_NOT_READY_FOR_ACTIVATION',
        observed_at=now.isoformat(), request_sha256=sha256(json.dumps(request, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        candidate_count=len(rows), expected_candidate_count=request.get('expected_candidate_count',98),
        candidate_count_matches=len(rows)==request.get('expected_candidate_count',98), training_cutoff=training['decision_date'],
        training_full_pit_verified=training.get('full_pit_verified',False), source_authenticated=False,
        source_errors=errors, calendar_errors=calendar_errors, parent_errors=parent_errors, baseline_errors=baseline_errors,
        next_future_window=next_window, calendar_final_session=dates[-1], securities=rows,
        missing_daily_parent_tickers=missing, blockers=gaps, benchmark=benchmark,
        preparation_counts={kind:sum(r['preparation_class']==kind for r in rows) for kind in sorted({r['preparation_class'] for r in rows})},
        first_parent_implementation=dict(existing_rule='data/strategy_daily_first_window_v3.py',
            missing_adapter='STATIC_VERIFIED_PAPER_FIRST_WINDOW_CONTEXT',
            steps=['Reuse registered identity and saved reviewed action-source baseline bytes, not old close alone',
                'Capture new last20 completed sessions plus notices; require exact identity, close/adjusted equality and baseline overlap',
                'Preserve existing action, issuer notice, clock and calendar checks; reject ambiguous unit changes',
                'Version shared reviewer to accept verified paper context instead of real ledger/target',
                'Archive first-parent proof then register its hash under paper authority; never copy WEB permissions'],
            already_executed=False),
        phases=[dict(phase='PREPARE_BEFORE_WINDOW', work=['pin code, calendar, 98 identities and historical training',
            'review and register selected security daily parents; unknown parent blocks',
            'prepare closed-day source bytes; replay against current account at admission']),
            dict(phase='FRESH_AT_DECISION', work=['fresh quotes and corporate actions, notices, halt evidence',
            'monthly continuous32 search using paper equity only when new monthly target is due',
            'daily SMA exposure and limit/cap verification; final clock and account revision CAS']),
            dict(phase='ACCEPT_10_00_TO_10_01', work=['accept only valid decisions inside unchanged window',
            'missed first window requires new future descriptor; never backfill']),
            dict(phase='AFTER_CLOSE', work=['collect actual completed minutes and settle existing DAY orders',
            'persist independent evidence and ledger; no presumed fills'])],
        inventory_seconds=time.perf_counter()-start, unique_bytes_read=inventory.bytes,
        network_calls=0, account_mutated=False, book_created=False, registration_created=False, orders_created=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--request', required=True)
    parser.add_argument('--request-sha256', required=True)
    args = parser.parse_args()
    inventory = Inventory(args.root)
    request = inventory.document(dict(path=args.request, sha256=args.request_sha256))
    print(json.dumps(preflight(root=args.root, request=request), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
