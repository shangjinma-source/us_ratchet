import json
from scripts.build_candidate_forward_membership import build


def fixture(tmp_path,events):
    anchor=tmp_path/'anchor.json';queue=tmp_path/'events.json'
    anchor.write_text(json.dumps(dict(asof='2007-09-30',rows=[dict(candidate_historical_ticker=f'S{i}') for i in range(99)]+[dict(candidate_historical_ticker=None)])))
    queue.write_text(json.dumps(dict(events=events)))
    return anchor,queue


def event(day):
    return dict(date=day,review='PENDING',removed=['S0'],added=['NEW'])


def test_anchor_before_first_event_and_persistent_conflict(tmp_path):
    paths=fixture(tmp_path,[event('2007-12-04')]);result=build(*paths)
    assert len(result['monthly'])==15
    assert 'S0' in result['monthly'][0]['members']
    assert 'NEW' in result['monthly'][2]['members']
    assert all(len(m['members'])==100 and not m['admitted'] for m in result['monthly'])
    assert 'UNRESOLVED_SEC_NOVELLUS_NVDA' in result['monthly'][-1]['members']
    assert 'UNVERIFIED_EVENT:2007-12-04' in result['monthly'][-1]['blockers']


def test_invalid_event_order_and_compact_dates(tmp_path):
    for events in [[event('20071002')],[event('2008-01-02'),event('2007-12-04')],[event('2007-12-04'),event('2007-12-04')]]:
        try:build(*fixture(tmp_path,events))
        except ValueError:pass
        else:raise AssertionError('Invalid dates accepted')


def test_duplicate_anchor_cannot_collapse(tmp_path):
    paths=fixture(tmp_path,[]);source=json.loads(paths[0].read_text());source['rows'][1]=source['rows'][0];paths[0].write_text(json.dumps(source))
    try:build(*paths)
    except ValueError as error:assert str(error)=='ANCHOR_MUST_HAVE_100_DISTINCT_RECORDS'
    else:raise AssertionError('Duplicate anchor accepted')
