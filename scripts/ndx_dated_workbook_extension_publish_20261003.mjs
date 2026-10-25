/** Source-bound, create-only H export. No economic computation or final acceptance. */
import fs from 'node:fs/promises';
import {createReadStream, constants} from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {spawn} from 'node:child_process';

const STORAGE=path.resolve('D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714');
const SOURCE=fileURLToPath(import.meta.url),ROOT=path.dirname(path.dirname(SOURCE));
const DATA=path.join(STORAGE,'dated_workbook_extension_data_20261003_v1');
export const OUTPUT=path.join(STORAGE,'dated_workbook_extension_20261003_v1');
export const BOUND=Object.freeze({
 index:{path:path.join(DATA,'index.json'),sha256:'879402d5041928e36096ed24d09404bd9a4fecbdc76428225beaa01529117603'},publication:{path:path.join(DATA,'publication.json'),sha256:'5ec8da155e9bb40f44aa3a50cf3305a72fb7f6b670660b91f4f72b86e8c96521'},
 audit:{path:path.join(STORAGE,'dated_workbook_extension_data_independent_readback_20261003_v1/independent_readback.json'),sha256:'ef6adcb90ed6650d54d54965ff2540dfb392a34bc5c4f9982752bd88e602c1ce'},
 tasks:{path:path.join(DATA,'tasks.jsonl'),sha256:'6ce82b33ba276ee52e5526503d2faed1f1637ab3d91bce10afd4400df7e8f72a'},shared:{path:path.join(DATA,'shared_display.json'),sha256:'77396263d69c988d73269adc18d5dca226385b5997735879e42518a1e73bb536'},classification:{path:path.join(DATA,'classification.json'),sha256:'976b46dab1fb2f44305156562454876cb1fab1001b6f3ab29361b719cb8e99b5'},
 data_producer:{path:path.join(ROOT,'scripts/ndx_dated_workbook_extension_data_20261003.py'),sha256:'c07e34d389b8d4990df31db8e70a9a70c87e2856d9abf2b5a017f64b777c8577'},
 data_reader:{path:path.join(ROOT,'scripts/ndx_dated_workbook_extension_data_independent_readback_20261003.py'),sha256:'53357679a47679a98012cf06a58823594a9826c04f9e4ce7cf80ed1aa6d630c6'},
 core:{path:path.join(ROOT,'scripts/ndx_dated_workbook_extension_20261003.mjs'),sha256:'b2770383e837c136755bad29caaea8cc5b817f5b4678617a5a2ceb23d513263a'},
 path_component:{path:path.join(ROOT,'scripts/ndx_dated_path_chart_component_20261003.mjs'),sha256:'39fcd13d7588b4c1527bcd4dbf79bf5ec626da157d337f77323910231dc8023a'},
 risk_component:{path:path.join(ROOT,'scripts/ndx_dated_risk_chart_component_20261003.mjs'),sha256:'9a4112a2abaaaee7c5bb4bd6c0c632519f06cbe92a1c0314135d1efa194179d5'},
 navigation_component:{path:path.join(ROOT,'scripts/ndx_dated_extension_navigation_component_20261003.mjs'),sha256:'65e0f0760d0730b65e177e8e884eeb82c21f1ebe3747a364879cc868cdbe75b6'},
 native_helper:{path:path.join(ROOT,'scripts/ndx_workbook_native_hyperlinks_20261003.py'),sha256:'267333bd62a3399c6ab3c97104bf884a737e116a51e8c62243aa3e0fcd6a475d'},
});
const DEP='C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const PYTHON=path.join(DEP,'python/python.exe');
export const FLAGS=Object.freeze({formal_comparison_passed:false,point_in_time_verified:false,promotion_allowed:false,future_independent_oos:false,economics_recomputed:false,risk_recomputed:false,fit_performed:false,account_executed:false,independent_export_readback_passed:false,visual_acceptance_passed:false,workbook_delivered:false});
const DATA_FALSE=['source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','account_executed','fit_performed','economic_metrics_recomputed','risk_reaggregated','workbook_delivered','charts_rendered','visual_acceptance_passed','xlsx_actual_size_limit_verified','full_transitive_source_closure_reverified'];
export const digest=bytes=>createHash('sha256').update(bytes).digest('hex');
const loaded=digest(await fs.readFile(SOURCE));
const reference=(file,sha256)=>({path:file,sha256});
const refCheck=r=>{assert(r&&typeof r.path==='string'&&r.path.trim()===r.path&&r.path.length);assert.match(r.sha256??'',/^[a-f0-9]{64}$/,'Pending immutable anchor');};
function merge(s,r){refCheck(r);assert(s[r.path]===undefined||s[r.path]===r.sha256,'Source conflict');s[r.path]=r.sha256;}
function integer(x){assert(Number.isSafeInteger(x)&&x>=0,'Exact safe integer');return x;}
// JSON.rawJSON preserves BigInt integer lexemes, never Number rounding or ambiguous tags.
export const bytesJson=v=>Buffer.from(JSON.stringify(v,(_k,x)=>typeof x==='bigint'?JSON.rawJSON(x.toString()):x,2));
export async function resourceGate(directory,reserve=0){
 integer(reserve);let existing=path.resolve(directory),st;
 while(true){try{st=await fs.statfs(existing,{bigint:true});break;}catch(error){if(error.code!=='ENOENT')throw error;const parent=path.dirname(existing);assert.notEqual(parent,existing,'Output volume unavailable');existing=parent;}}
 assert(st.bavail*st.bsize>=5n*1024n**3n+BigInt(reserve),'RESOURCE_STOP_BEFORE_DISPATCH: reserve five GiB');
}
async function outputInventory(directory,expected={}){const rows=[];const seen=new Set();async function walk(d){for(const e of await fs.readdir(d,{withFileTypes:true})){const f=path.join(d,e.name);assert(!e.isSymbolicLink(),'Output symlink rejected');if(e.isDirectory())await walk(f);else{assert(e.isFile());const hash=await hashFile(f);if(expected[f]!==undefined){assert.equal(hash,expected[f],'Output drift');seen.add(f);}rows.push({path:path.relative(directory,f).replaceAll('\\','/'),byte_count:(await fs.stat(f)).size,sha256:hash});}}}await walk(directory);assert.equal(seen.size,Object.keys(expected).length,'Missing output evidence');return rows.sort((a,b)=>a.path.localeCompare(b.path));}

