"""Pending complete workbook from four already audited evidence families."""
import argparse,hashlib,json,subprocess,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/multidecision_h_workbook_20261008_v3'
IO=ROOT/'scripts/ndx_multidecision_daily_chain_sources_20261008.py';IO_SHA='2ace30756471b562699a16bad76d900163729c80072f12f7496a4ea1b537d084'
PURE=ROOT/'backtest/ndx_multidecision_h_workbook_display_v2_research.py';PURE_SHA='4c729d9af7719179c41ace6850a41b0155eda8d52b4e40ff31d12357d5459746'
DISPLAY_CHECKER=ROOT/'backtest/ndx_multidecision_h_workbook_display_inspection_v2_research.py';DISPLAY_CHECKER_SHA='25b2b334fae6ae328591cd7f8c39312aae87150980af2fee57f2133f87c0a337'
CELL_CHECKER=ROOT/'scripts/ndx_multidecision_h_workbook_inspection_v2_20261008.py';CELL_CHECKER_SHA='724d5bd11ae0b177a65d19ecbb2745c8c70589b4967abf6f16bfc70cd296b23b'
CHART_CHECKER=ROOT/'scripts/ndx_multidecision_h_chart_inspection_v2_20261008.py';CHART_CHECKER_SHA='580973fa1a5eb986b5643d47ca2222ac7b4f6f28f09bcb62778044ffc568ca0c'
BUILDER=ROOT/'scripts/ndx_multidecision_h_workbook_v2_20261008.mjs';BUILDER_SHA='e0f8d4a78d7b80686f910568717df8ea552392360cecfcbf04474be6da470de5'
NODE=Path(r'C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe')
MODULES=ROOT/'tmp/multidecision_h_workbook_runtime_20261008/node_modules'
BOUND={
    'presentation':('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_path_presentation_20261008_v1\\presentation.json','e724a501254b9685144a1c1c98011ae1f248d2e584983c0071de6e9cde2c2782'),
    'presentation_publication':('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_path_presentation_20261008_v1\\publication.json','cd7d75b84154e5004aadb6d4d660566b68dd99384e0b6ec706c8cbe76b02008e'),
    'presentation_audit':('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_path_presentation_independent_readback_20261008_v1\\independent_readback.json','6eed128ffcdd3a320ea06ca8cdaacd18b8bed2d96d02bbe8967b4773898a56e6'),
    'presentation_reader':('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_path_presentation_independent_readback_20261008.py','64d872ceb39fdc4218438b6d63eaccea77880499872f164846942dbc6705afb9'),
    'supplement':('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_holdings_supplement_20261008_v1\\supplement.json','dc23f888b033ada98b34357c960980ca0a02eecfbaeaca40a259155adf0bf8ae'),
    'supplement_publication':('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_holdings_supplement_20261008_v1\\publication.json','889733dc35d83cf551b14a9abffdc0eb585d92df57d8d990234441bb106e6fc6'),
    'supplement_audit':('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_holdings_supplement_independent_readback_20261008_v1\\independent_readback.json','50dc78b3cfb6f27ad8a59a0a2b107b0ac33956956721ba20dd643e98defde52d'),
    'supplement_reader':('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_holdings_supplement_independent_readback_20261008.py','b44686e6c8a5992087966fed1501ff35ebd031707ac16f33e9f28c7292550db4'),
    'diagnostics':('E:\\Git\\us_ratchet\\data\\cache\\research\\candidate_saved_risk_diagnostic_20261008_v1\\diagnostics.json','3f09e4da2697ceb73880aaf83882ad8f68a3cfbd1b0ec711ba358f5d264546b8'),
    'diagnostics_publication':('E:\\Git\\us_ratchet\\data\\cache\\research\\candidate_saved_risk_diagnostic_20261008_v1\\publication.json','e4e8e036a3bd52887ef324798164f24a3491b620209787496b5b647c7d002bbc'),
    'diagnostics_audit':('E:\\Git\\us_ratchet\\data\\cache\\research\\candidate_saved_risk_diagnostic_independent_readback_20261008_v1\\independent_readback.json','58dd8d0c5a4bbf89a993821ab1631d471ede1256e700824bcfd3b2c1fdd675b9'),
    'diagnostics_reader':('E:\\Git\\us_ratchet\\scripts\\ndx_candidate_saved_risk_diagnostic_independent_readback_20261008.py','80a32eccce1ffd06a03d4cb59da6b3fa618ed7aafd08f768f9912e36ddc694b5'),
    'chain':('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_daily_chain_projection_20261008_v1\\projection.json','cbf024b500c301111d993f6c3e4abe29421d07a5a1fe4bd41a62dab5bcb190ed'),
    'chain_publication':('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_daily_chain_projection_20261008_v1\\publication.json','9061a6c61b7a445a5c45466cc87a095e0dfd485de986edee3cacdc72486d7f3a'),
    'chain_audit':('E:\\Git\\us_ratchet\\data\\cache\\research\\multidecision_daily_chain_independent_readback_20261008_v1\\independent_readback.json','b57eabcb716d7dc1d82d7d991ad890a755c56f8818458db2661bf563a2eaaa7f'),
    'chain_reader':('E:\\Git\\us_ratchet\\scripts\\ndx_multidecision_daily_chain_independent_readback_20261008.py','03354188cae5abd1797f93e95f58003fe965dc5e8f6b48eae083e782a4aff65d'),
}
FLAGS=dict.fromkeys(('account_executed','financial_recomputation_performed','point_in_time_verified','promotion_allowed','formal_comparison_passed','full_h_delivery_complete','runtime_binary_closure_verified','automatic_retry_allowed','visual_acceptance_passed'),False)


