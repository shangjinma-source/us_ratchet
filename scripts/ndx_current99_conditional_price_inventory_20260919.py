"""Read-only references to 95 original and four isolated post-action price channels."""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_base_three_cell_window_delta_research import publish
BASE=ROOT/'data/cache/research'
ANCHORS={
 'old_index':('current101_conditional_prices_20260919_v1/index_101.json','0e48880f524f61c069efa9027f9dff64af7f39625b928bc07695402e7966d3ff'),
 'old_audit':('current101_conditional_prices_20260919_v1/archive_independent_audit_20260919.json','7fb3a17fe7234a77383d1dd0ae2868f3d4002799419233b3df4b5b418d6297e6'),
 'four_index':('post_action_quote_archive_probe_20260919_v2/index.json','877dc14a5d9aaf3baaa30e289369959828236a33c20edc9ddfc9a6c0841fae28'),
 'four_audit':('post_action_quote_archive_probe_20260919_v2/independent_raw_decimal_audit.json','2953804350d2976f28883e3b5d27d84644c4788541cb6fd1a2288df4386e3c49')}
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__).resolve(),archive.SOURCE,Path(publish.__code__.co_filename).resolve())}


def combine_references(*,original_rows,post_rows):
    old={r['ticker']:r for r in original_rows};new={r['ticker']:r for r in post_rows}
    if len(old)!=101 or len(original_rows)!=101 or len(new)!=4 or len(post_rows)!=4 or set(new)!={'EXC','HON','LRCX','WDC'}:
        raise ValueError('Exact original 101 and four post-action channels required')
    blocked={t for t,r in old.items() if r['status']=='EXPLICITLY_BLOCKED_NOT_MISSING_PRICE'}
    if blocked!={'CMCSA','EXC','HON','LRCX','TRI','WDC'}:raise ValueError('Original six blocked references required')
    rows=[];common=None
    for ticker,original in old.items():
        if ticker in new:
            chosen=new[ticker]
            if chosen['status']!='POST_ACTION_CONDITIONAL_PRICE_INDEPENDENTLY_AUDITED':raise ValueError('Independent post-action audit required')
            row=dict(ticker=ticker,status='CONDITIONAL_POST_ACTION_REFERENCE',original_reference=deepcopy(original),post_action_reference=deepcopy(chosen))
        elif ticker in blocked:
            rows.append(dict(ticker=ticker,status='BLOCKED_NO_CONDITIONAL_PRICE_REFERENCE',original_reference=deepcopy(original),post_action_reference=None));continue
        else:
            chosen=original
            if chosen['status']!='CONDITIONAL_PRICE_ARITHMETIC_VERIFIED_NOT_IDENTITY':raise ValueError('Original conditional audit status differs')
            row=dict(ticker=ticker,status='ORIGINAL_CONDITIONAL_REFERENCE',original_reference=deepcopy(original),post_action_reference=None)
        calendar=chosen['calendar']
        if (type(calendar) is not list or not calendar or calendar!=sorted(set(calendar))
                or type(chosen['row_count']) is not int or chosen['row_count']!=len(calendar)):
            raise ValueError('Full audited provider calendar required')
        row.update(calendar=calendar,row_count=len(calendar),price_identity_verified=False,point_in_time_verified=False,promotion_allowed=False)
        common=set(calendar) if common is None else common&set(calendar)
        rows.append(row)
    return dict(schema='CURRENT101_WITH_99_CONDITIONAL_PRICE_REFERENCES_V1',rows=rows,total_channels=101,
        original_conditional_channels=95,additional_post_action_channels=4,conditional_channels=99,blocked_channels=['CMCSA','TRI'],
        total_conditional_rows=sum(r.get('row_count',0) for r in rows),common_99_provider_calendar=sorted(common),
        original_artifacts_modified=False,quote_reconstruction_performed=False,independent_arithmetic_recomputed_here=False,
        input_artifact_binding_verified=False,
        provider_calendar_is_exchange_calendar=False,all_99_security_identities_verified=False,price_identity_verified=False,
        full_historical_source_closure_recovered=False,returns_generated=False,training_performed=False,point_in_time_verified=False,promotion_allowed=False)