async function hashFile(file){const h=createHash('sha256');for await(const b of createReadStream(file))h.update(b);return h.digest('hex');}
async function guard(s){for(const [p,h] of Object.entries(s))assert.equal(await hashFile(p),h,`Source drift: ${p}`);}
async function exactDir(dir,names){assert.deepEqual((await fs.readdir(dir)).sort(),[...names].sort(),'Exact namespace');}
export async function saveBytes(file,bytes){const h=await fs.open(file,'wx');try{await h.writeFile(bytes);await h.sync();}finally{await h.close();}assert.equal(await hashFile(file),digest(bytes));return reference(file,digest(bytes));}
async function saveJson(file,value){return saveBytes(file,bytesJson(value));}
async function syncExisting(file){const h=await fs.open(file,'r+');try{await h.sync();}finally{await h.close();}}

/** Metadata only: retain original unsafe integer lexemes as text; raw files copied unchanged. */
export function parseMetadata(bytes){
 const conversions=[];
 const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes),(key,v,context)=>{
  if(typeof v==='number'){
   assert(Number.isFinite(v),'Nonfinite JSON');
   if(Number.isInteger(v)&&!Number.isSafeInteger(v)){
    assert(context&&/^-?\d+$/.test(context.source),'Lossless integer lexeme required');conversions.push({key,original_decimal:context.source});return context.source;
   }
  }return v;
 });return {value,unsafe_integer_metadata_conversions:conversions};
}

