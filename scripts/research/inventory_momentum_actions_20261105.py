"""Potential action exposure only; one-share markers are never economic quantities."""
import argparse
import importlib.util
import json
import sys
from collections import Counter
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from docs.candidates.downside_bounded_execution_supplement_20261105 import extend_execution_evidence
from docs.candidates.downside_absence_artifact_20261105 import append_execution_artifact
from scripts.run_recent_continuous_probe import exposed_action_blockers
from scripts.assemble_old_continuous_inputs_v1 import exposure_gate
from scripts.run_old_continuous_probe_v4 import admit_reviewed_dividends,admit_period_absence
PINS={}


def require(ok,reason):
    if not ok:raise ValueError(reason)


def bind(pins):
    for name,digest in pins.items():
        path=(ROOT/name).resolve();require(path.is_relative_to(ROOT),'PATH_SCOPE')
        require(sha256(path.read_bytes()).hexdigest()==digest,'SOURCE_CHANGED:'+name)
        canonical=path.relative_to(ROOT).as_posix()
        require(canonical not in PINS or PINS[canonical]==digest,'PIN_CONFLICT:'+name)
        PINS[canonical]=digest


def read(name):
    path=(ROOT/name).resolve();raw=path.read_bytes();bind({path.relative_to(ROOT).as_posix():sha256(raw).hexdigest()})
    return json.loads(raw)


def inputs(window,freeze):
    late=window=='2024_2026'
    baseline='old_continuous_baseline_20261026_v9' if late else 'recent_continuous_baseline_20261026_v7'
    price_name='old_window_execution_prices_20261026' if late else 'recent_execution_prices_20261026'
    document=read('tmp/'+baseline+'/execution_inputs.json')
    prior=read('tmp/trend_'+window+'_20261026_v1/execution_inputs.json');review=deepcopy(prior['action_review'])
    require(prior['baseline_execution_inputs']==document,'BASELINE_INPUT_BINDING')
    price_path='tmp/'+price_name+'/execution_prices_v1.json';prices=read(price_path)
    require(PINS[price_path]==prior['execution_input_hashes']['prices'],'PRICE_PIN')
    for pins in (document['source_hashes'],document['assembled']['source_hashes'],document.get('action_source_hashes',{}),review['source_hashes'],prices.get('source_hashes',{})):bind(pins)
    supplemental=read('tmp/equal_four_20261105/source_review/admitted_supplement.json');bind(supplemental['source_hashes'])
    review['rows'].extend(deepcopy(supplemental['review_rows'][window]));document['dividend_events'].extend(deepcopy(supplemental['dividend_events'][window]))
    document,review,pins,audit=extend_execution_evidence(root=ROOT,document=document,prices=prices,review=review);bind(pins)
    legacy=proof=None
    if late:
        for name in freeze['additional_execution_artifacts']:
            require(name in freeze['source_hashes'],'ARTIFACT_FREEZE_PIN')
            artifact=read(name);bind(artifact['source_hashes']);append_execution_artifact(document,review,artifact)
        path='tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py'
        bind({path:'2016ac8bfc802ae3042bd7592e3a897bcb0568c88a79161a8de05d58dc8f3aa5'})
        spec=importlib.util.spec_from_file_location('momentum_inventory_legacy',ROOT/path)
        legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)
        proof=legacy.certify(ROOT,document['assembled']['session_dates']);bind(proof['source_hashes'])
    return document,prices,review,legacy,proof


