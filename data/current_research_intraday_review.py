"""Read-only local intraday observations; no fills, returns, or trusted timestamps."""
from datetime import date, datetime
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import json
import re
from data.current_research_intraday_journal import IntradayObservationJournal
from data.current_research_intraday_execution import decode_intraday_reference

NY = ZoneInfo('America/New_York')


def _time(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('NAIVE_OBSERVATION_TIME')
    return result


def _require(value, reason):
    if not value:
        raise ValueError(reason)


def review_intraday_session(journal_root, session, *, expected_event_hashes=None, journal=None, inventory_scope='SESSION'):
    """Review exactly the saved session inventory, without inventing missing events."""
    _require(date.fromisoformat(session).isoformat() == session, 'INVALID_SESSION')
    _require(inventory_scope in ('SESSION','PINNED_CAP_CLOSURE'), 'INVALID_INVENTORY_SCOPE')
    if inventory_scope == 'PINNED_CAP_CLOSURE':
        _require(isinstance(expected_event_hashes,dict) and expected_event_hashes, 'PINNED_CLOSURE_RECEIPTS_REQUIRED')
    journal = IntradayObservationJournal(journal_root) if journal is None else journal
    folder = journal.root / 'events' / session
    _require(folder.resolve().is_relative_to(journal.root / 'events'), 'SESSION_PATH_OUTSIDE_JOURNAL')
    records = []; events = {}
    for path in sorted(folder.glob('*.json')):
        relative = path.relative_to(journal.root).as_posix()
        record = dict(path=relative, issues=[], observations=[])
        records.append(record)
        try:
            _require(path.resolve().is_relative_to(journal.root / 'events'), 'EVENT_PATH_OUTSIDE_JOURNAL')
            digest = sha256(path.read_bytes()).hexdigest(); record['event_sha256'] = digest
            expected = (expected_event_hashes or {}).get(relative)
            record['external_expected_hash_matched'] = expected is not None and expected == digest
            if expected is not None:_require(expected == digest, 'EXPECTED_EVENT_HASH_MISMATCH')
            event = journal.read_event(relative, expected_sha256=digest)
            identifier = event['event_id']; sequence = event['observation_sequence']
            _require(isinstance(identifier,str) and re.fullmatch(r'[0-9a-f]{32}',identifier), 'INVALID_EVENT_ID')
            _require(type(sequence) is int and sequence > 0, 'INVALID_SEQUENCE')
            _require(isinstance(event['process_boot_id'],str) and re.fullmatch(r'[0-9a-f]{32}',event['process_boot_id']), 'INVALID_BOOT_ID')
            record.update(event_id=identifier, process_boot_id=event['process_boot_id'], observation_sequence=sequence,
                          research_id=event['research_id'], service_source_sha256=event['service_source_sha256'])
            _require(path.stem == identifier and identifier not in events, 'DUPLICATE_OR_WRONG_EVENT_ID')
            _require(type(sequence) is int and sequence > 0, 'INVALID_SEQUENCE')
            started = _time(event['request_started_at']); finished = _time(event['request_finished_at'])
            _require(started <= finished and started.astimezone(NY).date().isoformat() == session, 'EVENT_SESSION_OR_TIME_MISMATCH')
            response = event['response']
            _require(all(response[key] == event[key] for key in ('research_id','process_boot_id','observation_sequence')), 'RESPONSE_EVENT_BINDING_MISMATCH')
            _require(response['research_only'] is True and response['execution_blocked'] is True, 'NOT_RESEARCH_RESPONSE')
            events[identifier] = (event, record)
            record['captures'] = event['captures']
            record['status'] = response['status']
            for capture in event['captures']:
                captured = _time(capture['captured_at'])
                _require(captured <= finished, 'CAPTURE_AFTER_REQUEST')
                if capture['role'] == 'FETCHED':
                    _require(started <= captured, 'FETCH_CAPTURE_BEFORE_REQUEST')
            for row in response['stocks']:
                item = dict(row); record['observations'].append(item)
                checked = _time(row['checked_at'])
                _require(started <= checked <= finished, 'CHECKED_TIME_OUTSIDE_REQUEST')
                if row['status'] != 'AVAILABLE':
                    _require(row.get('limit_price') is None and row.get('fresh_cash_reference') is None, 'FAILED_ROW_EXPOSES_PRICE')
                    continue
                used = [c for c in event['captures'] if c['role'] == 'USED' and c['ticker'] == row['ticker']]
                _require(len(used) == 1, 'USED_CAPTURE_NOT_UNIQUE')
                used = used[0]; captured = _time(used['captured_at'])
                _require(captured == _time(row['quote_response_captured_at']), 'USED_CAPTURE_TIME_MISMATCH')
                replay = decode_intraday_reference((journal.root / used['path']).read_bytes(), ticker=row['ticker'], now=checked, captured_at=captured)
                _require(replay['session'] == session, 'QUOTE_SESSION_MISMATCH')
                for key, value in replay.items():
                    _require(row[key] == value, 'REPLAY_MISMATCH:' + key)
                _require(row['quote_response_age_seconds'] == (checked-captured).total_seconds(), 'CAPTURE_AGE_MISMATCH')
                cap = Fraction(row['limit_price']); before = row['cap_before']
                _require(cap == min(Fraction(row['observed_cap']), Fraction(before)) if before is not None else cap == Fraction(row['observed_cap']), 'CAP_FORMULA_MISMATCH')
                fresh = row['fresh_cash_reference']; cash = Fraction(fresh['cash']); quantity = fresh['quantity']
                _require(type(quantity) is int and quantity == cash//cap and Fraction(fresh['limit_price']) == cap, 'FRESH_QUANTITY_MISMATCH')
                _require(Fraction(fresh['commission']) == 0 and Fraction(fresh['notional']) == quantity*cap
                         and Fraction(fresh['residual_cash']) == cash-quantity*cap, 'CASH_IDENTITY_MISMATCH')
                binding = event.get('research_binding', {})
                _require(Fraction(binding['budget_identity_exact']['entered_cash']) == cash and fresh['research_id'] == event['research_id'], 'BUDGET_BINDING_MISMATCH')
                item['raw_replay_verified'] = True
        except Exception as error:
            record['issues'].append(str(error))
    present={record['path'] for record in records}
    if inventory_scope == 'PINNED_CAP_CLOSURE':
        _require(present == set(expected_event_hashes), 'PINNED_CLOSURE_INVENTORY_MISMATCH')
    missing_receipts=sorted(set(expected_event_hashes or {})-present)
    coverage_notes=[]
    records.sort(key=lambda r:(r.get('process_boot_id',''),r.get('observation_sequence',0),r['path']))
    latest = {}; sequences = {}; seen_sequences = set(); cap_dependencies = []
    for record in records:
        if 'event_id' not in record or record['issues']:continue
        boot=record['process_boot_id']; seq=record['observation_sequence']; sequence_key=(boot,seq)
        if sequence_key in seen_sequences:record['issues'].append('DUPLICATE_BOOT_SEQUENCE')
        seen_sequences.add(sequence_key)
        previous_sequence=sequences.get(boot)
        if previous_sequence is None and seq>1:
            coverage_notes.append(dict(process_boot_id=boot,first_sequence=seq,reason='SESSION_BOOT_PREFIX_NOT_COVERED_MAY_BE_PRIOR_SESSION'))
        if previous_sequence is not None and seq != previous_sequence+1:
            if inventory_scope == 'SESSION':
                record['issues'].append('MISSING_SEQUENCE_RANGE:'+str(previous_sequence+1)+'..'+str(seq-1))
            else:
                coverage_notes.append(dict(process_boot_id=boot,first_missing_sequence=previous_sequence+1,
                    last_missing_sequence=seq-1,reason='PINNED_CAP_CLOSURE_DOES_NOT_PROVE_FULL_SESSION_OR_LATEST'))
        sequences[boot]=seq
        for row in record['observations']:
            if row['status'] != 'AVAILABLE':continue
            key=(boot,record['research_id'],row['ticker'],row.get('session'))
            try:
                cap=Fraction(row['limit_price']); previous=latest.get(key)
                if previous is not None:
                    _require(cap<=previous[0], 'CAP_INCREASED_WITHIN_BOOT')
                    if row.get('cap_persistence') == 'TRANSACTIONAL_LOCAL_SQLITE_MIN_ACROSS_RESTARTS':
                        # Another process may have committed a lower cap since
                        # this boot's last response; its origin is checked below.
                        _require(Fraction(row['cap_before'])<=previous[0], 'CAP_BEFORE_INCREASED_FROM_LAST_SAVED')
                    else:
                        _require(Fraction(row['cap_before'])==previous[0], 'CAP_BEFORE_DIFFERS_FROM_LAST_SAVED')
                for field in ('prior_cap_event_id','cap_origin_event_id'):
                    target=row.get(field)
                    if target is None:
                        _require(field=='prior_cap_event_id' and row['cap_before'] is None, 'MISSING_CAP_ORIGIN')
                        continue
                    _require(target in events, 'MISSING_CAP_EVENT:'+target)
                    source,source_record=events[target]
                    _require(not source_record['issues'], 'SOURCE_CAP_EVENT_INVALID:'+target)
                    cross_boot = source['process_boot_id'] != boot
                    _require(source['research_id']==record['research_id'], 'CAP_EVENT_SCOPE_MISMATCH')
                    if cross_boot:
                        _require(row.get('cap_persistence') == 'TRANSACTIONAL_LOCAL_SQLITE_MIN_ACROSS_RESTARTS', 'CAP_EVENT_SCOPE_MISMATCH')
                    else:
                        _require(source['observation_sequence'] < seq or (field=='cap_origin_event_id' and target==record['event_id']), 'CAP_EVENT_ORDER_MISMATCH')
                    source_rows=[r for r in source['response']['stocks'] if r['ticker']==row['ticker'] and r.get('session')==row.get('session') and r['status']=='AVAILABLE']
                    _require(len(source_rows)==1, 'CAP_EVENT_ROW_MISMATCH')
                    if cross_boot:
                        source_row = source_rows[0]
                        source_security = source.get('research_binding', {}).get('selected_security', {})
                        current_security = events[record['event_id']][0].get('research_binding', {}).get('selected_security', {})
                        _require(source_row.get('cap_persistence') == row['cap_persistence']
                                 and source_security == current_security
                                 and isinstance(current_security.get('security_id'), str) and current_security['security_id']
                                 and current_security.get('ticker') == row['ticker'], 'CAP_EVENT_SCOPE_MISMATCH')
                        _require(_time(source_row['checked_at']) <= _time(row['checked_at']), 'CAP_EVENT_ORDER_MISMATCH')
                        if field == 'cap_origin_event_id':
                            _require(source_row.get('cap_origin_event_id') == target, 'CAP_ORIGIN_NOT_SELF_ROOTED')
                    if target != record['event_id']:
                        cap_dependencies.append((record, source_record, target))
                    expected=cap if field=='cap_origin_event_id' else Fraction(row['cap_before'])
                    _require(Fraction(source_rows[0]['limit_price'])==expected, 'CAP_EVENT_PRICE_MISMATCH')
                latest[key]=(cap,record['event_id'])
            except Exception as error:
                record['issues'].append(str(error))
    # Boot IDs have no chronological ordering. Propagate damage after every
    # source record has completed its own cap-chain checks.
    changed = True
    while changed:
        changed = False
        for record, source_record, target in cap_dependencies:
            issue = 'SOURCE_CAP_EVENT_INVALID:' + target
            if source_record['issues'] and issue not in record['issues']:
                record['issues'].append(issue); changed = True
    issues=sum(bool(r['issues']) for r in records)
    return dict(schema='INTRADAY_OBSERVATION_REVIEW_V1',session=session,inventory_scope=inventory_scope,
                status='INCOMPLETE' if issues or missing_receipts else 'NO_OBSERVATIONS' if not records else 'REVIEWED_LOCAL_OBSERVATIONS',
                missing_receipts=missing_receipts,coverage_notes=coverage_notes,
                event_count=len(records),events_with_issues=issues,records=records,
                reviewer_source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                decoder_source_sha256=sha256(Path(__file__).with_name('current_research_intraday_execution.py').read_bytes()).hexdigest(),
                external_receipts_provided=expected_event_hashes is not None,
                limitations=['Local hashes are not external trusted timestamps or proof the UI displayed a suggestion.',
                             'Inventory contains only saved events; missing failed writes and pre-enable requests cannot be reconstructed.',
                             'Research snapshot bindings are archived claims; this review does not re-certify their entire source closure.',
                             'Raw replay uses the identified current decoder; no network, fills, trades, returns, or backfilled observations.'])


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--journal-root',required=True);parser.add_argument('--session',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args(); report=review_intraday_session(args.journal_root,args.session)
    with Path(args.output).open('x',encoding='utf-8') as stream:json.dump(report,stream,ensure_ascii=False,indent=2)
    print(json.dumps({key:report[key] for key in ('status','event_count','events_with_issues')}))

if __name__=='__main__':main()
