from copy import deepcopy
from datetime import datetime,time,timezone
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zoneinfo import ZoneInfo
from core.strategy_account_ledger import canonical
from data.strategy_paper_application_descriptor_v2 import SCOPE,plan_future_start
from backtest.current_strategy_prospective_paper_book_v2 import create_book,transact,replay,CODE_PATHS as BOOK_PINS,SETTLEMENT_SCHEMA
from data.strategy_prospective_paper_selection_v2 import select_prospective_target,verify_prospective_target
from data.strategy_prospective_paper_source_daily_v2 import verify_prospective_daily
from data.strategy_prospective_paper_decision_v2 import produce_prospective_decision,ProspectiveTemporaryCaps,CODE_PATHS
import test_strategy_paper_application_descriptor_v1 as descriptor_fixture
from test_strategy_paper_daily_signal_v1 import setup
from test_strategy_paper_execution_preview_v1 import capture

ROOT=Path(__file__).resolve().parents[1]


def fixture(folder,monthly_price='1000',extra_code_paths=(),extra_sources=None,extra_sessions=(),integration_review_sha256='a'*64):
    old=setup(folder)
    calendar=json.loads(old['calendar_bytes'])
    calendar['sessions'].extend(deepcopy(extra_sessions))
    for row in calendar['sessions']:
        day=datetime.fromisoformat(row['date']).date()
        for field,hour,minute in [('open',9,30),('close',16,0)]:
            row[field]=datetime.combine(day,time(hour,minute),ZoneInfo('America/New_York')).astimezone(timezone.utc).isoformat()
    cal=canonical(calendar);calhash=sha256(cal).hexdigest()
    release=json.loads(old['release_bytes']);release['calendar_sha256']=calhash
    f=descriptor_fixture.DescriptorTests();f.setUp();app=deepcopy(f.app)
    app['schema']='CURRENT_STRATEGY_PAPER_APPLICATION_DESCRIPTOR_V2'
    app['scope']=SCOPE
    app['ledger_schema']='CURRENT_STRATEGY_PROSPECTIVE_PAPER_BOOK_V2'
    app['policy']['daily_rule']='MONTHLY_CAP50_EXIT20'
    app['calendar_sha256']=calhash
    app['plan']=plan_future_start(calendar_bytes=cal,calendar_sha256=calhash,now='2026-11-03T14:58:00+00:00',terminal_date=calendar['sessions'][-1]['date'])
    app['policy']['fee_bps']='0'
    codes={p:(ROOT/p).read_bytes() for p in CODE_PATHS|BOOK_PINS|set(extra_code_paths)}
    sources={'policy/daily.json':canonical(release)}
    sources.update(extra_sources or {})
    app['code_sha256']={p:sha256(raw).hexdigest() for p,raw in codes.items()}
    app['source_sha256']={p:sha256(raw).hexdigest() for p,raw in sources.items()}
    raw=canonical(app);desc_hash=sha256(raw).hexdigest()
    approval=canonical(dict(schema='PAPER_APPLICATION_REVIEW_V1',scope=SCOPE,descriptor_sha256=desc_hash,approved=True,
        reviewed_at='2026-11-03T14:58:30+00:00',review_role='IMPLEMENTATION_REVIEW_OF_USER_AUTHORIZED_PAPER_SCOPE',
        authorization_basis='TEMPORARY SYNTHETIC INTEGRATION TEST ONLY'))
    registration=canonical(dict(schema='PROSPECTIVE_PAPER_REGISTRATION_V1',scope=SCOPE,descriptor_sha256=desc_hash,
        account_id=app['account_id'],simulation_id=app['simulation_id'],registered_at='2026-11-03T14:59:00+00:00',
        first_session=app['plan']['first_session'],terminal_session=app['plan']['terminal_session'],integration_review_sha256=integration_review_sha256))
    authority=dict(descriptor_arguments=dict(descriptor_bytes=raw,trusted_descriptor_sha256=desc_hash,
        approval_bytes=approval,trusted_approval_sha256=sha256(approval).hexdigest(),calendar_bytes=cal,code_bytes=codes,source_bytes=sources),
        registration_bytes=registration,trusted_registration_sha256=sha256(registration).hexdigest(),trusted_integration_review_sha256=integration_review_sha256)
    book=create_book(authority=authority,clock=lambda:datetime.fromisoformat('2026-11-03T15:00:00+00:00'));admitted={}
    package=deepcopy(old['selection_arguments']['source_package']);selection_at='2026-11-03T15:00:01+00:00'
    def put(path,value):
        raw=canonical(value);package['files'][path]=raw;package['source_hashes'][path]=sha256(raw).hexdigest()
    marks=json.loads(package['files']['marks.paper.json'])
    for mark in marks.values():mark.update(observed_at=selection_at,price=monthly_price)
    put('marks.paper.json',marks)
    units=json.loads(package['files']['review.paper.json']);units.update(account_revision=book['revision'],reviewed_at=selection_at,
        marks_sha256=package['source_hashes']['marks.paper.json'])
    for sid,unit in units['securities'].items():
        unit.update(current_mark_sha256=sha256(canonical(marks[sid])).hexdigest(),covered_through=selection_at)
    put('review.paper.json',units)
    for p,raw in codes.items():package['files'][p]=raw;package['source_hashes'][p]=sha256(raw).hexdigest()
    review=canonical(dict(schema='PROSPECTIVE_PAPER_SOURCE_ADMISSION_V1',scope=SCOPE,descriptor_sha256=desc_hash,
        account_id=book['account_id'],account_revision=book['revision'],source_sha256=package['source_hashes'],
        available_at=selection_at,source_authenticated=False,coverage_complete=False))
    selection_args=dict(book=book,authority=authority,admitted_decisions=admitted,source_review_bytes=review,
        trusted_source_review_sha256=sha256(review).hexdigest(),source_package=package,manifest_path='manifest.json',
        marks_path='marks.paper.json',unit_review_path='review.paper.json',now=selection_at,maximum_mark_age_seconds=120)
    selected=select_prospective_target(clock=lambda:selection_at,**selection_args)
    inputs=json.loads(old['files']['normalized.json']);inputs['base_target']['origin_reference']=selected['decision_id']
    inputs['base_target']['quantities']=selected['payload']['target_quantities']
    rows={r['date']:r for r in calendar['sessions']}
    inputs['session_close_times']['closes']={day:rows[day]['close'] for day in inputs['session_dates']}
    for history in inputs['histories'].values():
        for row in history['closes']:row['completed_at']=rows[row['date']]['close']
    files=deepcopy(old['files']);files['normalized.json']=canonical(inputs)
    receipt=json.loads(old['receipt_bytes']);receipt.update(account_id=book['account_id'],account_revision=book['revision'],
        target_id=selected['decision_id'],release_sha256=app['source_sha256']['policy/daily.json'],available_at='2026-11-03T15:00:02+00:00',
        valid_from='2026-11-03T15:00:02+00:00',source_sha256={p:sha256(raw).hexdigest() for p,raw in files.items()})
    daily=dict(book=book,authority=authority,admitted_decisions=admitted,selection_result=selected,selection_arguments=selection_args,
        now='2026-11-03T15:00:10+00:00',release_path='policy/daily.json',receipt_bytes=canonical(receipt),
        trusted_receipt_sha256=sha256(canonical(receipt)).hexdigest(),files=files)
    return daily

