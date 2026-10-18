"""Two additional old-pool channels only; source capture and dependency locations."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib
import gzip
import json
from pathlib import Path
import sys
import pandas as pd
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.ndx_identity_source_probe import capture
from scripts.ndx_joint_weight_verify import _restore_input


def main():
    directory = ROOT / 'data/cache/research/legacy_pool_additional_split_probe_20260912_v1'
    directory.mkdir(exist_ok=True)
    if (directory / 'report.json').exists(): raise FileExistsError('Completed report exists')
    prior_path = ROOT / 'data/cache/research/root_return_semantics_probe_20260912_v1/root_return_semantics_review_20260912.json'
    prior_sha = 'a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b'
    assert hashlib.sha256(prior_path.read_bytes()).hexdigest() == prior_sha
    review = json.loads(prior_path.read_bytes())
    sources = dict(review['source_hashes']) | {str(prior_path): prior_sha}
    for relative in ('scripts/ndx_legacy_pool_additional_split_probe.py', 'scripts/ndx_identity_source_probe.py', 'scripts/ndx_joint_weight_verify.py'):
        path = ROOT / relative
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    def verify():
        for path, sha in sources.items(): assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha, path
    verify()
    contexts, universe = [], set()
    for location in review['actual_window_error_locations']:
        path, = [Path(p) for p, sha in sources.items() if sha == location['context_sha256'] and Path(p).name == 'context.json']
        context = json.loads(path.read_bytes())
        inputs = {key: _restore_input(value) for key, value in context['prepared_inputs'].items()}
        universe.update(inputs['universe'].ticker)
        contexts.append((location, inputs))
    assert {'FTNT', 'GOOGL'} <= universe
    now = datetime.now(timezone.utc)
    start = int(datetime(2022, 1, 1, tzinfo=timezone.utc).timestamp())
    requests = [dict(name='yahoo_' + ticker.lower(), method='GET', direct=False,
                    url=f'https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start}&period2={int(now.timestamp())}&interval=1d&events=div%2Csplits')
                for ticker in ('FTNT', 'GOOGL')]
    requests += [dict(name='sec_ftnt_split_8k', method='GET', direct=False,
                      url='https://www.sec.gov/Archives/edgar/data/1262039/000126203922000023/ftnt-20220622.htm'),
                 dict(name='sec_alphabet_all_class_split', method='GET', direct=False,
                      url='https://www.sec.gov/Archives/edgar/data/1652044/000165204422000068/googexhibit991q22022.htm')]
    probes, events, publication_facts = [], [], []
    for request in requests:
        path = directory / (request['name'] + '.response.bin')
        metadata_path = Path(str(path) + '.metadata.json')
        if path.exists():
            raw = path.read_bytes()
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_bytes())
            else:
                # The first interrupted run reached the UTF-8 decode after an HTTP-200
                # branch. Preserve its bytes; actual socket receipt time was not saved.
                saved = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
                metadata = dict(name=request['name'], http_status=200,
                    http_status_evidence='RECOVERED_FROM_PRIOR_RUN_REACHED_HTTP_200_BRANCH',
                    request_url_exact_not_recovered=True, requested_channel_url=request['url'].split('?')[0],
                    received_at_utc=None, response_saved_at_utc=saved,
                    transport_receipt_metadata_lost_on_prior_decode_exception=True)
        else:
            metadata, raw = capture(request)
            if raw is None: raise ValueError('No raw response')
            with path.open('xb') as handle: handle.write(raw)
        digest = hashlib.sha256(raw).hexdigest(); sources[str(path)] = digest
        metadata.update(response_path=str(path), response_sha256=digest, response_bytes=len(raw))
        if not metadata_path.exists():
            with metadata_path.open('x',encoding='utf8') as handle: json.dump(metadata,handle,indent=2,sort_keys=True)
        sources[str(metadata_path)] = hashlib.sha256(metadata_path.read_bytes()).hexdigest()
        probes.append(metadata)
        if metadata['http_status'] != 200: continue
        if request['name'].startswith('sec_'):
            body = gzip.decompress(raw) if raw[:2] == b'\x1f\x8b' else raw
            text = BeautifulSoup(body.decode('utf8'), 'html.parser').get_text(' ', strip=True)
            fragments = []
            for term in ('five-for-one', 'June 22, 2022', 'June 23, 2022', '20-for-one', 'Class A, Class B, and Class C'):
                pos = text.find(term)
                if pos >= 0: fragments.append({'term': term, 'surrounding_text': text[max(0,pos-80):pos+240]})
            publication_facts.append(dict(source_path=str(path), extracted_fragments=fragments,
                                          source_claims_not_provider_series_authentication=True))
            continue
        data, = json.loads(raw)['chart']['result']
        ticker = request['name'][6:].upper()
        assert data['meta']['symbol'] == ticker and data['meta']['currency'] == 'USD'
        days = [datetime.fromtimestamp(t, ZoneInfo('America/New_York')).date().isoformat() for t in data['timestamp']]
        assert days == sorted(set(days))
        received_day = datetime.fromisoformat(metadata.get('received_at_utc') or metadata['response_saved_at_utc']).astimezone(ZoneInfo('America/New_York')).date().isoformat()
        metadata['unfinalized_sessions'] = [day for day in days if day >= received_day]
        metadata['completed_session_count'] = sum(day < received_day for day in days)
        metadata['unfinalized_training_use_allowed'] = False
        close = data['indicators']['quote'][0]['close']
        root_path = ROOT / 'data/cache' / (ticker + '.csv')
        sources[str(root_path)] = hashlib.sha256(root_path.read_bytes()).hexdigest()
        old = pd.read_csv(root_path).set_index('Date').Close
        for split in data.get('events', {}).get('splits', {}).values():
            day = datetime.fromtimestamp(split['date'], ZoneInfo('America/New_York')).date().isoformat()
            index = days.index(day)
            if index == 0 or day >= received_day: continue
            previous = days[index - 1]
            assert previous in old and day in old
            locations = []
            for location, inputs in contexts:
                calendar = [d.date().isoformat() for d in inputs['returns'].index]
                contract = inputs['contract']; fit, width, step = [contract[k] for k in ('fit_days','window_days','step_days')]
                windows = []
                for ordinal, offset in enumerate(range(fit, len(calendar)-width+1, step)):
                    history, forward = calendar[offset-fit:offset], calendar[offset:offset+width]
                    if day in history or day in forward:
                        windows.append(dict(ordinal=ordinal, in_fit=day in history, in_forward=day in forward))
                locations.append(dict(coordinate=location['coordinate'], windows=windows,
                    candidate_universe_contains_ticker=ticker in set(inputs['universe'].ticker),
                    incumbent_weight=inputs['incumbent_weights'].get(ticker, 0.0)))
            events.append(dict(ticker=ticker, session=day, previous_session=previous,
                new_shares=split['numerator'], old_shares=split['denominator'],
                old_root_return=float(old.loc[day]/old.loc[previous]-1),
                provider_split_only_price_return=float(close[index]/close[index-1]-1),
                old_close_previous=float(old.loc[previous]), old_close=float(old.loc[day]),
                provider_close_previous=close[index-1], provider_close=close[index],
                raw_path=str(path), raw_sha256=digest, window_locations=locations))
    verify()
    previous_samples = {row['ticker'] for row in review['samples']}
    result = dict(schema='ndx_legacy_pool_additional_split_probe_v1', source_hashes=sources, probes=probes,
        old_fifteen_context_union=sorted(universe), old_pool_union_count=len(universe),
        previous_five_sample_tickers=sorted(previous_samples), previous_samples_in_pool=sorted(previous_samples & universe),
        new_provider_ticker_count=2, additional_tickers=['FTNT','GOOGL'],
        dedicated_semantics_probe_pool_coverage_count=len((previous_samples | {'FTNT','GOOGL'}) & universe),
        observed_split_events=events, official_document_fragments=publication_facts,
        remaining_unsampled_pool=sorted(universe - previous_samples - {'FTNT','GOOGL'}),
        scope='TWO_ADDITIONAL_OLD_POOL_SPLIT_COUNTEREXAMPLES_NOT_EXHAUSTIVE_EVENT_CERTIFICATE',
        goog_single_cell_delta_is_complete_data_repair=False, all_old_pool_events_verified=False,
        calendar_exchange_completeness_verified=False, provider_price_identity_verified=False,
        cache_modified=False, training_rerun=False, point_in_time_verified=False, promotion_allowed=False)
    path = directory / 'report.json'
    with path.open('x',encoding='utf8') as handle: json.dump(result,handle,indent=2,sort_keys=True);handle.write('\n')
    verify()
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        statuses=[p['http_status'] for p in probes],events=[{k:e[k] for k in ('ticker','session','old_root_return','provider_split_only_price_return')} for e in events])))


if __name__ == '__main__': main()
