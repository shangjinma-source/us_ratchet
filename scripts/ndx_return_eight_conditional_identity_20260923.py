"""Explicit eight-security historical accounting assumptions; never legal admission."""
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive

BASE = ROOT / 'data/cache/research'
SOURCE = Path(__file__).resolve()
LOADED = {str(SOURCE): hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          str(archive.SOURCE): archive.drift.file_sha(archive.SOURCE)}
BOUND = {
    'seven': ('seven_dated_identity_assembly_20260919_v1/identities.json', 'ed810b2fc1626e05f3c1edee10212645dad37435461b8b7e8d01dcba1354e7c2'),
    'four': ('four_issuer_filing_identity_20260912_v1/dated_identity_adjudication.json', 'a70551b92c2154b9b1efe5eadb35b1f3c0f34b1c9a858506e3a2085df888d8a4'),
    'new': ('adbe_googl_web_transcription_20260923_v1/readback.json', 'd7294199d93073d7d416d0eac467d11abcff30043d7540448f4734e496116e09'),
    'schedule': ('return_lane_targets_20260923_v1/schedule.json', 'f5ee54df3651882791e4e6ecac548d0ec7847c44a9c551938d20c17c2cb23c70'),
    'linkage': ('return_lane_targets_20260923_v1/schedule_independent_linkage.json', 'f1529817338a022bb9831de9e4d08407a7eb7015098e085e43ea37506ac8ed0b'),
}
COORDINATES = {
    'AMAT': ('0000006951', '038222105'), 'AVGO': ('0001730168', '11135F101'),
    'BKR': ('0001701605', '05722G100'), 'CDNS': ('0000813672', '127387108'),
    'FTNT': ('0001262039', '34959E109'), 'GOOG': ('0001652044', '02079K107'),
    'ADBE': ('0000796343', '00724F101'), 'GOOGL': ('0001652044', '02079K305'),
}
ASSUMPTION = 'EXPLICIT_CONDITIONAL_STABILITY_BETWEEN_DATED_SNAPSHOTS_NOT_FULL_LEGAL_INTERVAL_CERTIFICATION'
CLOCK = [('2023-03-31', '2023-04-03'), ('2023-04-28', '2023-05-01'),
         ('2023-05-31', '2023-06-01'), ('2023-06-30', '2023-07-03'),
         ('2023-07-31', '2023-08-01'), ('2023-08-31', '2023-09-01')]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def assemble(documents):
    seven, four, new = (documents[key] for key in ('seven', 'four', 'new'))
    require(seven['conditional_window'] == dict(start='2023-03-31', end='2023-05-01'),
        'Preserve the older 21-day adjudication boundary')
    require(all(document['point_in_time_verified'] is False and document['promotion_allowed'] is False
        for document in (seven, four, new)), 'Dated facts must not imply legal admission')
    require(new['structural_byte_and_cover_readback_only'] is True
        and new['raw_http_original_verified_count'] == 0, 'Preserve web-only factual evidence limitation')
    rows = []
    for ticker, (cik, cusip) in sorted(COORDINATES.items()):
        sid = f'security:{cik}:{cusip}'
        if ticker in ('ADBE', 'GOOGL'):
            found = [row for row in new['rows'] if row['ticker'] == ticker]
            require(len(found) == 1, 'Unique new factual observation required')
            original = found[0]
            facts = original['facts']
            require((facts['subject_cik'], facts['cusip']) == (cik, cusip)
                and original['local_http_status'] == 403, 'New factual identity or failed capture differs')
            title = original['parsed_original_cover']['security_class_title']
            evidence = dict(type='WEB_FACTS_AND_SEPARATE_ORIGINAL_10K_COVER_WITH_FAILED_HTTP_CAPTURE',
                dated_evidence=original, source_role='new')
        elif ticker == 'GOOG':
            found = [row for row in four['rows'] if row['ticker'] == ticker]
            require(len(found) == 1, 'Unique GOOG dated fact required')
            original = found[0]
            require((original['issuer_cik'], original['cusip'], original['security_id']) == (cik, cusip, sid),
                'GOOG Class C must not be substituted for GOOGL Class A')
            title = original['security_class_cover']
            evidence = dict(type='SEALED_DATED_ADJUDICATION_NOT_EARLY_AVAILABILITY',
                dated_evidence=original, source_role='four')
        else:
            found = [row for row in seven['rows'] if row['ticker'] == ticker]
            require(len(found) == 1, 'Unique reused dated identity required')
            original = found[0]
            require((original['subject_cik'], original['cusip'], original['security_id']) == (cik, cusip, sid),
                'Original dated coordinate differs')
            title = original['security_class']
            evidence = dict(type='SEALED_DATED_FACTS_REUSED_WITH_NEW_EXPLICIT_WINDOW_ASSUMPTION',
                dated_evidence=original, original_conditional_window=seven['conditional_window'], source_role='seven')
        require(('Class C' in title if ticker == 'GOOG' else 'Class A' in title if ticker in ('GOOGL', 'BKR')
                 else 'common' in title.lower()), 'Share class conflicts with the dated coordinate')
        rows.append(dict(ticker=ticker, subject_cik=cik, cusip=cusip, issuer_id=f'issuer:{cik}',
            security_id=sid, security_class=title, evidence=evidence,
            continuous_interval_verified=False, provider_binding_verified=False, point_in_time_verified=False))
    by_sid = {row['security_id']: row for row in rows}
    schedule = documents['schedule']
    calendar = [day for day in schedule['calendar'] if '2023-03-31' <= day <= '2023-09-01']
    require(len(calendar) == 107 and calendar == sorted(set(calendar))
        and calendar[0] == '2023-03-31' and calendar[-1] == '2023-09-01',
        'Exact 107-session conditional calendar required')
    require([(row['decision_date'], row['execution_date']) for row in schedule['schedule']] == CLOCK
        and all(start in calendar and end in calendar and calendar.index(end) == calendar.index(start) + 1
                for start, end in CLOCK), 'Exact six next-observed-session decisions required')
    require(len(rows) == len(by_sid) == 8 and len({row['issuer_id'] for row in rows}) == 7,
        'Eight securities but seven distinct issuers required')
    union = set()
    require(len(schedule['schedule']) == 6, 'Complete six-decision target schedule required')
    for decision in schedule['schedule']:
        targets = decision['targets']
        require(set(targets) <= set(by_sid), 'Target lacks a factual coordinate')
        require(len({target['issuer_id'] for target in targets.values()}) == len(targets),
            'Multiple share classes of the same issuer in one decision')
        for sid, target in targets.items():
            require(all(target[key] == by_sid[sid][key] for key in ('ticker', 'issuer_id')), 'Target identity contradicts evidence')
        union.update(targets)
    require(union == set(by_sid), 'Exact full schedule security union required')
    return dict(schema='RETURN_EIGHT_CONDITIONAL_IDENTITY_ASSEMBLY_V1', rows=rows,
        security_count=8, distinct_issuer_count=7, conditional_window=dict(start='2023-03-31', end='2023-09-01'),
        interval_stability_assumption=ASSUMPTION, source_facts_reparsed=False,
        reuse_basis='HARD_PINNED_DATED_FACTS_AND_ALL_BOUND_BYTES_VERIFIED',
        goog_googl_relationship='DIFFERENT_SECURITY_IDS_SAME_ISSUER_NOT_A_RENAME',
        continuous_identity_interval_verified=False, provider_price_binding_verified=False,
        early_evidence_availability_inferred=False, historical_membership_verified=False,
        execution_performed=False, order_generation_allowed=False, point_in_time_verified=False, promotion_allowed=False)


