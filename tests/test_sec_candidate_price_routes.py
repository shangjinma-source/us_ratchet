import json
from pathlib import Path
from scripts.build_sec_candidate_price_routes import build


def test_routes_keep_missing_identity_and_finite_boundaries(tmp_path):
    def save(path,data):
        target=tmp_path/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(data))
    save('tmp/bull_bear_membership_diagnostic_20261025_v1/sec_company_identity_leads.json',dict(rows=[dict(candidate_historical_ticker=t) for t in ['MNST','MISSING','JAVA']]))
    save('tmp/github_history_routes_20261025/wiki_coverage.json',dict(coverage={'MNST':dict(first='1995-01-01',last='2018-01-01')}))
    save('tmp/github_history_routes_20261025/yahoo_foreign_probe/manifest.json',[])
    target=tmp_path/'tmp/legacy_three_probe_20261025/JAVA.csv';target.parent.mkdir(parents=True)
    target.write_text('Date,Open,High,Low,Close\n2007-01-03,1,2,1,2\n2011-01-03,nan,nan,nan,nan\n')
    result=build(tmp_path);rows=result['records']
    assert not rows[0]['price_routes']  # Beverage MNST is not Monster Worldwide.
    assert not rows[1]['price_routes']
    assert rows[2]['price_routes'][0]['finite_last']=='2007-01-03'
    assert result['no_candidate_route']==['MNST','MISSING']