def module(path,digest):
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('Fixed source code bytes')
    value=types.ModuleType('_workbook_v2_'+path.stem);value.__file__=str(path);exec(compile(raw,str(path),'exec'),value.__dict__);return value


def prepare():
    for digest in (IO_SHA,PURE_SHA,DISPLAY_CHECKER_SHA,CELL_CHECKER_SHA,CHART_CHECKER_SHA,BUILDER_SHA,*(v[1]for v in BOUND.values())):
        if type(digest)is not str or len(digest)!=64 or set(digest)-set('0123456789abcdef'):raise ValueError('Pending immutable source pin')
    io=module(IO,IO_SHA);refs={key:io.reference(*value)for key,value in BOUND.items()}
    io.require(set(refs)=={r+s for r in ('presentation','supplement','diagnostics','chain')for s in ('','_publication','_audit','_reader')},'Four exact source families')
    lower={key:ref for key,ref in refs.items()if key.split('_')[0]in ('supplement','diagnostics')}
    prepared=io.prepare(lower);sources=prepared['sources'];inventories=prepared['inventories'];docs=prepared['documents'];observed=list(prepared['observed_audit_starts'])
    for role,prefix,field,status,published in [('presentation','MULTIDECISION_PATH_PRESENTATION','presentation','PASS_SAVED_EVIDENCE_PROJECTION','PUBLISHED_SAVED_EVIDENCE_PROJECTION_PENDING_INDEPENDENT_READBACK'),('chain','MULTIDECISION_DAILY_CHAIN','projection','PASS_MIXED_BASIS_DAILY_CHAIN_PROJECTION','PUBLISHED_MIXED_BASIS_CHAIN_PROJECTION_PENDING_READBACK')]:
        doc=io.load(refs[role],sources);pub=io.load(refs[role+'_publication'],sources);audit=io.load(refs[role+'_audit'],sources);io.load(refs[role+'_reader'],sources,False)
        io.require(doc['schema']==prefix+'_DOCUMENT_V1'and pub['schema']==prefix+'_PUBLICATION_V1'and audit['schema']==prefix+'_INDEPENDENT_READBACK_V1','Exact document roles')
        io.require(pub['status']==published and audit['status']==status,'Audited publication required')
        io.exact(pub[field+'_reference'],refs[role]);io.exact(audit[field+'_reference'],refs[role]);io.exact(audit['publication_reference'],refs[role+'_publication']);io.exact(audit['reader_sha256'],refs[role+'_reader']['sha256'])
        for value in (doc,pub,audit):
            io.require(value['point_in_time_verified']is False and value['promotion_allowed']is False,'Original authority')
            for name,digest in value['source_hashes'].items():io.merge(sources,io.reference(name,digest))
            for directory,names in value.get('source_inventories',{}).items():
                io.require(directory not in inventories or set(inventories[directory])==set(names),'Conflicting source inventory');inventories[directory]=names
        for key in (role,role+'_publication',role+'_reader'):io.require(audit['source_hashes'].get(refs[key]['path'])==refs[key]['sha256'],'Audited original source identity')
        parent=Path(refs[role]['path']).parent;io.exact(doc['started_reference'],pub['started_reference']);io.exact(doc['started_reference']['path'],str(parent/'started.json'))
        start=io.load(doc['started_reference'],sources);io.exact(start['source_hashes'],doc['source_hashes']);io.exact(start['input_references'],doc['input_references'])
        inventories[str(parent)]=[str(parent/name)for name in ('started.json',field+'.json','publication.json')]
        audit_parent=Path(refs[role+'_audit']['path']).parent;startref=io.reference(str(audit_parent/'started.json'),io.sha((audit_parent/'started.json').read_bytes()));astart=io.load(startref,sources);observed.append(startref)
        if role=='presentation':
            io.exact(astart['artifact_references']['presentation'],refs[role]);io.exact(astart['artifact_references']['publication'],refs[role+'_publication'])
        else:
            io.exact(audit['started_reference'],startref);io.exact(astart['projection_reference'],refs[role]);io.exact(astart['publication_reference'],refs[role+'_publication']);io.exact(doc['input_references'],lower)
        inventories[str(audit_parent)]=[str(audit_parent/name)for name in ('started.json','independent_readback.json')];docs[role]=doc
    for path,digest in ((SOURCE,LOADED),(PURE,PURE_SHA),(DISPLAY_CHECKER,DISPLAY_CHECKER_SHA),(CELL_CHECKER,CELL_CHECKER_SHA),(CHART_CHECKER,CHART_CHECKER_SHA),(BUILDER,BUILDER_SHA)):io.load(io.reference(str(path),digest),sources,False)
    args={key+'_document':docs[key]for key in ('presentation','supplement','diagnostics','chain')};args['references']={key:refs[key]for key in ('presentation','supplement','diagnostics','chain')}
    io.guard(sources,inventories,prepared['helper'])
    return io,refs,sources,inventories,prepared['helper'],args,observed