def build():
    sources = dict(LOADED)
    documents = {}
    for role, (path, checksum) in BOUND.items():
        path = BASE / path
        raw = path.read_bytes()
        require(hashlib.sha256(raw).hexdigest() == checksum, 'Hard evidence SHA differs')
        archive.merge(sources, {str(path): checksum})
        documents[role] = json.loads(raw)
        for field in ('source_hashes', 'historical_expected_source_hashes'):
            if field in documents[role]:
                archive.merge(sources, documents[role][field])
    require(documents['linkage']['exact_schedule_reconstruction'] is True
        and documents['linkage']['schedule_reference'] == dict(path=str(BASE / BOUND['schedule'][0]), sha256=BOUND['schedule'][1]),
        'Independent schedule linkage differs')
    contract = archive.load_contract()
    archive.verify_expected_sources(sources, contract)
    value = assemble(documents)
    value.update(source_references={role: dict(path=str(BASE / path), sha256=checksum)
        for role, (path, checksum) in BOUND.items()}, historical_expected_source_hashes=sources,
        archive_resolution=archive.verify_expected_sources(sources, contract))
    return value


if __name__ == '__main__':
    value = build()
    output = BASE / 'return_eight_conditional_identity_20260923_v1/identities.json'
    contract = archive.load_contract()
    require(archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) == value['archive_resolution'],
        'Sources changed before publication')
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as handle:
        handle.write(raw)
        handle.flush()
        os.fsync(handle.fileno())
    require(archive.verify_expected_sources(value['historical_expected_source_hashes'], contract) == value['archive_resolution']
        and output.read_bytes() == raw, 'Published bytes or sources changed')
    print(json.dumps(dict(path=str(output), sha256=hashlib.sha256(raw).hexdigest())))
