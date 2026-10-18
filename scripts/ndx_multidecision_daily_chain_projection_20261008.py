"""Pending publication of complete daily saved/derived chain projection."""
import argparse,hashlib,json,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/multidecision_daily_chain_projection_20261008_v1'
IO=ROOT/'scripts/ndx_multidecision_daily_chain_sources_20261008.py';IO_SHA='2ace30756471b562699a16bad76d900163729c80072f12f7496a4ea1b537d084'
PURE=ROOT/'backtest/ndx_multidecision_daily_chain_projection_research.py';PURE_SHA='db647694a82f1f160900c6eb7f7ab2933116d5976ee8c7274f5fa35016f25bad'
AGGREGATOR=ROOT/'backtest/ndx_saved_chain_weight_aggregation_research.py';AGGREGATOR_SHA='c0a5428973df1f8227f03fe822a4d7b0f64fc790ce48bb11120ea274947a2b40'
BOUND={'supplement': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_holdings_supplement_20261008_v1\\supplement.json', 'dc23f888b033ada98b34357c960980ca0a02eecfbaeaca40a259155adf0bf8ae'), 'supplement_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_holdings_supplement_20261008_v1\\publication.json', '889733dc35d83cf551b14a9abffdc0eb585d92df57d8d990234441bb106e6fc6'), 'supplement_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_holdings_supplement_independent_readback_20261008_v1\\independent_readback.json', '50dc78b3cfb6f27ad8a59a0a2b107b0ac33956956721ba20dd643e98defde52d'), 'supplement_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_holdings_supplement_independent_readback_20261008.py', 'b44686e6c8a5992087966fed1501ff35ebd031707ac16f33e9f28c7292550db4'), 'diagnostics': ('E:\\Git\\us_ratchet\\data\\cache\\research\\candidate_saved_risk_diagnostic_20261008_v1\\diagnostics.json', '3f09e4da2697ceb73880aaf83882ad8f68a3cfbd1b0ec711ba358f5d264546b8'), 'diagnostics_publication': ('E:\\Git\\us_ratchet\\data\\cache\\research\\candidate_saved_risk_diagnostic_20261008_v1\\publication.json', 'e4e8e036a3bd52887ef324798164f24a3491b620209787496b5b647c7d002bbc'), 'diagnostics_audit': ('E:\\Git\\us_ratchet\\data\\cache\\research\\candidate_saved_risk_diagnostic_independent_readback_20261008_v1\\independent_readback.json', '58dd8d0c5a4bbf89a993821ab1631d471ede1256e700824bcfd3b2c1fdd675b9'), 'diagnostics_reader': ('E:\\Git\\us_ratchet\\scripts\\ndx_candidate_saved_risk_diagnostic_independent_readback_20261008.py', '80a32eccce1ffd06a03d4cb59da6b3fa618ed7aafd08f768f9912e36ddc694b5')}
FLAGS=dict.fromkeys(('account_executed','risk_gate_recomputed','normalization_performed','point_in_time_verified','promotion_allowed','source_bytes_authenticated','historical_label_validity_verified','full_h_delivery_complete','automatic_retry_allowed'),False)


def module(path,digest):
    if type(digest)is not str or len(digest)!=64 or set(digest)-set('0123456789abcdef'):raise ValueError('Pending immutable source pin')
    blob=path.read_bytes()
    if hashlib.sha256(blob).hexdigest()!=digest:raise ValueError('Source code bytes')
    value=types.ModuleType('_daily_chain_'+path.stem);value.__file__=str(path);exec(compile(blob,str(path),'exec'),value.__dict__);return value


def run(*,execute=False):
    if execute is not True:raise ValueError('Explicit new chain publication')
    for digest in (IO_SHA,PURE_SHA,AGGREGATOR_SHA,*(v[1]for v in BOUND.values())):
        if type(digest)is not str or len(digest)!=64 or set(digest)-set('0123456789abcdef'):raise ValueError('Pending immutable source pin')
    io=module(IO,IO_SHA);io.safe(OUTPUT);io.require(not OUTPUT.exists(),'Create-only no retry')
    refs={key:io.reference(*value)for key,value in BOUND.items()};prepared=io.prepare(refs);sources=prepared['sources']
    for path,digest in ((SOURCE,LOADED),(PURE,PURE_SHA),(AGGREGATOR,AGGREGATOR_SHA)):io.load(io.reference(str(path),digest),sources,False)
    pure=module(PURE,PURE_SHA);aggregator=module(AGGREGATOR,AGGREGATOR_SHA)
    guard=lambda:io.guard(sources,prepared['inventories'],prepared['helper'])
    guard();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        start=io.save(OUTPUT/'started.json',dict(schema='MULTIDECISION_DAILY_CHAIN_STARTED_V1',input_references=refs,source_hashes=sources,**FLAGS))
        projection=pure.build_chain_projection(supplement_document=prepared['documents']['supplement'],diagnostics_document=prepared['documents']['diagnostics'],references={key:refs[key]for key in ('supplement','diagnostics')},aggregate_saved_weights=aggregator.aggregate_saved_weights)
        guard()
        result=io.save(OUTPUT/'projection.json',dict(schema='MULTIDECISION_DAILY_CHAIN_DOCUMENT_V1',projection=projection,input_references=refs,source_hashes=sources,source_inventories=prepared['inventories'],started_reference=start,
            original_audit_started_references=prepared['observed_audit_starts'],original_audit_starts_externally_anchored=False,independent_readback_status='PENDING',new_saved_weight_chain_addition_performed=True,**FLAGS))
        guard()
        pub=io.save(OUTPUT/'publication.json',dict(schema='MULTIDECISION_DAILY_CHAIN_PUBLICATION_V1',status='PUBLISHED_MIXED_BASIS_CHAIN_PROJECTION_PENDING_READBACK',projection_reference=result,started_reference=start,input_references=refs,source_hashes=sources,**FLAGS))
        guard();io.require({p.name for p in OUTPUT.iterdir()}=={'started.json','projection.json','publication.json'},'Exact output inventory')
        for ref in (start,result,pub):io.require(io.sha(Path(ref['path']).read_bytes())==ref['sha256'],'Output bytes drift')
        return result
    except BaseException as error:
        io.save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
