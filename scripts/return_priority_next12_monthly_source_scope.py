"""Read-only next-period membership and numeric coverage; no strategy inputs."""
import csv,gzip,hashlib,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
ROOT=Path(__file__).resolve().parents[1]
OUTPUT=ROOT/'tmp/next12_monthly_source_scope_20261014_v1.json'

def prepare():
    pins={}
    def read(path,expected=None):
        raw=(ROOT/path).read_bytes();sha=hashlib.sha256(raw).hexdigest()
        if expected and sha!=expected:raise ValueError('SOURCE_CHANGED:'+path)
        pins[path]=sha;return raw
    def table(path):
        manifest=json.loads(read(path+'.manifest.json'));rows=list(csv.DictReader(read(path,manifest['content_sha256']).decode('utf-8-sig').splitlines()))
        if len(rows)!=manifest['row_count']:raise ValueError('ROW_COUNT_MISMATCH')
        return rows
    base='data/cache/candidate_pools/ndx_history/'
    events=table(base+'exact_events/exact_events.csv');history=table(base+'qqq_nport_constituents.csv')
    identities=table('data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv')
    anchor_path='tmp/fixed12_data_coverage_20261014_v3/coverage.json';anchor=json.loads(read(anchor_path))['windows'][-1]
    panelpath='tmp/current_ohlc_actual_projection_20261014_v1/panel.json';panel=json.loads(read(panelpath));calendar=panel['calendar']
    trainpath='tmp/fixed12_training_prepare_20261014_v6/prepared.json';training=json.loads(read(trainpath))
    sources={};cache={};source_events={};source_meta={}
    for row in panel['stocks']:
        sources.setdefault(row['ticker'],[]).append(panelpath)
        cache[(row['ticker'],panelpath)]={d:r[:4] for d,r in zip(calendar,row['values'])}
    for window in training['windows']:
        for row in window['candidates']:
            path=row.get('training_source')
            if path and path not in sources.setdefault(row['ticker'],[]):sources[row['ticker']].append(path)
    insm='data/cache/research/ndx_v11_current_price_basis_v1/raw/INSM.csv'
    manifest=json.loads(read(insm+'.manifest.json'))
    read(insm,manifest['content_sha256'])
    sources.setdefault('INSM',[]).append(insm)
    def prices(ticker,path):
        key=(ticker,path)
        if key in cache:return cache[key]
        raw=read(path,training['source_hashes'].get(path))
        if path.endswith('.csv'):
            rows=list(csv.DictReader(raw.decode('utf-8-sig').splitlines()));cache[key]={r['Date']:[r[k] for k in ['Open','High','Low','Close']] for r in rows};source_events[key]=[]
        else:
            channel=json.loads(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw)['chart']['result'][0]
            if channel['meta']['symbol']!=ticker:raise ValueError('SYMBOL_MISMATCH')
            zone=ZoneInfo(channel['meta']['exchangeTimezoneName']);day=lambda t:datetime.fromtimestamp(t,zone).date().isoformat();q=channel['indicators']['quote'][0]
            cache[key]={day(t):[q[k][i] for k in ['open','high','low','close']] for i,t in enumerate(channel['timestamp'])}
            source_events[key]=[dict(kind=k,date=day(e['date']),payload=e) for k,records in channel.get('events',{}).items() for e in records.values() if k!='dividends']
        return cache[key]
    def apply(members,after,cutoff):
        result=set(members);issues=[];applied=[]
        for event in sorted(events,key=lambda e:(e['effective_date'],e['event_id'],e['action'],e['ticker'])):
            if not(after<event['effective_date']<=cutoff and event['announcement_date']<=cutoff and event['source_available_date']<=cutoff):continue
            if event['action'] not in ('add','remove'):continue
            if not all(event[k]=='True' for k in ['source_verified','source_manifest_verified','future_data_guard']):issues.append(event);continue
            read(base+'exact_events/'+event['raw_path'],event['content_sha256']);ticker=event['ticker']
            if event['action']=='add':
                if ticker in result:issues.append(dict(reason='ALREADY_PRESENT',event=event))
                result.add(ticker)
            else:
                if ticker not in result:issues.append(dict(reason='REMOVAL_ABSENT',event=event))
                result.discard(ticker)
            applied.append(event)
        return result,issues,applied
    months=[f'2025-{m:02d}' for m in range(7,13)]+[f'2026-{m:02d}' for m in range(1,7)]
    decisions=[max(d for d in calendar if d.startswith(month)) for month in months];windows=[]
    for decision in decisions:
        chain,issues,applied=apply(anchor['members'],anchor['decision_cutoff'],decision)
        available=max(r['available_date'] for r in history if r['available_date']<=decision)
        reports=[r for r in history if r['available_date']==available];report=reports[0]['report_date']
        proxy,proxyissues,_=apply([r['ticker'] for r in reports],report,decision)
        index=calendar.index(decision);days=calendar[index-252:index+1];end=decisions[decisions.index(decision)+1] if decision!=decisions[-1] else '2026-07-30'
        execution=[d for d in calendar if decision<=d<=end];rows=[]
        for ticker in sorted(chain|proxy):
            choices=[]
            for path in sources.get(ticker,[]):
                data=prices(ticker,path)
                def valid(day,ohlc):
                    try:
                        values=[float(x) for x in data[day]]
                        if ohlc:return 0<values[2]<=min(values[0],values[3])<=max(values[0],values[3])<=values[1]
                        return values[3]>0
                    except (KeyError,TypeError,ValueError):return False
                choices.append(dict(path=path,basis='CONDITIONAL_PROVIDER_COORDINATE' if path==panelpath or path.endswith('.bin') else 'CONDITIONAL_ARCHIVE_NEEDS_PERIOD_UNIT_REVIEW',
                    missing_training_close=[d for d in days if not valid(d,False)],missing_execution_ohlc=[d for d in execution if not valid(d,True)],
                    observed_nondividend_actions=[e for e in source_events.get((ticker,path),[]) if days[0]<e['date']<='2026-07-30']))
            identity=[r for r in identities if ticker in r['ticker_set'].split('|') or r['ticker']==ticker]
            rows.append(dict(ticker=ticker,in_event_chain=ticker in chain,in_latest_report_overlay=ticker in proxy,
                identity_candidates=[{k:r[k] for k in ['security_id','issuer_id','cusip','available_from','observation_from','observation_to','identity_status']} for r in identity],
                prior_reviewed_identity_candidates=list({c['security_id']:dict(security_id=c['security_id'],issuer_id=c['issuer_id'],identity_bridge=c.get('identity_bridge'),source=trainpath) for w in training['windows'] for c in w['candidates'] if c['ticker']==ticker}.values()),
                identity_resolution='REQUIRES_DATE_SPECIFIC_LIFECYCLE_REVIEW' if len(identity)!=1 else 'ONE_EXISTING_CANDIDATE_NOT_YET_PERIOD_CERTIFIED',
                source_candidates=choices,has_single_numeric_complete_source=any(not s['missing_training_close'] and not s['missing_execution_ohlc'] for s in choices)))
        windows.append(dict(decision_date=decision,active_date=calendar[index+1],training_dates=days,scenario_start_dates=days[::21][:-1],scenario_end_dates=days[21::21],execution_dates=execution,
            conditional_event_chain_members=sorted(chain),latest_report_overlay_members=sorted(proxy),latest_report_date=report,latest_report_available=available,
            report_extra=sorted(proxy-chain),report_missing=sorted(chain-proxy),event_chain_issues=issues,report_overlay_issues=proxyissues,
            applied_official_events=applied,candidates=rows,search_ready=False))
    return dict(status='SOURCE_SCOPE_PREPARED_MEMBERSHIP_AND_UNIT_REVIEW_REQUIRED',period=dict(start='2025-07-31',end='2026-07-30'),windows=windows,
        source_hashes=pins,prior_reviewed_anchor=dict(path=anchor_path,date=anchor['decision_cutoff'],role='EVENT_CHAIN_START_ONLY_NOT_POOL_CARRY_FORWARD'),
        exact_events_last_effective=max(e['effective_date'] for e in events),latest_report_date=max(r['report_date'] for r in history),
        gaps=['Official event registry currently ends 2026-01-20; absence of later rows is not proof of no later changes.',
              'Latest filed QQQ holdings plus public events are independent proxy evidence; reconcile all membership differences before claiming full historical NDX membership.',
              'Old full-source price availability alone does not validate 2025-2026 unit changes: review HON/HONA,SOLS; CMCSA/VSNT; AZN ADS and any returned non-simple actions.',
              'INSM saved Sina cache starts 2025-06-09 due requested_begin, not proof of IPO short history; missing prior training must be sourced, not exclude as immature issuer.',
              'No gross, decision nominal costs or executable search_arguments generated until date-specific identity and price-coordinate reviews close.'],
        network_calls=0,search_calls=0,book_calls=0,current_survivors_used_as_membership=False,members_removed_for_future_price_gaps=False)

if __name__=='__main__':
    if OUTPUT.exists():raise ValueError('CREATE_ONLY_OUTPUT_EXISTS')
    result=prepare()
    with OUTPUT.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2,allow_nan=False)
    print(json.dumps(dict(path=str(OUTPUT),sha256=hashlib.sha256(OUTPUT.read_bytes()).hexdigest(),windows=[dict(date=w['decision_date'],chain=len(w['conditional_event_chain_members']),proxy=len(w['latest_report_overlay_members']),extra=w['report_extra'],missing=w['report_missing'],numeric_gaps=[r['ticker'] for r in w['candidates'] if not r['has_single_numeric_complete_source']]) for w in result['windows']]),ensure_ascii=False))
