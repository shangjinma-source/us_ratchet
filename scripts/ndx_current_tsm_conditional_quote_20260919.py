"""One hard-bound incumbent TSM conditional quote channel; no identity adjudication."""
import argparse
import gzip
import json
from decimal import Decimal
from datetime import datetime
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts import ndx_current_tsm_raw_readback_20260919 as evidence
from backtest import ndx_nominal_quote_reconstruction_research as nominal
from backtest import ndx_root_price_archive_contract_research as archive
from scripts.ndx_base_three_cell_window_delta_research import publish
READBACK=evidence.FOLDER/'independent_raw_readback.json'
READBACK_SHA='1cdd01d248e0448dd0cd1f31bb7314ed9976e4effebd5bec17dfd7a0bf946ece'
LOADED=dict(evidence.LOADED)
for path in (Path(__file__).resolve(),Path(evidence.__file__).resolve(),nominal.SOURCE,archive.SOURCE,Path(publish.__code__.co_filename).resolve()):
    archive.merge(LOADED,{str(path):evidence.raw_reader.drift.file_sha(path)})


def decimal_audit(decoded,result,calendar):
    data=json.loads(decoded,object_pairs_hook=evidence.raw_reader.unique,parse_float=Decimal,parse_int=Decimal)['chart']['result'][0]
    dates=[evidence.raw_reader.day(int(t)) for t in data['timestamp']]
    if dates!=sorted(set(dates)) or data['meta']['symbol']!='TSM' or data.get('events',{}).get('splits',{}):raise ValueError('Exact zero-returned-split TSM scope required')
    if type(result['row_count']) is not int or result['row_count']!=len(calendar) or [r['session'] for r in result['rows']]!=calendar:raise ValueError('Full fixed target calendar required')
    positions={d:i for i,d in enumerate(dates)};maximum=Decimal(0)
    for row in result['rows']:
        if (row['ticker']!='TSM' or row['currency']!='USD' or type(row['split_factor']) not in (int,float) or row['split_factor']!=1
                or row['split_factor_numerator']!='1' or row['split_factor_denominator']!='1' or row['later_split_effective_sessions']!=[]):raise ValueError('Conditional factor one required')
        i=positions[row['session']]
        if type(row['provider_timestamp']) is not int or row['provider_timestamp']!=data['timestamp'][i]:raise ValueError('Raw timestamp differs')
        for field in ('open','close'):
            raw=data['indicators']['quote'][0][field][i]
            if type(raw) not in (int,Decimal) or not Decimal(raw).is_finite() or raw<=0:raise ValueError('Finite positive raw price required')
            actual=evidence.raw_reader.number(row['nominal_'+field]);copied=evidence.raw_reader.number(row['quote_'+field])
            error=abs(actual-Decimal(raw));maximum=max(maximum,error)
            if actual!=copied or error>Decimal('1e-12'):raise ValueError('Independent Decimal raw quote differs')
    return dict(row_count=len(calendar),cells_checked=2*len(calendar),maximum_absolute_decimal_error=str(maximum),
                reported_factor_used=False,dividends_applied=False,adjclose_used=False)


def reconstruct(decoded,receipt,calendar):
    info=evidence.raw_reader.inspect_raw(decoded,'TSM')
    cutoff=evidence.CUTOFF;received=datetime.fromisoformat(receipt['received_at_utc'])
    if received.tzinfo is None:raise ValueError('Aware receipt required')
    receipt_day=received.astimezone(evidence.raw_reader.NY).date().isoformat()
    expected=[d for d in info['days'] if d<=cutoff and d<receipt_day]
    if not expected or expected[-1]!=cutoff or calendar!=expected or info['events']:raise ValueError('Complete fixed-cutoff zero-returned-split channel required')
    result=nominal.reconstruct_nominal_quote_ticker(raw=decoded,ticker='TSM',calendar=calendar,
        request=dict(method=receipt['request_method'],credentials_sent=receipt['credentials_sent'],url=receipt['request_url']),
        received_at_utc=receipt['received_at_utc'],quote_field_basis=nominal.BASIS)
    return result,decimal_audit(decoded,result,calendar)


def verify(value):
    sources=value['historical_expected_source_hashes']
    if any(sources.get(p)!=h for p,h in LOADED.items()) or sources.get(str(READBACK))!=READBACK_SHA:raise ValueError('Required source omitted')
    checked=archive.verify_expected_sources(sources,archive.load_contract())
    if checked!=value['archive_resolution'] or checked['archive_resolutions'] or checked['historical_gap_observations']:raise ValueError('Only actual non-root sources allowed')
    for k in ('price_identity_verified','quote_basis_independently_authenticated','complete_actions_verified','zero_returned_splits_proves_no_actions',
              'point_in_time_verified','promotion_allowed','returns_generated','training_performed','fixed_99_cutoff_upgraded','old_readiness_modified'):
        if value[k] is not False:raise ValueError('Conditional scope cannot be upgraded')


def build():
    sources=dict(LOADED)
    def read(path,h):
        path=str(Path(path).resolve());raw=Path(path).read_bytes()
        if evidence.raw_reader.digest(raw)!=h:raise ValueError('Hard evidence bytes differ')
        archive.merge(sources,{path:h});return raw
    report=evidence.raw_reader.loads(read(READBACK,READBACK_SHA))
    fresh=evidence.build()
    if evidence.raw_reader.canonical(fresh)!=evidence.raw_reader.canonical(report):raise ValueError('Independent raw readback differs')
    archive.merge(sources,report['source_hashes']);contract=archive.load_contract();archive.verify_expected_sources(sources,contract)
    index=evidence.raw_reader.loads(read(evidence.INDEX,evidence.INDEX_SHA));entry=index['entry']
    receipt=evidence.raw_reader.loads(read(entry['receipt_path'],entry['receipt_sha256']))
    raw=read(report['raw_path'],report['raw_sha256']);decoded=gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw
    if evidence.raw_reader.digest(decoded)!=report['decoded_sha256']:raise ValueError('Decoded SHA differs')
    calendar=report['coverage']['target_completed_calendar'];result,independent=reconstruct(decoded,receipt,calendar)
    events=evidence.raw_reader.loads(decoded)['chart']['result'][0].get('events',{})
    checked=archive.verify_expected_sources(sources,contract)
    value=dict(schema='INCUMBENT_TSM_FIXED_CUTOFF_CONDITIONAL_NOMINAL_QUOTE_V1',ticker='TSM',cutoff=evidence.CUTOFF,
        raw_readback=dict(path=str(READBACK),sha256=READBACK_SHA),capture_index=dict(path=str(evidence.INDEX),sha256=evidence.INDEX_SHA),
        calendar=calendar,reconstruction=result,independent_decimal_audit=independent,all_returned_raw_events=events,
        excluded_after_fixed_target=report['coverage']['excluded_after_fixed_target'],received_at_utc=report['received_at_utc'],
        historical_expected_source_hashes=sources,archive_resolution=checked,actual_root_price_csv_dependency_count=0,
        archive_authority_count=111,original_22_79_capture_loader_called=False,synthetic_manifest_created=False,
        price_identity_verified=False,quote_basis_independently_authenticated=False,complete_actions_verified=False,
        zero_returned_splits_proves_no_actions=False,point_in_time_verified=False,promotion_allowed=False,returns_generated=False,
        training_performed=False,fixed_99_cutoff_upgraded=False,old_readiness_modified=False)
    verify(value);return value


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Create-only conditional quote')
    verify(value);saved=publish(path,value);verify(value);return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args()
    print(json.dumps(publish_verified(args.output,build())))
