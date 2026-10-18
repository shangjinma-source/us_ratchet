"""Bounded saved-original split fact readback; no prices or old events changed.

Run with the bundled Python containing pypdf. Receipt dates are not PIT dates.
"""
import csv
from datetime import date
from fractions import Fraction
import gzip
import hashlib
import html
import io
import json
from pathlib import Path
import re
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'tmp/historical_split_registry_diagnostic_20261014_v1'
FACT = 'data/cache/research/standard_split_official_evidence_20260912_v1/specific_split_fact_readback.json'
OLD = 'data/cache/candidate_pools/ndx_fundamentals/price_basis_v2/split_events.csv'
GOOG = 'data/cache/research/root_return_semantics_probe_20260912_v1/'
LEGACY = 'data/cache/research/legacy_pool_additional_split_probe_20260912_v1/'
TTD = 'data/cache/candidate_pools/ndx_taxonomy_v2/raw_sec/issuer_0001671933/000167193324000014/ttd-20231231.htm'


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def main():
    assert not OUT.exists(), 'Create-only diagnostic'
    hashes = {}
    def read(path, expected=None):
        path = Path(path)
        if not path.is_absolute(): path = ROOT/path
        raw = path.read_bytes(); actual = digest(raw)
        assert expected is None or actual == expected, str(path)
        hashes[path.relative_to(ROOT).as_posix()] = actual
        return raw
    def text(path, expected):
        raw = read(path, expected)
        if raw[:2] == b'\x1f\x8b': raw = gzip.decompress(raw)
        if raw.startswith(b'%PDF'):
            result = ' '.join(page.extract_text() for page in PdfReader(io.BytesIO(raw)).pages)
        else:
            result = html.unescape(re.sub('<[^>]+>', ' ', raw.decode('utf-8')))
        return re.sub(r'\s+', ' ', result)
    def evidence(path, expected, needles):
        content = text(path, expected)
        normalized = re.sub(r'\s*-\s*', '-', content).lower()
        for needle in needles: assert needle.lower() in normalized, (path, needle)
        excerpts = []
        for needle in needles:
            index = normalized.index(needle.lower())
            excerpts.append(normalized[max(0,index-70):index+len(needle)+150])
        return dict(path=str(path), sha256=expected, required_original_phrases=needles,
                    original_text_excerpt=excerpts, original_text_checks_passed=True)
    facts = json.loads(read(FACT)); events = []
    for row in facts['specific_events']:
        ratio = f"{row['new_shares']} for {row['old_shares']}"
        day = date.fromisoformat(row['first_adjusted_trading_date'])
        date_text = f'{day.strftime("%B")} {day.day}, {day.year}'
        if row['document_role']=='CLEARING_MEMO_HOSTED_BY_EXCHANGE':
            needles = [ratio+' stock split', 'ex-distribution date is '+date_text, row['cusip']]
        else:
            needles = ['three-for-one', 'split-adjusted basis on '+date_text]
        proof = evidence(row['raw_path'], row['raw_sha256'], needles)
        events.append(dict(ticker=row['ticker'], event_date=row['first_adjusted_trading_date'],
            new_shares=row['new_shares'], old_shares=row['old_shares'],
            factor=str(Fraction(row['new_shares'],row['old_shares'])),
            status='SPECIFIC_EVENT_OFFICIAL_OR_EXCHANGE_HOSTED_ORIGINAL_SUPPORTED',
            source_role=row['document_role'], evidence=[proof],
            evidence_received_at=row.get('received_at_utc'),
            authority_limit='CLEARING_SUMMARY_NOT_ISSUER_FILING' if 'CLEARING' in row['document_role'] else 'SPECIFIC_ISSUER_EVENT_ONLY',
            conditional_unit_conversion_event=True))
    review = json.loads(read(GOOG+'goog_split_primary_review_20260912.json'))
    refhash = {Path(path).name: value for path,value in review['source_hashes'].items()}
    approved = evidence(GOOG+'sec_goog_split_approved_2022.response.bin', refhash['sec_goog_split_approved_2022.response.bin'],
                        ['20-for-one', 'class a', 'class c', 'split-adjusted basis on July 18, 2022'])
    executed = evidence(GOOG+'sec_goog_split_executed_2022.response.bin', refhash['sec_goog_split_executed_2022.response.bin'],
                        ['On July 15, 2022, the company executed a 20-for-one stock split', 'Class A, Class B, and Class C'])
    for ticker in ('GOOG','GOOGL'):
        events.append(dict(ticker=ticker,event_date='2022-07-18',new_shares=20,old_shares=1,factor='20',
                           status='SPECIFIC_ISSUER_EVENT_ORIGINAL_SUPPORTED',evidence=[approved,executed],
                           conditional_unit_conversion_event=True))
    manifest = json.loads(read(TTD+'.manifest.json'))
    proof = evidence(TTD, manifest['content_sha256'], ['ten-for-one stock split', 'split-adjusted basis on June 17, 2021'])
    events.append(dict(ticker='TTD',event_date='2021-06-17',new_shares=10,old_shares=1,factor='10',
                       status='SPECIFIC_ISSUER_EVENT_ORIGINAL_SUPPORTED',evidence=[proof],
                       conditional_unit_conversion_event=True, outside_requested_window=True))
    meta = json.loads(read(LEGACY+'sec_ftnt_split_8k.response.bin.metadata.json'))
    proof = evidence(LEGACY+'sec_ftnt_split_8k.response.bin', meta['response_sha256'],
                     ['five-for-one forward stock split', 'multiplied by five'])
    # The filing proves the ratio but does not state June23 as the first trading
    # day. Preserve the provider-only date corroboration rather than upgrading it.
    provider_meta = json.loads(read(LEGACY+'yahoo_ftnt.response.bin.metadata.json'))
    raw = read(LEGACY+'yahoo_ftnt.response.bin',provider_meta['response_sha256'])
    if raw[:2]==b'\x1f\x8b':raw=gzip.decompress(raw)
    channel = json.loads(raw)['chart']['result'][0]
    from datetime import datetime, timezone
    observed = [event for event in channel['events']['splits'].values()
                if datetime.fromtimestamp(event['date'],timezone.utc).date().isoformat()=='2022-06-23']
    assert len(observed)==1 and Fraction(str(observed[0]['numerator']))/Fraction(str(observed[0]['denominator']))==5
    events.append(dict(ticker='FTNT',event_date='2022-06-23',new_shares=5,old_shares=1,factor='5',
                       status='OFFICIAL_RATIO_PROVIDER_DATE_ONLY', evidence=[proof], provider_event=observed[0],
                       provider_raw_path=LEGACY+'yahoo_ftnt.response.bin',
                       official_first_trading_date_verified=False, conditional_unit_conversion_event=False,
                       gap='First adjusted trading date needs explicit official corroboration; ratio is supported'))
    old = list(csv.DictReader(io.StringIO(read(OLD).decode('utf-8-sig'))))
    assert len(old)==17
    lookup = {(row['ticker'],row['event_date']): row for row in events}
    comparison = []
    for inferred in old:
        official = lookup.get((inferred['ticker'],inferred['event_date']))
        status = ('UNVERIFIED_IN_BOUNDED_SAVED_SOURCE_REVIEW' if official is None else
                  'CONFLICT_WITH_OFFICIAL_RATIO' if Fraction(inferred['split_factor'])!=Fraction(official['factor']) else
                  'RATIO_MATCH_DATE_NOT_OFFICIALLY_VERIFIED' if not official['conditional_unit_conversion_event'] else
                  'MATCH_WITH_SPECIFIC_ORIGINAL_EVENT')
        comparison.append(dict(inferred=inferred,diagnostic_status=status,
            in_requested_window='2022-03-01'<=inferred['event_date']<='2024-07-31',
            explicit_event=official, inferred_ratio_is_not_conversion_authority=True))
    additions = [row for row in events if (row['ticker'],row['event_date']) not in {(x['ticker'],x['event_date']) for x in old}]
    assert any(row['ticker']=='PCAR' and row['factor']=='3/2' for row in additions)
    explicit = [row for row in events if row['conditional_unit_conversion_event'] and '2022-03-01'<=row['event_date']<='2024-07-31']
    result = dict(status='COMPLETE_BOUNDED_SAVED_ORIGINAL_SPLIT_DIAGNOSTIC',
        scope_start='2022-03-01',scope_end='2024-07-31',comparison_all_17_inferred_events=comparison,
        explicit_conditional_event_table=explicit, omitted_from_inferred_csv=additions,
        outside_scope_correction=[row for row in events if row.get('outside_requested_window')],
        unresolved_event_candidates=[row for row in events if not row['conditional_unit_conversion_event']],
        source_hashes=hashes, script_sha256=digest(Path(__file__).read_bytes()),
        gaps=['Five 2021 inferred events have not been individually verified in this bounded source review',
              'This is not an exhaustive all-issuer corporate-action registry; later omitted events still need coverage audit',
              'FTNT ratio5 is official but June23 first adjusted trading day is provider-only here',
              'Event truth does not establish each provider OHLC/volume adjustment basis, dividend total return, or PIT receipt',
              'PCAR fractional-share cash-in-lieu and nominal-share bookkeeping are not resolved by the 3/2 factor'],
        conversion_formula='For known nominal pre-event quote unit: divide OHLC by new/old; multiply share units by new/old. Never apply to already adjusted series.',
        conversion_applied=False, old_split_csv_modified=False, price_panel_modified=False,
        formal_pit_verified=False,evidence_available_at_inferred=False,global_price_basis_certified=False,
        strategy_runs=0,book_calls=0,network_calls=0)
    for path, expected in hashes.items():assert digest((ROOT/path).read_bytes())==expected
    OUT.mkdir()
    for name,value in [('result.json',result),('explicit_conditional_events.json',explicit)]:
        raw=json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False).encode('utf-8')
        with (OUT/name).open('xb') as stream:stream.write(raw)
        print(name,digest(raw))


if __name__=='__main__':main()