export function validateInputs(d,r){
 const {index,publication:p,audit:a}=d;
 assert.equal(index.schema,'SOURCE_BOUND_DATED_WORKBOOK_EXTENSION_DATA_V1');assert.equal(p.schema,'DATED_WORKBOOK_EXTENSION_DATA_PUBLICATION_V1');assert.equal(p.status,'PUBLISHED_DISPLAY_DATA_NOT_WORKBOOK_DELIVERY');
 assert.equal(a.schema,'DATED_WORKBOOK_EXTENSION_DATA_INDEPENDENT_READBACK_V1');assert.equal(a.status,'PASS');assert.deepEqual(p.index_reference,r.index);assert.deepEqual(a.index_reference,r.index);assert.deepEqual(a.publication_reference,r.publication);
 assert.equal(a.reader_sha256,r.data_reader.sha256);assert.equal(a.source_hashes[r.data_reader.path],r.data_reader.sha256);assert.equal(a.producer_called,false);assert.equal(a.pure_projection_called,false);
 assert.deepEqual(p.source_hashes,index.source_hashes);
 for(const v of [index,p,a])for(const f of DATA_FALSE)assert.equal(v[f],false,f);
 assert.equal(integer(index.planned_task_count),1632);assert.equal(integer(index.projected_task_count)+integer(index.not_supplied_task_count),1632);
 assert.equal(integer(a.detail.planned_tasks),1632);assert.equal(a.detail.projected_tasks,index.projected_task_count);assert.equal(a.detail.missing_tasks,index.not_supplied_task_count);assert.equal(a.classification_rows_verified,101);
 assert.equal(index.full_new_cutoff_task_denominator,'6222659648236112670','Original bigint metadata preserved as text');
 assert.equal(index.delivery_status,'DISPLAY_DATA_ONLY_NOT_H_WORKBOOK_DELIVERY');
 for(const [k,role] of [['task_jsonl_reference','tasks'],['shared_display_reference','shared'],['classification_reference','classification']]){assert.deepEqual(p[k],index[k]);assert.equal(index[k].path,r[role].path);assert.equal(index[k].sha256,r[role].sha256);assert.equal(a.source_hashes[r[role].path],r[role].sha256);}
 assert.equal(a.verified_jsonl_sha256,r.tasks.sha256);assert.equal(a.verified_jsonl_bytes,index.task_jsonl_reference.byte_count);assert.equal(index.task_jsonl_reference.record_count,1632);
 assert.equal(index.source_hashes[r.data_producer.path],r.data_producer.sha256);
 for(const role of ['index','publication','data_producer'])assert.equal(a.source_hashes[r[role].path],r[role].sha256);
 const ids=index.task_index.map((v,i)=>{assert.equal(integer(v.task_ordinal),i);assert.match(v.numerical_task_id,/^[a-f0-9]{64}$/);return v.numerical_task_id;});assert.equal(ids.length,1632);assert.equal(new Set(ids).size,1632);
 assert.equal(d.shared.schema,'DATED_WORKBOOK_EXTENSION_SHARED_DATA_V1');assert.equal(d.classification.schema,'DATED_WORKBOOK_CLASSIFICATION_TABLE_V1');assert.equal(d.classification.rows.length,101);
 return ids;
}

async function load(){
 for(const r of Object.values(BOUND))refCheck(r); // Before runtime, directory creation, or source reads.
 const sources={[SOURCE]:loaded},bytes={},d={},lossless={};
 for(const [role,r] of Object.entries(BOUND)){merge(sources,r);if(role==='tasks')continue;const b=await fs.readFile(r.path);assert.equal(digest(b),r.sha256);bytes[role]=b;if(['index','publication','audit','shared','classification'].includes(role)){const parsed=parseMetadata(b);d[role]=parsed.value;lossless[role]=parsed.unsafe_integer_metadata_conversions;}}
 const ids=validateInputs(d,BOUND);
 for(const claims of [d.index.source_hashes,d.audit.source_hashes])for(const [p,h] of Object.entries(claims))merge(sources,reference(p,h));
 await exactDir(DATA,['started.json','tasks.jsonl','shared_display.json','classification.json','index.json','publication.json']);
 assert.equal(await fs.stat(path.dirname(BOUND.audit.path)).then(async dir=>(await fs.readdir(path.dirname(BOUND.audit.path))).includes('failure.json')),false,'Failed input audit');
 await guard(Object.fromEntries(Object.entries(sources).filter(([p])=>p!==BOUND.tasks.path)));
 return {sources,bytes,d,lossless,ids,references:structuredClone(BOUND)};
}

