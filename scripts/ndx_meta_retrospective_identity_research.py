"""Create-only real META full-history projection and two bounded rename scenarios."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_meta_retrospective_identity_research as meta


def build_report():
    projection=meta.build_bound_projection()
    def scenario(decisions):
        schedule=[dict(decision_date=day,execution_date=execution,
            targets={meta.SID:dict(issuer_id=meta.ISSUER,ticker='FB' if day<'2022-06-09' else 'META',target_weight=1.)})
            for day,execution in decisions]
        calendar=[day for day in projection['calendar'] if decisions[0][0]<=day<=decisions[-1][1]]
        return meta.simulate_bound_meta(projection=projection,schedule=schedule,calendar=calendar)
    across=scenario([('2022-06-08','2022-06-09'),('2022-06-13','2022-06-14')])
    between=scenario([('2022-06-07','2022-06-08'),('2022-06-10','2022-06-13')])
    sources=dict(projection['source_hashes'])
    for result in (across,between):meta.merge(sources,result['source_hashes'])
    path=Path(__file__).resolve();sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    meta.nominal.verify(sources)
    return dict(schema='ndx_meta_retrospective_identity_scenarios_v1',projection=projection,
        decision_to_fill_rename=across,between_decisions_rename=between,source_hashes=sources,
        source_scope='REAL_PROVIDER_PRICES_DATED_NASDAQ_RENAME_CONDITIONAL_RESEARCH',
        live_execution_performed=False,research_execution_performed=True,old_training_rerun=False,
        point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    output=ROOT/'data/cache/research/meta_historical_price_source_probe_20260912_v1/retrospective_identity_scenarios_20260912.json'
    if output.exists():raise FileExistsError(output)
    report=build_report();raw=(json.dumps(report,indent=2,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n').encode()
    meta.nominal.verify(report['source_hashes'])
    with output.open('xb') as handle:handle.write(raw)
    meta.nominal.verify(report['source_hashes'])
    print(json.dumps(dict(path=str(output),sha256=hashlib.sha256(raw).hexdigest())))