def verify(report):
    sources=report['historical_expected_source_hashes']
    required=dict(LOADED,**{str(BASE/p):h for p,h in ANCHORS.values()})
    if any(sources.get(p)!=h for p,h in required.items()):raise ValueError('Hard external audit/index or loaded source omitted')
    checked=archive.verify_expected_sources(sources,archive.load_contract())
    if checked!=report['archive_resolution']:raise ValueError('Archive source partition differs')
    for key in ('original_artifacts_modified','quote_reconstruction_performed','independent_arithmetic_recomputed_here',
        'provider_calendar_is_exchange_calendar','all_99_security_identities_verified','price_identity_verified',
        'full_historical_source_closure_recovered','returns_generated','training_performed','point_in_time_verified','promotion_allowed'):
        if report.get(key) is not False:raise ValueError('Conditional research claim upgraded')


def build():
    sources=dict(LOADED)
    def read(path,sha):
        path=str(Path(path).resolve());raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Hard reviewed artifact differs')
        archive.merge(sources,{path:sha});return json.loads(raw)
    documents={k:read(BASE/p,h) for k,(p,h) in ANCHORS.items()}
    old_index,old,four_index,four=(documents[k] for k in ('old_index','old_audit','four_index','four_audit'))
    if (old['schema']!='CURRENT101_FINAL_PRICE_ARCHIVE_RESOLVED_INDEPENDENT_AUDIT_V1'
            or four['schema']!='POST_ACTION_FOUR_INDEPENDENT_RAW_DECIMAL_AUDIT_V1'
            or old['index']!=dict(path=str(BASE/ANCHORS['old_index'][0]),sha256=ANCHORS['old_index'][1])
            or four['index_ref']!=dict(path=str(BASE/ANCHORS['four_index'][0]),sha256=ANCHORS['four_index'][1])
            or old['conditional_price_channel_count']!=95 or old['blocked_channel_count']!=6
            or four['total_rows']!=2101 or four['cells_checked']!=4202 or four['producer_or_old_oracle_called'] is not False):
        raise ValueError('Complete matching independent audit scope required')
    for document in (old,four):
        for key in ('price_identity_verified','point_in_time_verified','promotion_allowed'):
            if document[key] is not False:raise ValueError('Independent audit boundary upgraded')
    for document,key in ((old,'historical_expected_source_hashes'),(four,'source_hashes')):
        archive.merge(sources,document[key])
        if archive.verify_expected_sources(document[key],archive.load_contract())!=document['archive_resolution']:
            raise ValueError('Independent audit archive partition differs')
    if (old_index['completed']!=101 or old_index['status']!='COMPLETE' or four_index['completed']!=4
            or [r['ticker'] for r in old['rows']]!=[r['ticker'] for r in old_index['entries']]
            or [r['ticker'] for r in four['rows']]!=[r['ticker'] for r in four_index['entries']]):
        raise ValueError('Independent audit/index ordered denominator differs')
    old_rows=[];new_rows=[]
    for audit_row,entry in zip(old['rows'],old_index['entries']):
        if old['historical_expected_source_hashes'].get(entry['path'])!=entry['sha256']:raise ValueError('Original audit omitted saved checkpoint')
        saved=read(entry['path'],entry['sha256'])
        if saved['ticker']!=audit_row['ticker']:raise ValueError('Original artifact ticker differs')
        old_rows.append(dict(audit_row,artifact_reference=dict(path=entry['path'],sha256=entry['sha256'])))
    for audit_row,entry in zip(four['rows'],four_index['entries']):
        if four['source_hashes'].get(entry['path'])!=entry['sha256']:raise ValueError('Four audit omitted saved checkpoint')
        saved=read(entry['path'],entry['sha256']);result=saved['result']
        if (saved['ticker']!=audit_row['ticker'] or [r['session'] for r in result['rows']]!=audit_row['calendar']
                or result['row_count']!=audit_row['row_count'] or Decimal(audit_row['maximum_absolute_decimal_error'])>Decimal('1e-12')):
            raise ValueError('Post-action independent full calendar/numeric evidence differs')
        new_rows.append(dict(audit_row,status='POST_ACTION_CONDITIONAL_PRICE_INDEPENDENTLY_AUDITED',
            artifact_reference=dict(path=entry['path'],sha256=entry['sha256'])))
    report=combine_references(original_rows=old_rows,post_rows=new_rows)
    report.update(historical_expected_source_hashes=sources,archive_resolution=archive.verify_expected_sources(sources,archive.load_contract()),
        external_audit_references={key:dict(path=str(BASE/p),sha256=h) for key,(p,h) in ANCHORS.items() if 'audit' in key},
        input_artifact_binding_verified=True)
    verify(report);return report


def publish_verified(path,report):
    if Path(path).exists():raise FileExistsError('Create-only reference inventory')
    verify(report);saved=publish(path,report);verify(report);return saved


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(publish_verified(args.output,build())))