def run(*,execute=False):
    if execute is not True:raise ValueError('Explicit workbook export')
    if OUTPUT.exists():raise ValueError('Create-only workbook namespace')
    io,refs,sources,inventories,helper,args,observed=prepare();io.safe(OUTPUT)
    pure=module(PURE,PURE_SHA);display_checker=module(DISPLAY_CHECKER,DISPLAY_CHECKER_SHA);cell_checker=module(CELL_CHECKER,CELL_CHECKER_SHA);chart_checker=module(CHART_CHECKER,CHART_CHECKER_SHA)
    guard=lambda:io.guard(sources,inventories,helper)
    guard();OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        started=io.save(OUTPUT/'started.json',dict(schema='MULTIDECISION_H_WORKBOOK_STARTED_V2',input_references=refs,source_hashes=sources,source_inventories=inventories,observed_original_audit_starts=observed,original_audit_starts_externally_anchored=False,**FLAGS))
        display=pure.build_display(**args);projection_check=display_checker.inspect_display(display=display,**args)
        inputref=io.save(OUTPUT/'display.json',display);guard()
        subprocess.run([str(NODE),'--max-old-space-size=16384',str(BUILDER),str(OUTPUT/'display.json'),str(OUTPUT),str(MODULES)],check=True)
        cells=cell_checker.inspect_workbook(OUTPUT/'workbook.xlsx',display)
        charts=chart_checker.inspect_chart_parts(OUTPUT/'workbook.xlsx',display_checker.chart_expectations(display))
        guard();readback=io.save(OUTPUT/'independent_readback.json',dict(schema='MULTIDECISION_H_WORKBOOK_READBACK_V2',status='PASS_MAPPING_ALL_CELLS_AND_CHARTS',source_projection=projection_check,cell_inspection=cells,chart_inspection=charts,**FLAGS))
        files={p.name:io.sha(p.read_bytes())for p in OUTPUT.iterdir()if p.is_file()}
        expected={'started.json','display.json','workbook.xlsx','workbook.xlsx.inspect.ndjson','independent_readback.json'}|{f'preview-{i:02d}.png'for i in range(43)}
        io.require(set(files)==expected,'Exact workbook file inventory')
        publication=io.save(OUTPUT/'publication.json',dict(schema='MULTIDECISION_H_WORKBOOK_PUBLICATION_V2',status='ALL_CELL_AND_CHART_READBACK_PASS_VISUAL_REVIEW_PENDING',started_reference=started,display_reference=inputref,readback_reference=readback,input_references=refs,source_hashes=sources,source_inventories=inventories,files=files,**FLAGS))
        guard();io.require({p.name for p in OUTPUT.iterdir()}==expected|{'publication.json'},'Final workbook inventory')
        for name,digest in files.items():io.require(io.sha((OUTPUT/name).read_bytes())==digest,'Final output bytes')
        io.require(io.sha(Path(publication['path']).read_bytes())==publication['sha256'],'Final publication bytes')
        return publication
    except BaseException as error:
        io.save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(error).__name__,error=str(error),**FLAGS));raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');print(json.dumps(run(execute=parser.parse_args().execute)))