/** Only authenticated module bytes are evaluated; relative imports are a fixed allow-list. */
export async function loadCore(bytes){
 for(const role of ['core','path_component','risk_component','navigation_component'])assert.equal(digest(bytes[role]),BOUND[role].sha256);
 const modules={},urls={};
 for(const role of ['path_component','risk_component','navigation_component']){
  let text=bytes[role].toString('utf8');if(role==='risk_component'){const needle="'./ndx_dated_path_chart_component_20261003.mjs'";assert.equal(text.split(needle).length,2);text=text.replace(needle,JSON.stringify(urls.path_component));}assert(!/from\s+['"]\./.test(text),'Unexpected component dependency');urls[role]=`data:text/javascript;base64,${Buffer.from(text).toString('base64')}`;modules[role]=await import(urls[role]);
 }
 let text=bytes.core.toString('utf8');
 for(const role of Object.keys(urls)){const filename=path.basename(BOUND[role].path),needle=`'./${filename}'`;assert.equal(text.split(needle).length,2,'Exact code dependency');text=text.replace(needle,JSON.stringify(urls[role]));}
 assert(!/from\s+['"]\./.test(text),'No unresolved code dependency');modules.core=await import(`data:text/javascript;base64,${Buffer.from(text).toString('base64')}`);
 return modules;
}

async function nativeLinks(helper,workbookBytes,links){
 assert.equal(digest(helper),BOUND.native_helper.sha256);
 const script="import sys,json,base64,hashlib\np=json.load(sys.stdin);s=base64.b64decode(p['source']);assert hashlib.sha256(s).hexdigest()==p['sha'];m={'__name__':'_verified_native_links'};exec(compile(s,'verified_native_links.py','exec'),m);out=m['add_native_navigation_links'](base64.b64decode(p['xlsx']),p['links']);sys.stdout.buffer.write(out)";
 return new Promise((resolve,reject)=>{
  const child=spawn(PYTHON,['-S','-B','-c',script],{windowsHide:true,stdio:['pipe','pipe','pipe']}),chunks=[],errors=[];let size=0;
  child.stdout.on('data',b=>{size+=b.length;if(size>100*1024*1024){child.kill();reject(new Error('Navigation output exceeds bounded transport'));}else chunks.push(b);});child.stderr.on('data',b=>errors.push(b));child.on('error',reject);child.on('close',code=>code===0?resolve(Buffer.concat(chunks)):reject(new Error(`Native helper exit ${code}: ${Buffer.concat(errors).toString('utf8')}`)));
  child.stdin.on('error',reject);child.stdin.end(bytesJson({source:helper.toString('base64'),sha:BOUND.native_helper.sha256,xlsx:workbookBytes.toString('base64'),links}));
 });
}

function rangesForPackage(tasks,riskModule){
 if(tasks[0].schema==='DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1')return [{worksheet:'任务索引',rows:tasks.length+1,columns:3},{worksheet:'缺失说明',rows:1,columns:1}];
 const r=riskModule.prepareRiskTables(tasks,tasks.map(t=>t.numerical_task_id));
 const chartHeight=Math.max(22,r.maxGroups*2),helperStart=8+6*(chartHeight+8)+10;
 return [{worksheet:'路径查看',rows:175,columns:7},{worksheet:'任务索引',rows:tasks.length+1,columns:6},{worksheet:'候选路径',rows:tasks.length*127+1,columns:7},{worksheet:'共享路径',rows:128,columns:9},
 ...r.pages.map((x,i)=>({worksheet:`风险明细${String(i+1).padStart(3,'0')}`,rows:x.length+1,columns:17})),...r.indexPages.map((x,i)=>({worksheet:`风险定位${String(i+1).padStart(3,'0')}`,rows:x.length+1,columns:38})),
 ...Array.from({length:Math.ceil(r.sourceIndex.length/r.maxRowsPerSheet)},(_,i)=>({worksheet:`风险来源${String(i+1).padStart(3,'0')}`,rows:Math.min(r.maxRowsPerSheet,r.sourceIndex.length-i*r.maxRowsPerSheet)+1,columns:6})),{worksheet:'风险查看',rows:helperStart+5*(r.maxGroups+3)+r.maxGroups,columns:14}];
}
const col=n=>{let s='';for(;n;n=Math.floor((n-1)/26))s=String.fromCharCode(65+(n-1)%26)+s;return s;};
async function snapshotCells(workbook,specs,file){
 const f=await fs.open(file,'wx'),h=createHash('sha256');let records=0,bytes=0;const ranges=[];
 try{for(const spec of specs){assert(integer(spec.rows)<=100001&&integer(spec.columns)<=16384,'Per-sheet row/column limit');const sheet=workbook.worksheets.getItem(spec.worksheet);ranges.push({...spec,range:`A1:${col(spec.columns)}${spec.rows}`});
  for(let start=0;start<spec.rows;start+=1000){const n=Math.min(1000,spec.rows-start),range=sheet.getRangeByIndexes(start,0,n,spec.columns);const b=Buffer.from(JSON.stringify({worksheet:spec.worksheet,start_row_zero_based:start,start_column_zero_based:0,row_count:n,column_count:spec.columns,values:range.values,formulas:range.formulas})+'\n');await f.writeFile(b);h.update(b);records++;bytes+=b.length;}}
 await f.sync();}finally{await f.close();}
 return {...reference(file,h.digest('hex')),byte_count:bytes,record_count:records,ranges,scope:'AUTHOR_SNAPSHOT_FOR_INDEPENDENT_CELL_AND_FORMULA_COMPARISON_NOT_INDEPENDENT_VERIFICATION'};
}

/** Stream copies and machine shards preserve each original JSONL line, not parsed reserialization. */
export async function* copyTaskLines(sourceFile,outputDir,state,{maxShardBytes=32*1024*1024,maxShardRows=100000,resourceCheck=resourceGate}={}){
 await fs.mkdir(path.join(outputDir,'machine'));const full=await fs.open(path.join(outputDir,'tasks.jsonl'),'wx'),whole=createHash('sha256');let shard=null,shash=null,sbytes=0,srows=0,sstart=0,total=0,offset=0,tail=Buffer.alloc(0);state.shards=[];state.task_locations=[];
 async function closeShard(){if(!shard)return;await shard.sync();await shard.close();state.shards.push({shard_index:state.shards.length,filename:`machine/tasks-${String(state.shards.length).padStart(5,'0')}.jsonl`,start_task_ordinal:sstart,stop_task_ordinal:total,record_count:srows,byte_count:sbytes,sha256:shash.digest('hex')});shard=null;}
 try{for await(const chunk of createReadStream(sourceFile)){
  tail=Buffer.concat([tail,chunk]);let end;
  while((end=tail.indexOf(10))>=0){const line=Buffer.from(tail.subarray(0,end+1));tail=tail.subarray(end+1);assert(line.length<=maxShardBytes,'Single machine record exceeds 32 MiB');
   if(shard&&(srows===maxShardRows||sbytes+line.length>maxShardBytes))await closeShard();
   if(!shard){sbytes=0;srows=0;sstart=total;shash=createHash('sha256');shard=await fs.open(path.join(outputDir,'machine',`tasks-${String(state.shards.length).padStart(5,'0')}.jsonl`),'wx');}
   await resourceCheck(outputDir,line.length*2);await full.writeFile(line);await shard.writeFile(line);whole.update(line);shash.update(line);state.task_locations.push({task_ordinal:total,shard_index:state.shards.length,byte_start:sbytes,byte_stop:sbytes+line.length,row_sha256:digest(line)});sbytes+=line.length;srows++;offset+=line.length;total++;yield line;
  }assert(tail.length<=maxShardBytes,'Bounded incomplete JSONL');
 }assert.equal(tail.length,0,'Partial terminal line');await closeShard();await full.sync();state.complete=true;state.byte_count=offset;state.record_count=total;state.sha256=whole.digest('hex');}
 finally{if(shard){await shard.sync();await shard.close();}await full.sync();await full.close();}
}

/** Internal I/O orchestration is exported solely for synthetic callback tests.
 * publish() supplies authenticated core, runtime, and immutable source state.
 */
export async function executeDelivery({state,output,core,riskModule,artifact,applyLinks,sourceGuard,resourceCheck=resourceGate}){
 await fs.mkdir(path.dirname(output),{recursive:true});await fs.mkdir(output);const pending={},machine={};let streamResult;
 try{
  await saveJson(path.join(output,'started.json'),{schema:'DATED_H_WORKBOOK_EXTENSION_STARTED_V1',input_references:state.references,source_hashes:state.sources,default_task_id:state.ids[0],...FLAGS});
  await fs.mkdir(path.join(output,'attempts'));await fs.mkdir(path.join(output,'sources'));
  for(const role of ['index','publication','audit','shared','classification']){await resourceCheck(output,state.bytes[role].length);await saveBytes(path.join(output,'sources',`${role}.json`),state.bytes[role]);}
  await resourceCheck(output,state.bytes.shared.length+state.bytes.classification.length);await saveBytes(path.join(output,'shared_display.json'),state.bytes.shared);await saveBytes(path.join(output,'classification.json'),state.bytes.classification);
  const coreResult=await core.streamDisplayPackages({lines:copyTaskLines(state.references.tasks.path,output,machine,{resourceCheck}),index:state.d.index,shared:state.d.shared,expectedTaskIds:state.ids,
   exportPackage:async(tasks,ids,draft)=>{
    await resourceCheck(output,200*1024*1024);await sourceGuard(false);const dir=path.join(output,'attempts',`attempt-${String(draft.attempt_index).padStart(5,'0')}`);await fs.mkdir(dir);
    await saveJson(path.join(dir,'started.json'),{...draft,status:'PENDING_EXPORT_ATTEMPT',...FLAGS});
    const built=core.buildDisplayPackage(artifact.Workbook,tasks,ids);assert.equal(built.costs.taskCount,ids.length);assert(built.costs.dataRows<=250000);
    const cells=await snapshotCells(built.workbook,rangesForPackage(tasks,riskModule),path.join(dir,'expected_cells.jsonl'));
    const chartIndex=await saveJson(path.join(dir,'chart_source_index.json'),{schema:'DATED_H_PACKAGE_CHART_SOURCE_INDEX_V1',...draft,charts:built.charts.map((c,i,all)=>{const worksheet=c.categoryRange?.split('!')[0]??null;return {...c,chart_ordinal:all.slice(0,i).filter(x=>(x.categoryRange?.split('!')[0]??null)===worksheet).length,worksheet};}),task_selector:built.taskSelector??null,date_selector:built.dateSelector??null,default_local_task:1,default_date_index:1,source_jsonl_records:tasks.map(t=>({numerical_task_id:t.numerical_task_id,task_ordinal:t.task_ordinal,source_record:state.d.index.task_index[t.task_ordinal].jsonl_record})),risk_source_index:built.riskSourceIndex??[],task_evidence:built.taskEvidence??[],engine_evidence:built.engineEvidence??[],...FLAGS});
    const previews=[];for(const [n,view] of (built.missingEvidence?[['任务索引','A1:C20']]:[['路径查看','A1:G46'],['风险查看','A1:N43']]).entries()){
     const image=await built.workbook.render({sheetName:view[0],range:view[1],format:'png',scale:1});previews.push({...await saveBytes(path.join(dir,`preview-${n}.png`),Buffer.from(await image.arrayBuffer())),worksheet:view[0],range:view[1]});
    }
    const file=path.join(dir,'artifact.xlsx');assert.equal(await fs.stat(file).then(()=>true,()=>false),false);const blob=await artifact.SpreadsheetFile.exportXlsx(built.workbook);await blob.save(file);await syncExisting(file);const bytes=await fs.readFile(file);
    pending[draft.attempt_index]={file,cells,chartIndex,previews,costs:built.costs};return {bytes,chartSources:built.charts};
   },preserveAttempt:async(e,bytes)=>{
    const p=pending[e.attempt_index];assert(p);assert.equal(await hashFile(p.file),e.sha256);assert.equal(bytes.length,e.bytes);const r=reference(p.file,e.sha256);await saveJson(path.join(path.dirname(p.file),'pending.json'),{schema:'DATED_H_EXPORT_ATTEMPT_V1',...e,reference:r,expected_cells_reference:p.cells,chart_source_index_reference:p.chartIndex,previews:p.previews,costs:p.costs,...FLAGS});return r;
   },onFailure:async detail=>{await saveJson(path.join(output,'stream_failure.json'),{...detail,...FLAGS});}});
  streamResult=coreResult;assert.equal(machine.complete,true);assert.equal(machine.record_count,1632);assert.equal(machine.sha256,state.references.tasks.sha256);assert.equal(coreResult.taskCount,1632);assert.equal(coreResult.unprocessedTaskCount,0);
  const packages=[];
  for(const p of coreResult.packages){const a=coreResult.attempts.find(x=>x.reference.path===p.attempt_reference.path);assert(a);const detail=pending[a.attempt_index];assert(p.byte_count<=50*1024*1024);const target=path.join(output,p.filename);await resourceCheck(output,p.byte_count);await fs.copyFile(p.attempt_reference.path,target,constants.COPYFILE_EXCL);await syncExisting(target);assert.equal(await hashFile(target),p.sha256);
   packages.push({...p,workbook_reference:reference(target,p.sha256),actual_data_rows:detail.costs.dataRows,expected_cells_reference:detail.cells,chart_source_index_reference:detail.chartIndex,previews:detail.previews});}
  assert.deepEqual(packages.flatMap(p=>p.tasks.map(t=>t.numerical_task_id)),state.ids);
  await resourceCheck(output,200*1024*1024);const nav=core.buildNavigation(artifact.Workbook,state.d.index,state.d.classification,packages,state.ids);assert.equal(nav.nativeHelperRequired,true);assert.equal(nav.nativeHyperlinks.length,1632);
  const navCells=await snapshotCells(nav.workbook,[{worksheet:'使用说明',rows:15,columns:8},{worksheet:'全部任务',rows:1633,columns:12},{worksheet:'分类覆盖',rows:102,columns:14},{worksheet:'数据来源',rows:3,columns:4}],path.join(output,'navigation_expected_cells.jsonl'));
  const rawNav=path.join(output,'attempts','navigation-artifact.xlsx');const navBlob=await artifact.SpreadsheetFile.exportXlsx(nav.workbook);await navBlob.save(rawNav);await syncExisting(rawNav);const native=await applyLinks(await fs.readFile(rawNav),nav.nativeHyperlinks);assert(native.length<=50*1024*1024,'Navigation exceeds50MiB');const navRef=await saveBytes(path.join(output,'路径与风险导航.xlsx'),native);
  const nativeIntents=await saveJson(path.join(output,'navigation_links.json'),{links:nav.nativeHyperlinks,helper_reference:state.references.native_helper});
  const previews=[];for(const [n,sheet] of ['使用说明','全部任务','分类覆盖'].entries()){const image=await nav.workbook.render({sheetName:sheet,range:sheet==='使用说明'?'A1:H15':'A1:N16',format:'png',scale:1});previews.push({...await saveBytes(path.join(output,`navigation-preview-${n}.png`),Buffer.from(await image.arrayBuffer())),worksheet:sheet});}
  const machineRef=await saveJson(path.join(output,'machine_index.json'),{schema:'DATED_H_MACHINE_DATA_INDEX_V1',full_tasks_reference:reference(path.join(output,'tasks.jsonl'),machine.sha256),record_count:machine.record_count,byte_count:machine.byte_count,shards:machine.shards,task_locations:machine.task_locations,shared_reference:reference(path.join(output,'shared_display.json'),state.references.shared.sha256),classification_reference:reference(path.join(output,'classification.json'),state.references.classification.sha256),...FLAGS});
  await sourceGuard(true);
  const expectedOutputs={};
  function collectRefs(v){if(!v||typeof v!=='object')return;if(typeof v.path==='string'&&path.isAbsolute(v.path)&&path.relative(output,v.path)!==''&&!path.isAbsolute(path.relative(output,v.path))&&path.relative(output,v.path)!=='..'&&!path.relative(output,v.path).startsWith('..'+path.sep)&&typeof v.sha256==='string'){assert(expectedOutputs[v.path]===undefined||expectedOutputs[v.path]===v.sha256);expectedOutputs[v.path]=v.sha256;}for(const x of Object.values(v))collectRefs(x);}
  collectRefs([packages,navRef,navCells,nativeIntents,previews,machineRef,...Object.values(pending).map(p=>[p.cells,p.chartIndex,p.previews])]);
  expectedOutputs[path.join(output,'tasks.jsonl')]=machine.sha256;
  for(const shard of machine.shards)expectedOutputs[path.join(output,shard.filename)]=shard.sha256;
  for(const role of ['index','publication','audit','shared','classification'])expectedOutputs[path.join(output,'sources',`${role}.json`)]=digest(state.bytes[role]);
  expectedOutputs[path.join(output,'shared_display.json')]=state.references.shared.sha256;expectedOutputs[path.join(output,'classification.json')]=state.references.classification.sha256;
  const output_inventory=await outputInventory(output,expectedOutputs);
  const manifest={schema:'DATED_H_WORKBOOK_EXTENSION_EXPORT_V1',status:'EXPORTED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',output_inventory,output_inventory_excludes:['export_manifest.json','publication.json'],supplementary_json_integer_encoding:'ORIGINAL_INTEGER_TOKEN_VIA_BIGINT_AND_JSON_RAWJSON',planned_task_count:1632,packaged_task_count:1632,unprocessed_task_count:0,default_task_id:state.ids[0],packages,attempts:coreResult.attempts,oversize_attempt_count:coreResult.preservedOversizeAttemptCount,navigation:{workbook_reference:navRef,expected_cells_reference:navCells,native_links_reference:nativeIntents,previews},machine_index_reference:machineRef,input_references:state.references,source_hashes:state.sources,metadata_integer_conversion_policy:'UNSAFE_INTEGER_METADATA_RETAINED_AS_DECIMAL_TEXT_RAW_SOURCE_BYTES_COPIED_EXACT',metadata_integer_conversions:state.lossless,actual_package_bytes_within_50_mib:true,source_eof_verified:true,original_order_preserved:true,classification_count:101,shared_series_count:4,shared_risk_track_count:2,rendered_previews_are_not_visual_acceptance:true,expected_cells_are_author_snapshots_not_independent_proof:true,...FLAGS};
  const mr=await saveJson(path.join(output,'export_manifest.json'),manifest);await sourceGuard(false);
  const pr=await saveJson(path.join(output,'publication.json'),{schema:'DATED_H_WORKBOOK_EXTENSION_PUBLICATION_V1',status:'PUBLISHED_EXPORT_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',manifest_reference:mr,source_hashes:state.sources,all_package_callbacks_were_pending_until_complete_eof:true,...FLAGS});
  await sourceGuard(false);const finalInventory=await outputInventory(output);assert.deepEqual(finalInventory.filter(x=>!['export_manifest.json','publication.json'].includes(x.path)),output_inventory,'Post-publication output drift or unexpected entry');assert.equal(await hashFile(mr.path),mr.sha256);assert.equal(await hashFile(pr.path),pr.sha256);return {...mr,publication_reference:pr};
 }catch(error){await saveJson(path.join(output,'failure.json'),{schema:'DATED_H_WORKBOOK_EXTENSION_FAILURE_V1',status:'FAILED_DO_NOT_CONSUME',error:String(error),stream_completed:!!streamResult,all_attempts_retained:true,retry_allowed:false,...FLAGS});throw error;}
}

export async function publish({execute=false}={}){
 assert.equal(execute,true,'Explicit publication required');const state=await load();await resourceGate(OUTPUT);await guard(Object.fromEntries(Object.entries(state.sources).filter(([p])=>p!==BOUND.tasks.path)));const modules=await loadCore(state.bytes);
 const require=createRequire(path.join(DEP,'node/package.json'));const artifact=await import(pathToFileURL(require.resolve('@oai/artifact-tool')).href);
 return executeDelivery({state,output:OUTPUT,core:modules.core,riskModule:modules.risk_component,artifact,applyLinks:(b,links)=>nativeLinks(state.bytes.native_helper,b,links),sourceGuard:final=>guard(final?state.sources:{[SOURCE]:loaded,...Object.fromEntries(Object.entries(state.references).filter(([k])=>!['tasks','index','publication','audit','shared','classification'].includes(k)).map(([,r])=>[r.path,r.sha256]))})});
}
if(process.argv[1]&&path.resolve(process.argv[1])===SOURCE)console.log(await publish({execute:process.argv.includes('--execute')}));
