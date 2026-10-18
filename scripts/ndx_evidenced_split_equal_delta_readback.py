"""Independent read-only scalar audit; imports no training or execution modules."""
from copy import deepcopy
import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
SOURCE_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
DIRECTORY=ROOT/'data/cache/research/evidenced_split_equal_delta_20260912_v1'
INVENTORY=ROOT/'data/cache/research/dynamic_frozen_v2/combined_summary_inventory_20260912.json'
INVENTORY_SHA='baa74f6447e4663ac13a0b4174ad0fa0cf0d799ce3d35a735c9f25379e24ca09'
CORRECTIONS={
    str(ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/root_return_semantics_review_20260912.json'):
        'a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b',
    str(ROOT/'data/cache/research/legacy_pool_additional_split_probe_20260912_v1/report.json'):
        '64e6c86a9ad8045dcb925990c04a7d00c8480cdec2e922ef215e9ed839acd850'}
DATES=('2023-04-03','2023-05-01','2023-06-01','2023-07-03','2023-08-01','2023-09-01',
       '2023-10-02','2023-11-01','2023-12-01','2024-01-02','2024-02-01','2024-03-01',
       '2024-04-01','2024-05-01','2024-06-03')
CELLS=(('GOOG','2022-07-18',-.025335378898117544),
       ('GOOGL','2022-07-18',-.024580059928059006),('FTNT','2022-06-23',.019968386675822902))
METRICS=('return_p50','return_p10','max_drawdown_p50','max_drawdown_p90',
         'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
         'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent',
         'return_p50_vs_012922','return_p10_vs_012922','max_drawdown_p50_vs_012922',
         'max_drawdown_p90_vs_012922','target_012922_distance')
RULE='BEFORE_METRIC_ACCESS_EACH_K_LEXICAL_FIRST_LAST_AND_EACH_GOOG_GOOGL_FTNT_PRESENCE_GROUP_LEXICAL_FIRST_LAST'


def require(condition,message):
    if not condition:raise ValueError(message)


def object_pairs(pairs):
    result={}
    for key,value in pairs:
        require(key not in result,'Duplicate JSON key');result[key]=value
    return result


def read(path,digest=None):
    raw=Path(path).read_bytes();actual=hashlib.sha256(raw).hexdigest()
    require(digest is None or actual==digest,'Input SHA differs: '+str(path))
    return json.loads(raw,object_pairs_hook=object_pairs),actual


def verify_sources(sources):
    for path,digest in sources.items():
        require(Path(path).is_absolute() and hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest,
                'Source SHA differs: '+path)


def decode(value):
    if isinstance(value,dict):
        if set(value)=={'mapping'}:return {key:decode(item) for key,item in value['mapping'].items()}
        if set(value)=={'float_hex'}:
            number=float.fromhex(value['float_hex']);require(math.isfinite(number),'Nonfinite encoded input');return number
        if set(value)=={'timestamp'}:return value['timestamp'][:10]
        if set(value)=={'sequence_type','items'}:return [decode(item) for item in value['items']]
        raise ValueError('Unknown typed value')
    require(value is None or type(value) in (str,int,bool),'Unknown scalar encoding')
    return value


def unpack_inputs(captured):
    output={}
    for name,item in captured.items():
        value=decode(item['payload'])
        if item['kind']=='panel':
            value['values_by_column']=dict(zip(value['columns'],value['column_values']))
        else:require(item['kind']=='non_panel','Unknown input kind')
        output[name]=value
    return output


def select_samples(definitions):
    """Fixed structural rule, intentionally takes no result metrics."""
    groups={}
    for combo in definitions:
        groups.setdefault(('k',len(combo)),[]).append(tuple(combo))
        presence=tuple(ticker in combo for ticker in ('GOOG','GOOGL','FTNT'))
        groups.setdefault(('presence',presence),[]).append(tuple(combo))
    chosen=set()
    for members in groups.values():
        ordered=sorted(members);chosen.update((ordered[0],ordered[-1]))
    return sorted(chosen)


def quantile(values,probability):
    ordered=sorted(values);position=(len(ordered)-1)*probability
    low=math.floor(position);high=math.ceil(position)
    return ordered[low]+(ordered[high]-ordered[low])*(position-low)


def scalar_window(values,cost):
    wealth=1.;peak=1.;drawdown=0.
    for index,value in enumerate(values):
        gross=1.+value
        if index==0:gross*=1.-cost
        wealth*=gross;require(math.isfinite(wealth) and wealth>0,'Invalid scalar wealth')
        peak=max(peak,wealth);drawdown=max(drawdown,1.-wealth/peak)
    return wealth**(252./len(values))-1.,drawdown


def scalar_metrics(inputs,combo):
    returns=inputs['returns']['values_by_column'];target=inputs['target_returns']['column_values'][0]
    contract=inputs['contract'];incumbent=inputs['incumbent_weights']
    total=sum(incumbent.values());incumbent={key:value/total for key,value in incumbent.items()}
    n=len(inputs['returns']['index']);k=len(combo)
    candidate=[sum(returns[ticker][day]*(1./k) for ticker in combo) for day in range(n)]
    control=[sum(returns[ticker][day]*incumbent[ticker] for ticker in sorted(incumbent)) for day in range(n)]
    turnover=.5*sum(abs((1./k if ticker in combo else 0.)-incumbent.get(ticker,0.))
        for ticker in sorted(set(combo)|set(incumbent)))
    fee=turnover*contract['transaction_cost_bps']/10000.
    cr=[];cd=[];ir=[];idd=[];tr=[];td=[]
    for ordinal,start in enumerate(range(contract['fit_days'],n-contract['window_days']+1,contract['step_days'])):
        end=start+contract['window_days']
        a,b=scalar_window(candidate[start:end],fee if ordinal==0 else 0.);cr.append(a);cd.append(b)
        a,b=scalar_window(control[start:end],0.);ir.append(a);idd.append(b)
        a,b=scalar_window(target[start:end],0.);tr.append(a);td.append(b)
    q=quantile
    result=dict(return_p50=q(cr,.5),return_p10=q(cr,.1),max_drawdown_p50=q(cd,.5),max_drawdown_p90=q(cd,.9),
        paired_return_p50_vs_incumbent=q([a-b for a,b in zip(cr,ir)],.5),
        paired_return_p10_vs_incumbent=q([a-b for a,b in zip(cr,ir)],.1),
        paired_drawdown_cost_p50_vs_incumbent=q([a-b for a,b in zip(cd,idd)],.5),
        paired_drawdown_cost_p90_vs_incumbent=q([a-b for a,b in zip(cd,idd)],.9),
        return_p50_vs_012922=q(cr,.5)-q(tr,.5),return_p10_vs_012922=q(cr,.1)-q(tr,.1),
        max_drawdown_p50_vs_012922=q(cd,.5)-q(td,.5),max_drawdown_p90_vs_012922=q(cd,.9)-q(td,.9))
    result['target_012922_distance']=sum(abs(result[key]) for key in (
        'return_p50_vs_012922','return_p10_vs_012922','max_drawdown_p50_vs_012922','max_drawdown_p90_vs_012922'))
    return result,turnover,fee


def verify_date(selection_date):
    require(selection_date in DATES,'Unknown date')
    inventory,_=read(INVENTORY,INVENTORY_SHA)
    descriptor,=[row for row in inventory['summaries'] if row['coordinate']['selection_date']==selection_date]
    summary,_=read(descriptor['path'],descriptor['sha256'])
    equal_path,equal_sha,=next(iter([(path,digest) for path,digest in summary['source_hashes'].items()
        if Path(path).name=='equal_base_'+selection_date.replace('-','')+'_20260911.json']))
    original,_=read(equal_path,equal_sha)
    definitions=original['definitions'];samples=select_samples(definitions)
    path=DIRECTORY/('equal_delta_'+selection_date.replace('-','')+'.json')
    report,report_sha=read(path);audit=report['audit'];sources=report['source_hashes']
    require(report['schema']=='ndx_evidenced_split_equal_delta_v1','Wrong report schema')
    require(report['coordinate']==original['coordinate']==descriptor['coordinate'],'Date/source coordinate differs')
    require(audit['old_report_path']==equal_path and audit['old_report_sha256']==equal_sha,'Wrong bound baseline')
    require(sources.get(str(Path(equal_path).resolve()))==equal_sha,'Missing bound baseline source')
    required=dict(original['source_hashes'])
    required.update(CORRECTIONS)
    for correction_path,correction_sha in CORRECTIONS.items():
        evidence,_=read(correction_path,correction_sha)
        for source_path,source_sha in evidence['source_hashes'].items():
            require(source_path not in required or required[source_path]==source_sha,'Evidence source conflict')
            required[source_path]=source_sha
    require(all(sources.get(source_path)==source_sha for source_path,source_sha in required.items()),
        'Original or correction closure entry missing')
    require(audit['cells']==[dict(ticker=ticker,session=day,old_value=0.,new_value=value) for ticker,day,value in CELLS],
        'Correction audit metadata differs')
    verify_sources(sources)
    context,context_sha=read(audit['original_context_path'],audit['original_context_sha256'])
    require(sources.get(audit['original_context_path'])==context_sha,'Original context absent from closure')
    require(all(all(task[key]==value for key,value in report['coordinate'].items()) for task in context['tasks']),
        'Context task date differs')
    require(report['runtime']==context['runtime'],'Numerical runtime changed')
    original_inputs=context['prepared_inputs'];expected=deepcopy(original_inputs)
    payload=expected['returns']['payload']['mapping']
    columns=decode(payload['columns']);days=decode(payload['index'])
    for ticker,day,value in CELLS:
        item=payload['column_values']['items'][columns.index(ticker)]['items'][days.index(day)]
        require(item=={'float_hex':0.0.hex()},'Original cell was not exact positive zero')
        item['float_hex']=value.hex()
    require(expected==report['corrected_inputs'],'Changes outside exactly three declared cells')
    inputs=unpack_inputs(expected);contract=inputs['contract']
    forward=[days[start:start+contract['window_days']] for start in
        range(contract['fit_days'],len(days)-contract['window_days']+1,contract['step_days'])]
    affected={ticker for ticker,day,value in CELLS if any(day in window for window in forward)}
    require(affected==({'GOOG','GOOGL'} if selection_date in DATES[:10] else set()),'Unexpected forward cell impact')
    require(audit['forward_affected']==bool(affected),'False affected flag')
    expected_count=24575 if selection_date in DATES[:11] else 12287
    require(len(definitions)==expected_count==len(original['evaluation']['records'])==audit['record_count']
        ==report['original_equal_record_denominator'],'Complete date denominator differs')
    require(len({tuple(combo) for combo in definitions})==expected_count,'Duplicate definition')
    old_records=original['evaluation']['records'];evaluation=report['evaluation']
    if not affected:
        require(evaluation is None and report['mode']=='OLD_EQUAL_RECORDS_REFERENCED_ALL_FORWARD_INPUTS_UNCHANGED',
            'Unchanged equal date should only reference old report')
        require(report['historical_numerical_delta_performed'] is False,'False reevaluation claim')
        rows=old_records
    else:
        require(evaluation is not None and evaluation['count']==expected_count==len(evaluation['records']),
                'Incomplete revised records')
        require(report['mode']=='REEVALUATED_THREE_DECLARED_CELL_INPUT'
            and report['historical_numerical_delta_performed'] is True,'Incorrect changed-input evaluation role')
        rows=evaluation['records']
        for key,value in original['evaluation'].items():
            if key not in ('records','source_hashes'):require(evaluation[key]==value,'Evaluation metadata changed')
    for combo,old,new in zip(definitions,old_records,rows):
        require(old['tickers']==new['tickers']==';'.join(combo),'Combination order differs')
        require(set(old)==set(new),'Record schema differs')
        for key in old:
            if key!='fractional_metrics':require(old[key]==new[key],'Risk/identity/denominator field changed')
        a=old['fractional_metrics'];b=new['fractional_metrics'];require(set(a)==set(b),'Metric schema differs')
        allowed=set(METRICS) if affected & set(combo) else {key for key in METRICS if key.startswith('paired_')}
        if not affected:allowed=set()
        for key in a:
            require(type(b[key]) in (int,float) and math.isfinite(b[key]),'Invalid numeric metric')
            if key not in allowed:require(a[key]==b[key],'Nondependent metric/fee changed: '+key)
    by_combo={tuple(row['tickers'].split(';')):row for row in rows}
    checks=[];maximum=0.
    for combo in samples:
        expected_metrics,turnover,fee=scalar_metrics(inputs,combo)
        actual=by_combo[combo]['fractional_metrics'];errors={key:abs(expected_metrics[key]-actual[key]) for key in METRICS}
        require(max(errors.values())<=1e-11,'Independent scalar economic metric differs: '+';'.join(combo))
        require(abs(actual['initial_turnover']-turnover)<=1e-14 and abs(actual['initial_transaction_cost']-fee)<=1e-14,
                'Independent initial fee/turnover differs')
        maximum=max(maximum,max(errors.values()))
        checks.append(dict(tickers=list(combo),holding_count=len(combo),metric_count=13,maximum_absolute_error=max(errors.values())))
    require(report['promotion_allowed'] is False and report['point_in_time_verified'] is False
        and report['ranking_or_promotion_performed'] is False,'Research boundary changed')
    verify_sources(sources)
    require(hashlib.sha256(path.read_bytes()).hexdigest()==report_sha,'Output changed during independent audit')
    return dict(selection_date=selection_date,coordinate=report['coordinate'],path=str(path),sha256=report_sha,
        record_count=expected_count,mode=report['mode'],all_record_nondependent_fields_verified=True,
        exactly_three_input_changes_verified=True,forward_affected_tickers=sorted(affected),
        scalar_sample_rule=RULE,scalar_samples=checks,scalar_sample_count=len(checks),
        scalar_metric_comparison_count=13*len(checks),maximum_scalar_absolute_error=maximum,
        source_file_count=len(sources),source_closure_verified=True,
        historical_evaluator_called=False,training_rerun=False,promotion_allowed=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection-date',action='append',choices=DATES)
    parser.add_argument('--output',required=True);args=parser.parse_args()
    output=Path(args.output).resolve()
    require((ROOT/'data/cache/research').resolve() in output.parents,'Research output only')
    if output.exists():raise FileExistsError(output)
    dates=args.selection_date or [day for day in DATES if (DIRECTORY/('equal_delta_'+day.replace('-','')+'.json')).exists()]
    require(bool(dates) and len(set(dates))==len(dates),'Unique explicit observed dates required')
    rows=[]
    for day in sorted(dates):
        row=verify_date(day);rows.append(row)
        print(json.dumps(dict(date=day,count=row['record_count'],samples=row['scalar_sample_count'],
            maximum_error=row['maximum_scalar_absolute_error'])),flush=True)
    report=dict(schema='ndx_evidenced_split_equal_delta_independent_inventory_v1',dates=rows,
        verified_date_count=len(rows),expected_date_count=15,verified_equal_record_count=sum(row['record_count'] for row in rows),
        expected_equal_record_count=319473,all_fifteen_dates_verified=sorted(dates)==list(DATES),
        missing_dates=sorted(set(DATES)-set(dates)),sample_rule=RULE,
        sample_selection_uses_performance=False,scalar_check_is_not_all_record_economic_recalculation=True,
        source_hashes={str(SOURCE):SOURCE_SHA,str(INVENTORY):INVENTORY_SHA,**{row['path']:row['sha256'] for row in rows}},
        training_or_historical_evaluator_called=False,point_in_time_verified=False,promotion_allowed=False)
    verify_sources(report['source_hashes']);raw=(json.dumps(report,sort_keys=True,indent=2,allow_nan=False)+'\n').encode()
    output.parent.mkdir(parents=True,exist_ok=True)
    with output.open('xb') as stream:stream.write(raw)
    require(output.read_bytes()==raw,'Independent inventory readback differs')
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest())),flush=True)


if __name__=='__main__':main()
