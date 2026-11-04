"""One bounded compilation of pre-inventoried zero-event frontier pairs, no replay."""
import json,time,hashlib
from copy import deepcopy
from pathlib import Path
from extend_risk_budget_pairs_20261105 import PairCompiler,ROOT,PARENT,PARENT_SHA


def main():
    started=time.monotonic();compiler=PairCompiler()
    inventory_path='tmp/risk_budget_pair_extension_20261105/frontier_local_inventory.json'
    inventory=compiler.read(inventory_path)
    for name,expected in inventory['source_hashes'].items():compiler.verify(name,expected)
    eligible=[r for r in inventory['rows'] if r['status']=='COMPLETE_LOCAL_NO_REPORTED_EVENT_WINDOW']
    assert len(eligible)==2729
    extension=deepcopy(compiler.parent)
    rows={(r['window'],r['decision_date']):r for r in extension['windows']}
    pairs=[]
    for requested in eligible:
        label,date,sid=requested['window'],requested['date'],requested['security_id']
        result=compiler.compile_pair(label,date,sid)
        assert result['status']=='CONDITIONAL_INPUT_READY' and result['basis']=='COMPLETE_LOCAL_NO_REPORTED_EVENT_WINDOW'
        row=rows[(label,date)];assert sid not in row['arguments']['stock_gross_returns']
        row['arguments']['stock_gross_returns'][sid]=result['gross']
        evidence=dict(window=label,decision_date=date,security_id=sid,**{k:v for k,v in result.items() if k!='gross'})
        row.setdefault('extension_pair_evidence',[]).append(evidence);pairs.append(evidence)
    extension['parent_artifact']=dict(path=PARENT,sha256=PARENT_SHA)
    extension['extension_scope']='Exactly2729 preinventoried zero-event pairs. Original target/equity/QQQ remain unchanged; dynamic caller supplies current account. Eventful or unreviewed pairs are not admitted.'
    extension['source_hashes'].update(compiler.pins)
    for path in [Path(__file__),ROOT/'scripts/research/extend_risk_budget_pairs_20261105.py']:
        extension['source_hashes'][path.relative_to(ROOT).as_posix()]=hashlib.sha256(path.read_bytes()).hexdigest()
    out=ROOT/'tmp/risk_budget_pair_extension_20261105'
    path=out/'risk_inputs_zero_event_frontier_v1.json'
    path.write_text(json.dumps(extension,indent=2),encoding='utf8')
    report=dict(status='BOUNDED_ZERO_EVENT_FRONTIER_COMPILED',parent=extension['parent_artifact'],
                artifact_path=path.relative_to(ROOT).as_posix(),artifact_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                added_pairs=len(pairs),original_pairs=113,pairs=pairs,elapsed_seconds=time.monotonic()-started,
                source_hashes=extension['source_hashes'],network_calls=0,economic_runs=0)
    (out/'zero_event_compilation_report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k not in ('pairs','source_hashes')}))

if __name__=='__main__':main()
