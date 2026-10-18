"""Independent candidate saved-risk reader. Does not load either producer pure."""
import argparse,hashlib,json,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/candidate_saved_risk_diagnostic_20261008_v1'
OUTPUT=ROOT/'data/cache/research/candidate_saved_risk_diagnostic_independent_readback_20261008_v1'
IO=ROOT/'scripts/ndx_candidate_saved_risk_sources_20261008.py';IO_SHA='5636c4704906e0b74d8b9400627de1d9b2ab74f2808550cdb0ccf24c08c86a75'
CHECKER=ROOT/'backtest/ndx_candidate_saved_risk_inspection_research.py';CHECKER_SHA='635fd2c45db38fdaacc54b4ce3960e9071fa5f2748f9b6e065419ae2eed35350'
PUBLISHER=ROOT/'scripts/ndx_candidate_saved_risk_diagnostic_20261008.py';PUBLISHER_SHA='16374646f4b5678a70a43a3000321bae9cdd5697dd2cfde39907176005b56d1d'
DIAGNOSTIC=ROOT/'backtest/ndx_saved_holdings_risk_diagnostic_research.py';DIAGNOSTIC_SHA='34dd4482b1480881faa06f45850d348d893d2f9031285ee5ec24ddabfd7f361e'
PROJECTION=ROOT/'backtest/ndx_candidate_daily_risk_projection_research.py';PROJECTION_SHA='ed5e6eeb72b5f68d02a2712224d9816b430d82c090d60e8fc91fa4891eb6aa97'
RESULT_SHA='3f09e4da2697ceb73880aaf83882ad8f68a3cfbd1b0ec711ba358f5d264546b8';PUBLICATION_SHA='e4e8e036a3bd52887ef324798164f24a3491b620209787496b5b647c7d002bbc'
BOUND={'inputs': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_inputs_20261003_v1\\inputs.json', 'c3311e2e9aea24c96c695e5a860f6ecd784356bbc8995657f1e13061de0ff4b9'), 'inputs_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_inputs_20261003_v1\\publication.json', '64c301cd36c9274f345997a2adb6ba67eb46ce824d8190865b4578441afca940'), 'inputs_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_inputs_independent_readback_20261003_v1\\independent_readback.json', '8568bbe2ea6fa33d2aa9956a72a8b11d902f353b6078044a9a832384ec0886fb'), 'inputs_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_account_inputs_independent_readback_20261003.py', '85f3fd668a948bf9b3e68f1d4c013ee6def02d806f57373c41ef65698443576d'), 'execution': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_execution_20261003_v1\\result.json', 'c79aafa533d78be14f888cd109d9942702c829c39d5ce0d09904501b5c812870'), 'execution_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_execution_20261003_v1\\publication.json', 'e1b00c1c1f8e4b4d31893e77ba46bc12009ba3e5fd452fdca1b1b01266ab68c7'), 'execution_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_account_execution_independent_readback_20261003_v1\\independent_readback.json', '33ebcb571c81793f92070c8db789b409b98eca139778c0c192c80fa6abcc74bb'), 'execution_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_account_execution_independent_readback_20261003.py', '69c54a144ca582a8537a4c52b0fbb6fdf61a0f2ece0d4233206cc87f6f729ca2')}
FLAGS=dict.fromkeys(('original_saved_risk','order_gate_evaluated','account_executed','point_in_time_verified','promotion_allowed','historical_label_validity_verified','source_bytes_authenticated','automatic_retry_allowed'),False)


def module(path,sha):
    raw=Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Bound independent code')
    value=types.ModuleType('_independent_saved_risk_'+Path(path).stem);value.__file__=str(path)
    exec(compile(raw,str(path),'exec'),value.__dict__);return value


