"""Two specific complex-action facts and raw-provider omissions; no price repair."""
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT/'data/cache/research'
SOURCE = Path(__file__).resolve()
LOADED = hashlib.sha256(SOURCE.read_bytes()).hexdigest()
MIRROR = BASE/'current_complex_completion_mirror_capture_20260919_v1/manifest.json'
MIRROR_SHA = 'aa3794341d5a7142a95a712d032191589c06cd02ca0340c4ec93dec107dadad4'
PRIMARY = BASE/'current_complex_completion_capture_20260919_v1/manifest.json'
PRIMARY_SHA = '6af372c096fa616cbebe7d419aeb66e3351b2894f08ffaed79e2ed5dc1147ed9'
PLAN = BASE/'current101_conditional_prices_20260919_v1/plan.json'
PLAN_SHA = '5e3fc9d87dd180d458265bf256e55c04b51da3b9c74be2a58a187beb6e99daf0'
OUTPUT = BASE/'current_complex_completion_readback_20260919_v1/report.json'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def extract(cmcsa, tri_announcement, tri_completed):
    requirements = (
        (cmcsa, ('January 5, 2026', 'completion of its previously announced separation',
                  '11:59 p.m. Eastern Time on January 2, 2026',
                  'Versant will commence regular-way trading today on Nasdaq',
                  'for every 25 shares of Comcast', 'Comcast Corporation (NASDAQ: CMCSA)')),
        (tri_announcement, ('May 1, 2026', 'markets open on May 4, 2026',
                            '884903881', 'CA8849038812', '0.984560 post-consolidated shares')),
        (tri_completed, ('May 5, 2026', 'On May 4, 2026, the company returned $605 million',
                         '$1.435518 per participating common share',
                         '0.984560 post-consolidated shares')))
    for text, phrases in requirements:
        if any(phrase not in text for phrase in phrases):
            raise ValueError('Required specific dated completion/announcement fact absent')
    return [dict(ticker='CMCSA', action_kind='SPINOFF_COMPLETED', completion_date='2026-01-02',
                 completion_time='23:59:00 America/New_York', first_post_action_session_candidate='2026-01-05',
                 distribution_child_ticker='VSNT', child_shares_per_parent_share='1/25',
                 post_action_cusip=None, parent_split_ratio_not_inferred_from_distribution=True),
            dict(ticker='TRI', action_kind='CASH_RETURN_AND_CONSOLIDATION_COMPLETED',
                 completion_date='2026-05-04', first_post_action_session_candidate='2026-05-04',
                 announced_post_action_cusip='884903881', announced_post_action_isin='CA8849038812',
                 declared_consolidation_ratio='0.984560', participating_cash_per_share_usd='1.435518',
                 opt_out_accounting_not_modeled=True, uniform_holder_economic_action_assumed=False)]


def build():
    sources = {str(SOURCE): LOADED}
    def read(path, expected):
        raw = Path(path).read_bytes()
        if sha(raw) != expected:
            raise ValueError('Hard evidence changed: '+str(path))
        if str(path) in sources and sources[str(path)] != expected:
            raise ValueError('Conflicting source')
        sources[str(path)] = expected
        return raw
    mirror = json.loads(read(MIRROR, MIRROR_SHA))
    primary = json.loads(read(PRIMARY, PRIMARY_SHA))
    texts = {}
    witnesses = {}
    for manifest in (mirror, primary):
        for path, digest in manifest['source_hashes'].items():
            read(path, digest)
        for capture in manifest['captures']:
            if capture['name'] not in ('cmcsa_completion_filing_mirror', 'tri_completion_filing_mirror', 'tri_2026_ratio'):
                continue
            if capture['http_status'] != 200:
                raise ValueError('Successful dated document required')
            raw = read(capture['raw_path'], capture['raw_sha256'])
            decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            if sha(decoded) != capture['decoded_sha256']:
                raise ValueError('Decoded document differs')
            text = ' '.join(BeautifulSoup(decoded.decode('utf-8-sig'), 'html.parser').get_text(' ', strip=True).split())
            texts[capture['name']] = text
            witnesses[capture['name']] = dict(raw_path=capture['raw_path'], raw_sha256=capture['raw_sha256'],
                request_url=capture['request_url'], received_at_utc=capture['received_at_utc'],
                normalized_text_sha256=sha(text.encode()), mirror_not_sec_origin_http='mirror' in capture['name'])
    rows = extract(texts['cmcsa_completion_filing_mirror'], texts['tri_2026_ratio'], texts['tri_completion_filing_mirror'])
    plan = json.loads(read(PLAN, PLAN_SHA))
    for row in rows:
        task, = [t for t in plan['tasks'] if t['ticker'] == row['ticker']]
        if task['mode'] != 'BLOCKED_COMPLEX_OR_IDENTITY':
            raise ValueError('Original complex guard must remain blocked')
        raw = read(task['raw_path'], task['raw_sha256'])
        decoded = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
        body = json.loads(decoded)['chart']['result'][0]
        if body['meta']['symbol'] != row['ticker']:
            raise ValueError('Provider ticker differs')
        events = [dict(event, session=datetime.fromtimestamp(event['date'], timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat())
                  for event in body.get('events', {}).get('splits', {}).values()]
        row.update(provider_raw_path=task['raw_path'], provider_raw_sha256=task['raw_sha256'],
                   all_returned_split_events=events,
                   specific_boundary_in_returned_events=any(e['session'] == row['first_post_action_session_candidate'] for e in events),
                   complex_event_is_ordinary_split=False, provider_raw_rewritten=False,
                   historical_price_repair_performed=False, conditional_post_action_quote_implemented=False,
                   provider_price_identity_bound=False, point_in_time_verified=False)
    report = dict(schema='TWO_COMPLEX_COMPLETION_AND_PROVIDER_OMISSION_FACTS_V1', rows=rows,
                  document_witnesses=witnesses, source_hashes=sources,
                  all_company_actions_covered=False, historical_membership_verified=False,
                  original_complex_guard_unchanged=True, quote_reconstruction_performed=False,
                  point_in_time_verified=False, promotion_allowed=False)
    verify(report)
    return report


def verify(report):
    for path, expected in report['source_hashes'].items():
        if sha(Path(path).read_bytes()) != expected:
            raise ValueError('Source changed during readback')


if __name__ == '__main__':
    report = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=False)
    with OUTPUT.open('x', encoding='utf8') as stream:
        json.dump(report, stream, sort_keys=True, indent=2)
        stream.write('\n')
    verify(report)
    print(json.dumps(dict(path=str(OUTPUT), sha256=sha(OUTPUT.read_bytes()))))