def run(roster_path,output):
    roster=read(roster_path)
    require(roster['status']=='STATIC_RANKING_COMPLETE_NOT_ACCOUNT_BACKTEST','ROSTER_STATUS')
    require(PINS[Path(roster_path).as_posix()]=='5523b8d87e08a8946cf6d2e15aa28fb8f13b3608ef5bde012220f825979aaf3c','FIXED_ROSTER_SHA')
    bind(roster['prior_expected_hashes_verified']);bind(roster['selection_artifact_hashes'])
    bind({'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json':roster['archive_manifest_sha256'],
          'scripts/research/preflight_cross_sectional_momentum_20261105.py':roster['script_sha256']})
    freeze=read('research_contracts/downside_max10_resume_v9_20261105/freeze.json');bind(freeze['source_hashes'])
    rows=roster['rows'];require(len(rows)==67,'67_ROSTERS_REQUIRED')
    result=[];unique={}
    for window,count in [('2021_2023',36),('2024_2026',31)]:
        document,prices,review,legacy,proof=inputs(window,freeze)
        dates=document['assembled']['session_dates'];plans=document['assembled']['monthly_inputs']
        selected_rows=sorted([r for r in rows if r['window']==window],key=lambda r:r['decision_date'])
        require(len(selected_rows)==count and [r['decision_date'] for r in selected_rows]==[p['decision_date'] for p in plans],'EXACT_MONTH_GRID')
        previous=set()
        for index,row in enumerate(selected_rows):
            day=row['decision_date'];active=dates[dates.index(day)+1]
            until=selected_rows[index+1]['decision_date'] if index+1<len(selected_rows) else dates[-1]
            ranking={r['security_id'] for r in row['selected']};require(len(ranking)==10,'TEN_RANKED_SIDS')
            on=row['gate']['risk_on'];require(type(on) is bool,'EXPLICIT_GATE')
            targets=ranking if on else set()
            args=dict(decision_date=day,account_state=dict(shares={sid:1 for sid in sorted(previous)}))
            selected=dict(target_quantities={sid:1 for sid in sorted(targets)})
            if window=='2021_2023':
                raw=exposed_action_blockers(args,selected,until,prices,None,active,())
                gate=exposed_action_blockers(args,selected,until,prices,review,active,document['dividend_events'])
            else:
                raw=exposure_gate(document,args,selected,until,active)
                gate=admit_reviewed_dividends(raw,review,document['dividend_events'])
                gate=admit_period_absence(gate,review);gate=legacy.admit(gate,proof)
            # Never pass artificial one-share positions to identity liquidation admission.
            record=dict(window=window,decision_date=day,active_date=active,through=until,market_risk_on=on,
                        ranked_sids=sorted(ranking),previous_potential_sids=sorted(previous),new_potential_sids=sorted(targets),
                        raw_gate=raw,reviewed_inventory=gate,scope='POTENTIAL_EXPOSURE_NOT_ECONOMIC_ADMISSION')
            result.append(record)
            for kind in ('unmapped_events','missing_action_streams'):
                for event in gate[kind]:
                    key=json.dumps([window,kind,event],sort_keys=True)
                    item=unique.setdefault(key,dict(window=window,category=kind,event=event,decision_dates=[]))
                    item['decision_dates'].append(day)
            previous=targets
    # Also bind the actual executed helper code; frozen dependencies are retained above.
    for path in [Path(__file__),ROOT/'docs/candidates/downside_bounded_execution_supplement_20261105.py',ROOT/'docs/candidates/downside_absence_artifact_20261105.py']:
        bind({path.relative_to(ROOT).as_posix():sha256(path.read_bytes()).hexdigest()})
    bind(dict(PINS))
    report=dict(status='ACTION_SCOPE_INVENTORY_NOT_ECONOMIC_ADMISSION',rows=result,unique_remaining=list(unique.values()),
                summary={w:dict(months=sum(r['window']==w for r in result),months_without_inventory_blockers=sum(r['window']==w and r['reviewed_inventory']['admitted'] for r in result),
                                cash_target_months=sum(r['window']==w and not r['market_risk_on'] for r in result)) for w in ('2021_2023','2024_2026')},
                source_hashes=PINS,limitations=['One share is a scope marker, not affordability or actual quantity.',
                'Previous monthly targets may overstate holdings after original 20pct exits.',
                'Pending or failed sales and corporate identity changes require actual account gates.',
                'No artificial identity liquidation admission; split/merger/conversion remain explicit blockers.',
                'Reviewed inventory does not establish point-in-time completeness or economic feasibility.'])
    out=(ROOT/output).resolve();require(out.is_relative_to(ROOT/'tmp'),'TMP_OUTPUT_ONLY');out.mkdir(parents=True,exist_ok=False)
    (out/'inventory.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(dict(status=report['status'],summary=report['summary'],unique_remaining=len(unique))))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--roster',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args();run(args.roster,args.output)
