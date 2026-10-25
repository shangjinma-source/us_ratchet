from datetime import date, timedelta
import hashlib
from scripts.audit_bull_bear_history_inputs import audit


def sample(tmp_path):
    source = tmp_path / 'source'
    source.write_bytes(b'evidence fixture')
    days = [(date(2020, 1, 1)+timedelta(days=i)).isoformat() for i in range(253)]
    interval = dict(ticker='OLD', start=days[0], end=days[-1], source='source')
    return dict(sessions=days, decisions=[days[-1]], memberships=[interval],
                identities=[dict(interval, security_id='sid')],
                sources={'source': hashlib.sha256(source.read_bytes()).hexdigest()},
                prices={'sid': dict(source='source', basis='HISTORICAL_NOMINAL',
                    rows={d: dict(open='1', high='2', low='1', close='2') for d in days})})


def test_complete_structure_does_not_certify_calendar_or_admit(tmp_path):
    result = audit(sample(tmp_path), tmp_path)
    assert result['structural_coverage_pass']
    assert result['status'] == 'NOT_ADMITTED'


def test_missing_delisted_member_is_not_dropped(tmp_path):
    manifest = sample(tmp_path)
    manifest['prices'].clear()
    result = audit(manifest, tmp_path)
    assert result['member_counts'][0]['distinct_tickers'] == 1
    assert result['issues'][0]['code'] == 'MISSING_PRICE_SECURITY'


def test_alias_overlap_and_adjusted_prices_block(tmp_path):
    manifest = sample(tmp_path)
    manifest['identities'].append(dict(manifest['identities'][0]))
    assert any(i['code'] == 'MISSING_OR_OVERLAPPING_IDENTITY' for i in audit(manifest, tmp_path)['issues'])
    manifest['identities'].pop()
    manifest['prices']['sid']['basis'] = 'SPLIT_ADJUSTED'
    assert any(i['code'] == 'UNREVIEWED_PRICE_BASIS' for i in audit(manifest, tmp_path)['issues'])


def test_missing_session_and_changed_source_block(tmp_path):
    manifest = sample(tmp_path)
    del manifest['prices']['sid']['rows'][manifest['sessions'][10]]
    (tmp_path / 'source').write_bytes(b'changed')
    codes = {i['code'] for i in audit(manifest, tmp_path)['issues']}
    assert {'SOURCE_MISSING_OR_CHANGED', 'MISSING_OR_INVALID_TRAINING_BARS'} <= codes


def test_empty_scope_never_passes(tmp_path):
    for field in ('sessions', 'decisions', 'memberships'):
        manifest = sample(tmp_path)
        manifest[field] = []
        result = audit(manifest, tmp_path)
        assert not result['structural_coverage_pass']
        assert any(i['code'] == 'EMPTY_RESEARCH_SCOPE' for i in result['issues'])