def run(*,execute=False):
    if execute is not True:raise ValueError('Explicit independent diagnostic readback')
    for sha in (IO_SHA,CHECKER_SHA,PUBLISHER_SHA,DIAGNOSTIC_SHA,PROJECTION_SHA,RESULT_SHA,PUBLICATION_SHA,*(item[1]for item in BOUND.values())):
        if type(sha)is not str or len(sha)!=64 or set(sha)-set('0123456789abcdef'):raise ValueError('Pending immutable source pin')
    io=module(IO,IO_SHA);io.safe(OUTPUT);io.require(not OUTPUT.exists(),'Create-only independent readback')
    refs={key:io.reference(*value)for key,value in BOUND.items()};prepared=io.prepare(refs)
    sources=prepared['sources'];expected_sources=dict(sources)
    for path,sha in ((PUBLISHER,PUBLISHER_SHA),(DIAGNOSTIC,DIAGNOSTIC_SHA),(PROJECTION,PROJECTION_SHA)):
        io.load(io.reference(str(path),sha),sources,body=False);expected_sources[str(path)]=sha
    resultref=io.reference(str(PARENT/'diagnostics.json'),RESULT_SHA);pubref=io.reference(str(PARENT/'publication.json'),PUBLICATION_SHA)
    result=io.load(resultref,sources);pub=io.load(pubref,sources)
    io.require(result['schema']=='CANDIDATE_SAVED_RISK_DIAGNOSTIC_DOCUMENT_V1'and pub['schema']=='CANDIDATE_SAVED_RISK_DIAGNOSTIC_PUBLICATION_V1','Original derived role')
    io.require(pub['status']=='PUBLISHED_DERIVED_DIAGNOSTIC_NOT_ORIGINAL_RISK_PENDING_READBACK','No original risk promotion')
    io.exact(pub['diagnostics_reference'],resultref);io.exact(pub['started_reference'],result['started_reference'])
    io.exact(result['started_reference']['path'],str(PARENT/'started.json'));start=io.load(result['started_reference'],sources)
    io.require(start['schema']=='CANDIDATE_SAVED_RISK_DIAGNOSTIC_STARTED_V1','Original diagnostic START')
    for value in (result,pub,start):
        io.exact(value['input_references'],refs);io.exact(value['source_hashes'],expected_sources)
        for name in FLAGS:io.require(value[name]is False,'Exact derived-only permission boundary')
    io.exact(result['source_inventories'],prepared['inventories']);io.exact(result['blocked_track_indices'],prepared['blocked_track_indices'])
    io.exact(result['original_audit_started_references'],prepared['observed_audit_started_references'])
    io.require(result['original_audit_starts_externally_anchored']is False,'Honest original START anchoring scope')
    io.require(result['derived_diagnostic_computed']is True and result['independent_readback_status']=='PENDING','Independent derived diagnostic status')
    io.load(io.reference(str(SOURCE),LOADED),sources,body=False);checker=module(CHECKER,CHECKER_SHA)
    io.load(io.reference(str(CHECKER),CHECKER_SHA),sources,body=False)
    inventories={**prepared['inventories'],str(PARENT):[str(PARENT/name)for name in ('started.json','diagnostics.json','publication.json')]}
    guard=lambda:io.guard(sources,inventories,prepared['lineage_helper'])
    guard();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started=io.save(OUTPUT/'started.json',dict(schema='CANDIDATE_SAVED_RISK_INDEPENDENT_STARTED_V1',diagnostics_reference=resultref,publication_reference=pubref,source_hashes=sources,**FLAGS))
        inspection=checker.inspect(prepared['paths'],result['paths'])
        for key in ('path_count','path_day_count','numeric_day_count','undefined_all_cash_day_count'):io.exact(result[key],inspection[key])
        io.require(inspection['numeric_day_count']==476 and inspection['undefined_all_cash_day_count']==4,'Exact original 480 positions')
        guard()
        report=io.save(OUTPUT/'independent_readback.json',dict(schema='CANDIDATE_SAVED_RISK_DIAGNOSTIC_INDEPENDENT_READBACK_V1',status='PASS',diagnostics_reference=resultref,publication_reference=pubref,started_reference=started,
            reader_sha256=LOADED,inspection=inspection,input_references=refs,source_hashes=sources,source_inventories=inventories,**FLAGS))
        guard();io.require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Exact independent namespace')
        for item in (started,report):io.require(io.sha(Path(item['path']).read_bytes())==item['sha256'],'Final independent bytes')
        return report
    except BaseException as error:
        io.save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true')
    print(json.dumps(run(execute=parser.parse_args().execute)))
