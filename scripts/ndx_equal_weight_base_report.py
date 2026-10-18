"""Source-bound equal-weight base research report with strict readback."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_equal_weight_base_inputs as preparation
from backtest import ndx_equal_weight_fractional_batch as evaluator

_SOURCE=Path(__file__).resolve()
_LOADED={str(Path(path).resolve()):hashlib.sha256(Path(path).read_bytes()).hexdigest()
         for path in (__file__,preparation.__file__,evaluator.__file__)}


def _digest(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:
        raise ValueError('Explicit SHA256 required')


def _check_sources(sources):
    if type(sources) is not dict or not sources:raise ValueError('Source closure required')
    for path,digest in sources.items():
        _digest(digest)
        if type(path) is not str or not Path(path).is_absolute():raise ValueError('Absolute source path required')
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=digest:raise ValueError('Report source changed: '+path)


def _merge(sources,other):
    for path,digest in other.items():
        if path in sources and sources[path]!=digest:raise ValueError('Source closure conflict')
        sources[path]=digest


def _coordinate(source_batch,universe_track,selection_date):
    from datetime import date
    if any(type(value) is not str or not value or value!=value.strip() for value in (source_batch,universe_track,selection_date)):
        raise ValueError('Canonical explicit date/source coordinate required')
    if date.fromisoformat(selection_date).isoformat()!=selection_date:raise ValueError('Canonical selection date required')
    return dict(source_batch=source_batch,universe_track=universe_track,selection_date=selection_date)


def _validate(report):
    if type(report) is not dict or set(report)!={'schema','coordinate','definitions','input_summary','training_semantics',
            'evaluation','source_hashes','saved_economic_metrics_used','whole_lot_status','promotion_allowed'}:
        raise ValueError('Exact base report schema required')
    if (report['schema']!='ndx_equal_weight_base_report_v1' or report['saved_economic_metrics_used'] is not False
            or report['whole_lot_status']!='NOT_EVALUATED' or report['promotion_allowed'] is not False):
        raise ValueError('Invalid report role/whole-lot claims')
    _coordinate(**report['coordinate'])
    definitions=report['definitions']; result=report['evaluation']; summary=report['input_summary']
    semantics=report['training_semantics']
    payload=semantics['payload']
    semantic_sha=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if (semantics['training_semantics_sha256']!=semantic_sha
            or payload['schema']!='ndx_dynamic_training_semantics_v1'
            or payload['source_batch']!=report['coordinate']['source_batch']
            or payload['universe_track']!=report['coordinate']['universe_track']
            or payload['decision_data_end']!=result['input_calendar_end']
            or payload['decision_data_end']>=report['coordinate']['selection_date']):
        raise ValueError('Training semantics/coordinate binding differs')
    if type(definitions) is not list or not definitions:raise ValueError('Explicit definitions required')
    combos=[]
    for definition in definitions:
        if (type(definition) is not list or not definition or any(type(t) is not str or not t or t!=t.strip().upper() for t in definition)
                or definition!=sorted(set(definition))):raise ValueError('Invalid ticker definition')
        combos.append(tuple(definition))
    if len(set(combos))!=len(combos):raise ValueError('Duplicate base definitions')
    if (result['schema']!='ndx_equal_weight_fractional_batch_v1' or result['whole_lot_status']!='NOT_EVALUATED'
            or result['full_legacy_result_compatible'] is not False or result['promotion_allowed'] is not False):
        raise ValueError('Fractional-only result identity required')
    count=len(combos)
    if (type(result['count']) is not int or result['count']!=count or len(result['records'])!=count
            or type(summary['equal_weight_base_count']) is not int or summary['equal_weight_base_count']!=count
            or summary['cardinalities']!=sorted({len(combo) for combo in combos})):
        raise ValueError('Base report denominator mismatch')
    # input_summary is the preparation-stage audit. Its false evaluation flag
    # does not describe the subsequently computed evaluation records.
    if (summary['saved_economic_metrics_used'] is not False or summary['new_evaluation_performed'] is not False
            or summary['promotion_allowed'] is not False
            or type(summary['all_base_count']) is not int or summary['all_base_count']<count
            or type(summary['delta_count']) is not int or summary['delta_count']<0):
        raise ValueError('Invalid base source summary')
    required_metrics={'return_p50','return_p10','max_drawdown_p50','max_drawdown_p90',
        'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent','paired_drawdown_cost_p50_vs_incumbent',
        'paired_drawdown_cost_p90_vs_incumbent','return_p50_vs_012922','return_p10_vs_012922',
        'max_drawdown_p50_vs_012922','max_drawdown_p90_vs_012922','target_012922_distance'}
    for combo,row in zip(combos,result['records']):
        if set(row)!={'tickers','holding_count','weight_spec','fractional_metrics','risk_liquidity_metrics',
                     'rolling_fit_window_count','whole_lot_status','promotion_allowed'}:
            raise ValueError('Exact fractional record schema required')
        if (row['tickers']!=';'.join(combo) or type(row['holding_count']) is not int or row['holding_count']!=len(combo)
                or row['weight_spec']!='equal_weight' or row['whole_lot_status']!='NOT_EVALUATED' or row['promotion_allowed'] is not False):
            raise ValueError('Base result/definition identity differs')
        if (type(row['rolling_fit_window_count']) is not int or row['rolling_fit_window_count']!=len(result['window_starts'])
                or row['rolling_fit_window_count']<1):raise ValueError('Window denominator mismatch')
        if not required_metrics<=set(row['fractional_metrics']):raise ValueError('Missing fractional metrics')
        if any(type(v) not in (int,float) or not math.isfinite(v) for v in row['fractional_metrics'].values()):
            raise ValueError('Invalid fractional metric')
        risk=row['risk_liquidity_metrics']
        numeric_risk={'risk_chain_top1','risk_chain_top3','issuer_top1','weight_top3_max','effective_n_min',
                      'portfolio_min_median_dollar_volume_usd','minimum_single_weight_observed'}
        boolean_risk={'declared_max_single_passed','declared_security_top3_weight_passed',
                      'declared_risk_chain_top1_weight_passed','declared_effective_n_passed','liquidity_constraint_passed'}
        if set(risk)!=numeric_risk|boolean_risk:
            raise ValueError('Exact risk/liquidity metric keys required')
        if (any(type(risk[key]) not in (int,float) or not math.isfinite(risk[key]) for key in numeric_risk)
                or any(type(risk[key]) is not bool for key in boolean_risk)):
            raise ValueError('Invalid risk/liquidity metric types')
    for path,digest in {**_LOADED,**result['source_hashes']}.items():
        if report['source_hashes'].get(path)!=digest:raise ValueError('Required source missing from report closure')
    _check_sources(report['source_hashes'])


def run(*,source_batch,universe_track,selection_date):
    coordinate=_coordinate(source_batch,universe_track,selection_date)
    _check_sources(_LOADED)
    prepared=preparation.prepare_equal_base_date(**coordinate)
    inputs=prepared['inputs']
    evaluation=evaluator.evaluate_equal_weight_fractional_batch(combinations=prepared['combinations'],
        universe=inputs['universe'],returns=inputs['returns'],target_returns=inputs['target_returns'],
        incumbent_weights=inputs['incumbent_weights'],contract=inputs['contract'])
    sources=dict(_LOADED)
    _merge(sources,prepared['source_hashes']);_merge(sources,evaluation['source_hashes'])
    report=dict(schema='ndx_equal_weight_base_report_v1',coordinate=coordinate,
        definitions=[list(combo) for combo in prepared['combinations']],input_summary=prepared['summary'],
        training_semantics=prepared['training_semantics'],evaluation=evaluation,source_hashes=sources,
        saved_economic_metrics_used=False,whole_lot_status='NOT_EVALUATED',promotion_allowed=False)
    _validate(report)
    return report


def _object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise ValueError('Duplicate report JSON key')
        result[key]=value
    return result


def load_report(path,*,expected_sha256):
    _digest(expected_sha256)
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=expected_sha256:raise ValueError('Report SHA mismatch')
    report=json.loads(raw,object_pairs_hook=_object)
    _validate(report)
    if Path(path).read_bytes()!=raw:raise ValueError('Report changed during readback')
    return report


def save_new(report,path):
    _validate(report)
    raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:stream.write(raw)
    digest=hashlib.sha256(raw).hexdigest()
    restored=load_report(path,expected_sha256=digest)
    if restored!=report:raise ValueError('Report strict readback differs')
    return digest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source-batch','universe-track','selection-date','output-path'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args()
    if Path(args.output_path).exists():raise ValueError('Output exists; inspect rather than rerun')
    result=run(source_batch=args.source_batch,universe_track=args.universe_track,selection_date=args.selection_date)
    digest=save_new(result,args.output_path)
    print(json.dumps(dict(path=args.output_path,sha256=digest,count=result['evaluation']['count'],whole_lot_status='NOT_EVALUATED')))
