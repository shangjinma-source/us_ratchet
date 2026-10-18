"""Single offline whole-raw alignment for the new observation; no qualification."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from data.current_research_ohlc_panel import parse_provider_ohlc,bind_ohlc_panel
from data.current_research_close_panel import FALSE_FLAGS

BASE='data/cache/research/current_raw_capture_20261014_v1'
OUTPUT=ROOT/'tmp/current_ohlc_actual_projection_20261014_v1'
PINS={
 BASE+'/completion_index_104.json':'6c4edd3fa4d6288e3bdebe8a042f7d96abf13cc1dc91e31d3a6c992e442cc767',
 'tmp/current104_capture_continuation_20261014_v1/raw_readback.json':'6c2e15192894a831d5fd410aa0f7cc0a263453e88b1e170d943e58473f9fe9b6',
 'data/cache/research/current_quote_list_observation_20261013_v1/observation.json':'41573c3b20f683f1565e969be689d1eac52b4d1b4fb0d29d8c5b9c477e371fbf',
 'data/current_research_ohlc_panel.py':'c9eed4d223c33a8edbdd1f425eff80079ded57cc55f69386d58f696d45b8e1f0',
 'data/current_research_close_panel.py':'5ebacf528557a869b28b532b79852964b0ed6d1865c553626618284b34c3841d',
}


def save(name,value):
    raw=json.dumps(value,indent=2,allow_nan=False).encode('utf-8')
    with (OUTPUT/name).open('xb') as f:f.write(raw)
    return hashlib.sha256(raw).hexdigest()


def prepare():
    if OUTPUT.exists():raise ValueError('Create-only output already exists')
    pins={}
    def read(name,expected):
        raw=(ROOT/name).read_bytes();h=hashlib.sha256(raw).hexdigest()
        if h!=expected:raise ValueError('Source hash differs: '+name)
        pins[name]=h
        return raw
    docs={name:json.loads(read(name,h)) if name.endswith('.json') else read(name,h) for name,h in PINS.items()}
    index=docs[BASE+'/completion_index_104.json']
    audit=docs['tmp/current104_capture_continuation_20261014_v1/raw_readback.json']
    observation=docs['data/cache/research/current_quote_list_observation_20261013_v1/observation.json']
    names=observation['observed_symbols'];controls=['TSM','QQQ','SPY'];queue=names+controls
    if len(names)!=101 or len(set(queue))!=104 or index['queue']!=queue or index['target_date']!='2026-10-13':raise ValueError('Explicit101+3scope differs')
    if audit['channels']!=104 or audit['target_session']!='2026-10-13':raise ValueError('Readback scope differs')
    checked={r['ticker']:r['raw_sha256'] for r in audit['rows']}
    raws={}
    for entry in index['entries']:
        t=entry['ticker'];receipt=json.loads(read(BASE+'/'+t+'.receipt.json',entry['receipt_sha256']))
        read(BASE+'/'+t+'.decoded.json',entry['decoded_sha256'])
        read(BASE+'/'+t+'.started.json',receipt['started_sha256'])
        if entry['raw_sha256']!=checked[t] or receipt['raw_sha256']!=checked[t]:raise ValueError('Raw readback mismatch')
        raws[t]=read(BASE+'/'+t+'.response.bin',entry['raw_sha256'])
    if set(raws)!=set(queue):raise ValueError('Full channel set required')
    pins[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    OUTPUT.mkdir()
    save('registration.json',dict(status='REGISTERED_BEFORE_OFFLINE_ALIGNMENT',target='2026-10-13',source_hashes=pins,
        stocks=101,controls=controls,maximum_extractions=1,network_calls=0,search_calls=0,book_calls=0,
        qualification_inherited=False,old_identity_or_risk_intervals_extended=False,**FALSE_FLAGS))
    channels={t:parse_provider_ohlc(raw,t) for t,raw in raws.items()}
    calendar=[d for d in channels['QQQ']['dates'] if d<='2026-10-13']
    if calendar[-1]!='2026-10-13':raise ValueError('Target absent from QQQ timeline')
    def close_row(t):
        data=dict(zip(channels[t]['dates'],channels[t]['values']))
        return dict(ticker=t,raw_close=[data[d][3] if d in data else None for d in calendar])
    association=dict(target='2026-10-13',calendar=calendar,stocks=[close_row(t) for t in names],controls=[close_row(t) for t in controls],**FALSE_FLAGS)
    panel=bind_ohlc_panel(sealed_close=association,channels=channels)
    panel.update(source_hashes=pins,calendar_source='QQQ_PROVIDER_OBSERVED_SESSIONS_NOT_EXCHANGE_CERTIFIED',
        close_association_scope='NEW_RAW_QUOTE_CLOSE_ALIGNMENT_ONLY_NO_OLD_SEALED_CLOSE_OR_QUALIFICATION_INHERITED',
        whole_source_capture=BASE,prior_membership_observation_reused=True,current_membership_revalidated=False,
        network_calls=0,search_calls=0,book_calls=0,production_adoption=False)
    for name,h in pins.items():read(name,h)
    panel_sha=save('panel.json',panel)
    coverage=dict(panel_sha256=panel_sha,target=panel['target'],sessions=len(calendar),first_session=calendar[0],
        stocks=len(panel['stocks']),controls=controls,
        rows=[dict(ticker=r['ticker'],missing_field_counts=r['missing_field_counts'],missing_provider_dates=r['missing_provider_dates'],
                   target_ohlcv=r['values'][-1],excluded_future_dates=r['excluded_future_dates']) for r in panel['stocks']+panel['controls']],
        no_missing_fill=True,no_old_panel_mutation=True,network_calls=0,search_calls=0,source_hashes=pins,**FALSE_FLAGS)
    save('coverage.json',coverage)
    print(json.dumps(dict(panel_sha256=panel_sha,sessions=len(calendar),stocks=101,controls=controls,missing_ohlcv=sum(sum(r['missing_field_counts'].values()) for r in coverage['rows']))))


if __name__=='__main__':prepare()
