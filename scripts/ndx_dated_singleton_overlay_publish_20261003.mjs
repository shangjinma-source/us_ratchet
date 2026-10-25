/** Create-only repair overlay. Future terminal parent pins deliberately reject IO. */
import fs from 'node:fs/promises';
import {createReadStream} from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';
const SOURCE=fileURLToPath(import.meta.url),ROOT=path.dirname(path.dirname(SOURCE));
const STORAGE='D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714';
const PARENT=path.join(STORAGE,'dated_workbook_extension_20261003_v1');
export const OUTPUT=path.join(STORAGE,'dated_singleton_repair_overlay_20261003_v1');
export const BOUND=Object.freeze({manifest:{path:path.join(PARENT,'export_manifest.json'),sha256:null},publication:{path:path.join(PARENT,'publication.json'),sha256:null},publisher:{path:path.join(ROOT,'scripts/ndx_dated_workbook_extension_publish_20261003.mjs'),sha256:'f3375accf43c4f765b83b6e708e3986262e5a249107724d115adfbbdf651a771'},plan:{path:path.join(ROOT,'scripts/ndx_dated_singleton_overlay_plan_20261003.mjs'),sha256:'ef7c9c8704fc211a7bbd0e0932d2de2451c275354f8f6f5e8dcb9dbfe028567d'},repair:{path:path.join(ROOT,'scripts/ndx_dated_singleton_path_label_repair_20261003.mjs'),sha256:'f5ef70fbc034a17a1254723b07b4cf21278d1ee11967a6a1c11489bb008fdc00'},links:{path:path.join(ROOT,'scripts/ndx_dated_overlay_native_links_20261003.py'),sha256:'7126d0ade019db5a8ab1540b94de64fd18f49413f3160729379aea672468af99'}});
const DEP='C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const FLAGS={source_bytes_authenticated:false,economics_recomputed:false,risk_recomputed:false,fit_performed:false,account_executed:false,point_in_time_verified:false,formal_comparison_passed:false,future_independent_oos:false,promotion_allowed:false,independent_export_readback_passed:false,visual_acceptance_passed:false,native_excel_open_verified:false,workbook_delivered:false};
const sha=b=>createHash('sha256').update(b).digest('hex');const LOADED=sha(await fs.readFile(SOURCE));
const json=v=>Buffer.from(JSON.stringify(v,(_k,x)=>typeof x==='bigint'?JSON.rawJSON(x.toString()):x,2));
const ref=(p,h)=>({path:p,sha256:h});
const valid=r=>{assert(r&&path.isAbsolute(r.path));assert.match(r.sha256,/^[a-f0-9]{64}$/);};
const inside=(p,root)=>{const r=path.relative(root,p);assert(r&&!path.isAbsolute(r)&&r!=='..'&&!r.startsWith('..'+path.sep));};
async function hashFile(p){const h=createHash('sha256');for await(const b of createReadStream(p))h.update(b);return h.digest('hex');}
async function absentFailure(p){assert.equal(await fs.stat(path.join(path.dirname(p),'failure.json')).then(()=>true,()=>false),false,'Failed parent');}
async function read(r,s){valid(r);assert(s[r.path]===undefined||s[r.path]===r.sha256);await absentFailure(r.path);const b=await fs.readFile(r.path);assert.equal(sha(b),r.sha256);s[r.path]=r.sha256;return b;}
async function guard(s){for(const [p,h] of Object.entries(s)){await absentFailure(p);assert.equal(await hashFile(p),h,'Immutable source drift');}}
async function space(p,n=0){let d=p;while(!(await fs.stat(d).then(()=>true,()=>false)))d=path.dirname(d);const q=await fs.statfs(d,{bigint:true});assert(q.bavail*q.bsize>=5n*1024n**3n+BigInt(n),'5GiB plus write budget');}
async function save(p,b){await space(path.dirname(p),b.length);const h=await fs.open(p,'wx');try{await h.writeFile(b);await h.sync();}finally{await h.close();}assert.equal(await hashFile(p),sha(b));return ref(p,sha(b));}
async function saveJson(p,v){return save(p,json(v));}
async function moduleFrom(b){return import('data:text/javascript;base64,'+b.toString('base64'));}
export async function loadInputs(){
 for(const r of Object.values(BOUND))valid(r); // all future anchors checked before source IO
 const sources={[SOURCE]:LOADED},bytes={};for(const [k,r] of Object.entries(BOUND))bytes[k]=await read(r,sources);
 let old=bytes.publisher.toString('utf8').replaceAll('import.meta.url',JSON.stringify(pathToFileURL(BOUND.publisher.path).href));const publisher=await moduleFrom(Buffer.from(old));
 const manifest=publisher.parseMetadata(bytes.manifest).value,publication=publisher.parseMetadata(bytes.publication).value,d={},sourceBytes={};
 for(const [role,r] of Object.entries(publisher.BOUND)){assert.deepEqual(manifest.input_references[role],r,'Frozen original data/code input');if(role==='tasks'){assert.equal(await hashFile(r.path),r.sha256);sources[r.path]=r.sha256;continue;}sourceBytes[role]=await read(r,sources);if(['index','publication','audit','shared','classification'].includes(role))d[role]=publisher.parseMetadata(sourceBytes[role]).value;}
 publisher.validateInputs(d,publisher.BOUND);
 const expected={[BOUND.publisher.path]:BOUND.publisher.sha256};for(const r of Object.values(publisher.BOUND))expected[r.path]=r.sha256;for(const claims of [d.index.source_hashes,d.audit.source_hashes])for(const [p,h] of Object.entries(claims)){assert(expected[p]===undefined||expected[p]===h);expected[p]=h;}assert.deepEqual(manifest.source_hashes,expected,'Exact frozen parent closure');
 for(const [p,h] of Object.entries(manifest.source_hashes)){assert(sources[p]===undefined||sources[p]===h);sources[p]=h;}
 const parentFiles={};for(const r of manifest.output_inventory){assert(!path.isAbsolute(r.path));const p=path.resolve(PARENT,r.path);inside(p,PARENT);assert(parentFiles[p]===undefined);assert.equal((await fs.stat(p)).size,r.byte_count);assert.equal(await hashFile(p),r.sha256);parentFiles[p]=r.sha256;}
 const planModule=await moduleFrom(bytes.plan),repair=await moduleFrom(bytes.repair);
 const plan=planModule.planSingletonOverlay({parentManifest:manifest,parentPublication:publication,parentReference:BOUND.manifest,parentPublicationReference:BOUND.publication,dataIndex:d.index,outputRoot:OUTPUT,repairReference:BOUND.repair});
 await guard(sources);return {sources,parentFiles,bytes,sourceBytes,publisher,planModule,repair,manifest,d,plan};
}
export function parseDisplayRow(bytes){return JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes),(_k,v,c)=>{if(typeof v==='number'){assert(Number.isFinite(v));if(Number.isInteger(v)&&!Number.isSafeInteger(v)){assert(/^-?(0|[1-9][0-9]*)$/.test(c?.source));return BigInt(c.source);}}return v;});}
async function inventory(root){const all=[];async function walk(d){for(const e of await fs.readdir(d,{withFileTypes:true})){assert(!e.isSymbolicLink());const p=path.join(d,e.name);if(e.isDirectory())await walk(p);else{assert(e.isFile());all.push({path:path.relative(root,p).replaceAll('\\','/'),byte_count:(await fs.stat(p)).size,sha256:await hashFile(p)});}}}await walk(root);return all.sort((a,b)=>a.path.localeCompare(b.path));}
async function parentGuard(c){await guard(c.sources);await guard(c.parentFiles);const expected=new Set([...Object.keys(c.parentFiles),BOUND.manifest.path,BOUND.publication.path].map(p=>path.resolve(p)));const actual=await inventory(PARENT);assert.deepEqual(actual.map(r=>path.resolve(PARENT,r.path)).sort(),[...expected].sort(),'Exact terminal parent namespace');}
async function cells(w,specs,file){const f=await fs.open(file,'wx'),h=createHash('sha256');let byte_count=0,record_count=0;try{for(const spec of specs){for(let start=0;start<spec.rows;start+=1000){const n=Math.min(1000,spec.rows-start),r=w.worksheets.getItem(spec.worksheet).getRangeByIndexes(start,0,n,spec.columns),b=Buffer.from(JSON.stringify({worksheet:spec.worksheet,start_row_zero_based:start,start_column_zero_based:0,row_count:n,column_count:spec.columns,values:r.values,formulas:r.formulas})+'\n');await space(path.dirname(file),b.length);await f.writeFile(b);h.update(b);byte_count+=b.length;record_count++;}}await f.sync();}finally{await f.close();}return {path:file,sha256:h.digest('hex'),byte_count,record_count,ranges:structuredClone(specs),scope:'AUTHOR_SNAPSHOT_FOR_INDEPENDENT_CELL_AND_FORMULA_COMPARISON_NOT_INDEPENDENT_VERIFICATION'};}
export function compareCellCaptures(oldRecords,newRecords,taskId){
 assert.match(taskId,/^[a-f0-9]{64}$/);assert(Array.isArray(oldRecords)&&Array.isArray(newRecords));assert.equal(oldRecords.length,newRecords.length);
 const selected=e=>`=IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=1),${e},NA()),NA())`;
 const previous=selected("INDEX('任务索引'!$B$2:$B$2,$B$4)"),replacement=selected("'任务索引'!$B$2");let changed=0,checked=0;
 for(let n=0;n<oldRecords.length;n++){
  const a=oldRecords[n],b=newRecords[n];assert.deepEqual(Object.keys(a).sort(),Object.keys(b).sort());
  for(const key of Object.keys(a))if(!['values','formulas'].includes(key))assert.deepEqual(a[key],b[key]);
  for(const key of ['start_row_zero_based','start_column_zero_based','row_count','column_count'])assert(Number.isSafeInteger(a[key])&&a[key]>=0);assert(a.row_count>0&&a.column_count>0);
  for(const key of ['values','formulas'])for(const r of [a,b]){assert.equal(r[key].length,a.row_count);assert(r[key].every(v=>Array.isArray(v)&&v.length===a.column_count));}
  for(let i=0;i<a.row_count;i++)for(let j=0;j<a.column_count;j++){
   const permitted=a.worksheet==='路径查看'&&a.start_row_zero_based+i===4&&a.start_column_zero_based+j===1;checked++;
   if(permitted){assert.equal(a.values[i][j],'#VALUE!');assert.equal(a.formulas[i][j],previous);assert.equal(b.values[i][j],'ID: '+taskId);assert.equal(b.formulas[i][j],replacement);changed++;}
   else{assert.deepEqual(a.values[i][j],b.values[i][j],'Unchanged source value');assert.deepEqual(a.formulas[i][j],b.formulas[i][j],'Unchanged source formula');}
  }
 }
 assert.equal(changed,1,'Exactly one registered label delta');return {schema:'DATED_H_SINGLETON_CELL_PRESERVATION_V1',checked_cells:checked,changed_cells:changed,allowed_cell:'路径查看!B5',only_registered_delta:true,source_bytes_authenticated:false,economic_values_recomputed:false};
}
async function captureRecords(r){const b=await read(r,{});assert.equal(b.at(-1),10);return b.toString('utf8').trimEnd().split('\n').map(x=>JSON.parse(x));}
async function relocate(source,workbook,links,c){const script="import sys,json,base64,hashlib\np=json.load(sys.stdin);s=base64.b64decode(p['source']);assert hashlib.sha256(s).hexdigest()==p['sha'];m={'__name__':'_overlay_links'};exec(compile(s,'overlay_links.py','exec'),m);sys.stdout.buffer.write(m['relocate_navigation'](base64.b64decode(p['workbook']),p['links'],p['parent'],p['output']))";
 return new Promise((resolve,reject)=>{const child=spawn(path.join(DEP,'python/python.exe'),['-S','-B','-c',script],{windowsHide:true,stdio:['pipe','pipe','pipe']}),out=[],errors=[];let count=0;child.stdout.on('data',b=>{count+=b.length;if(count>50*1024**2){child.kill();reject(Error('Oversize navigation'));}else out.push(b);});child.stderr.on('data',b=>errors.push(b));child.on('error',reject);child.on('close',code=>code===0?resolve(Buffer.concat(out)):reject(Error(Buffer.concat(errors).toString())));child.stdin.on('error',reject);child.stdin.end(json({source:source.toString('base64'),sha:BOUND.links.sha256,workbook:workbook.toString('base64'),links,parent:c.plan.parent_root,output:OUTPUT}));});}
export async function publish({execute=false}={}){
 assert.equal(execute,true);const c=await loadInputs();assert.equal(await fs.stat(OUTPUT).then(()=>true,()=>false),false,'Create only no retry');await space(OUTPUT,200*1024**2);await fs.mkdir(OUTPUT);const written=[];
 try{
  written.push(await saveJson(path.join(OUTPUT,'started.json'),{schema:'DATED_H_SINGLETON_OVERLAY_STARTED_V1',input_references:BOUND,source_hashes:c.sources,...FLAGS}));written.push(await saveJson(path.join(OUTPUT,'repair_plan.json'),c.plan));
  await parentGuard(c);const modules=await c.publisher.loadCore(c.sourceBytes),artifact=createRequire(path.join(DEP,'node/node_modules','x.cjs'))('@oai/artifact-tool'),replacements=[];
  const fh=await fs.open(c.publisher.BOUND.tasks.path,'r');
  try{for(const r of c.plan.replacements){await space(OUTPUT,200*1024**2);await guard(Object.fromEntries(Object.entries(c.sources).filter(([p])=>p.endsWith('.mjs')||p.endsWith('.py'))));const parent=c.plan.packages[r.package_index].parent_package,loc=r.source_records[0].jsonl_record;
    assert.equal(loc.record_index,parent.start_task_ordinal);const start=loc.byte_start,stop=loc.byte_stop;assert(Number.isSafeInteger(start)&&Number.isSafeInteger(stop)&&stop>start&&stop-start<=64*1024**2);const raw=Buffer.alloc(stop-start);assert.equal((await fh.read(raw,0,raw.length,start)).bytesRead,raw.length);assert.equal(sha(raw),loc.row_sha256);assert.equal(raw.at(-1),10);
    const compact=parseDisplayRow(raw);assert.equal(compact.numerical_task_id,r.task_id);assert.equal(compact.task_ordinal,parent.start_task_ordinal);const task=modules.core.restoreTaskDisplay(compact,c.d.shared),built=modules.core.buildDisplayPackage(artifact.Workbook,[task],[r.task_id]);assert.equal(built.costs.dataRows,parent.actual_data_rows);
    const repairEvidence=c.repair.repairSingletonPathLabel(built.workbook,[r.task_id]);const dir=path.join(OUTPUT,`repair-${String(r.package_index).padStart(4,'0')}`);await fs.mkdir(dir);
    const chartBytes=await read(parent.chart_source_index_reference,{}),chart=parseDisplayRow(chartBytes);assert.deepEqual(built.charts,chart.charts.map(({worksheet,chart_ordinal,...rest})=>rest));assert.deepEqual(built.riskSourceIndex,chart.risk_source_index);assert.deepEqual(built.taskEvidence,chart.task_evidence);assert.deepEqual(built.engineEvidence,chart.engine_evidence);
    const chartRef=await save(path.join(dir,'chart_source_index.json'),chartBytes),cellRef=await cells(built.workbook,parent.expected_cells_reference.ranges,path.join(dir,'expected_cells.jsonl')),previews=[];
    const preservation=compareCellCaptures(await captureRecords(parent.expected_cells_reference),await captureRecords(cellRef),r.task_id);
    for(const [i,v] of parent.previews.entries()){const image=await built.workbook.render({sheetName:v.worksheet,range:v.range,format:'png',scale:1});previews.push({...await save(path.join(dir,`preview-${i}.png`),Buffer.from(await image.arrayBuffer())),worksheet:v.worksheet,range:v.range});}
    const file=path.join(OUTPUT,parent.filename),blob=await artifact.SpreadsheetFile.exportXlsx(built.workbook);await blob.save(file);const f=await fs.open(file,'r+');try{await f.sync();}finally{await f.close();}const size=(await fs.stat(file)).size;assert(size<=50*1024**2,'Actual singleton export50MiB limit');const workbookRef=ref(file,await hashFile(file));
    const repairRef=await saveJson(path.join(dir,'repair_evidence.json'),{...repairEvidence,cell_preservation:preservation,parent_package_reference:{...BOUND.manifest,json_pointer:`/packages/${r.package_index}`},parent_attempt_reference_preserved:parent.attempt_reference,parent_attempt_is_not_new_export_evidence:true,source_jsonl_reference:c.publisher.BOUND.tasks,source_record:loc,shared_reference:c.publisher.BOUND.shared,new_workbook_reference:workbookRef,new_byte_count:size,...FLAGS});
    replacements.push({...structuredClone(parent),workbook_reference:workbookRef,sha256:workbookRef.sha256,byte_count:size,expected_cells_reference:cellRef,chart_source_index_reference:chartRef,previews,repair_evidence_reference:repairRef});written.push(workbookRef,cellRef,chartRef,repairRef,...previews);
  }}finally{await fh.close();}
  const packages=c.plan.packages.map(p=>replacements.find(r=>r.package_index===p.package_index)??p.parent_package);const links=c.plan.native_links.map(l=>({...l,expected_workbook_reference:packages[l.package_index].workbook_reference}));const oldNav=c.manifest.navigation;
  const navBytes=await read(oldNav.workbook_reference,{});const navRef=await save(path.join(OUTPUT,'路径与风险导航.xlsx'),await relocate(c.bytes.links,navBytes,links,c));const navCells=await save(path.join(OUTPUT,'navigation_expected_cells.jsonl'),await read(oldNav.expected_cells_reference,{}));const linkRef=await saveJson(path.join(OUTPUT,'navigation_links.json'),{schema:'DATED_H_OVERLAY_NATIVE_LINKS_V1',links,parent_navigation_reference:oldNav.workbook_reference,...FLAGS});const navPreviews=[];
  for(const [i,p] of oldNav.previews.entries())navPreviews.push({...p,...await save(path.join(OUTPUT,`navigation-preview-${i}.png`),await read(p,{})),copied_unchanged_display_only:true});
  const navigation={workbook_reference:navRef,expected_cells_reference:{...oldNav.expected_cells_reference,...navCells},native_links_reference:linkRef,previews:navPreviews,link_count:1632,only_native_relationship_targets_changed:true};written.push(navRef,navCells,linkRef,...navPreviews);
  await parentGuard(c);const manifest=c.planModule.composeSingletonOverlayManifest({plan:c.plan,replacementPackages:replacements,navigation,newSourceReferences:Object.values(BOUND)});manifest.source_hashes=c.sources;manifest.output_inventory=await inventory(OUTPUT);manifest.output_inventory_excludes=['export_manifest.json','publication.json'];const mr=await saveJson(path.join(OUTPUT,'export_manifest.json'),manifest);const pr=await saveJson(path.join(OUTPUT,'publication.json'),{schema:'DATED_H_SINGLETON_OVERLAY_PUBLICATION_V1',status:'PUBLISHED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',manifest_reference:mr,source_hashes:c.sources,...FLAGS});written.push(mr,pr);
  await parentGuard(c);for(const r of written)assert.equal(await hashFile(r.path),r.sha256);assert.deepEqual((await inventory(OUTPUT)).filter(x=>!manifest.output_inventory_excludes.includes(x.path)),manifest.output_inventory);return {...mr,publication_reference:pr};
 }catch(e){const b=json({schema:'DATED_H_SINGLETON_OVERLAY_FAILURE_V1',status:'FAILED_DO_NOT_RETRY',error:String(e),saved_references:written,...FLAGS});const f=await fs.open(path.join(OUTPUT,'failure.json'),'wx');try{await f.writeFile(b);await f.sync();}finally{await f.close();}throw e;}
}
if(process.argv[1]&&path.resolve(process.argv[1])===SOURCE)console.log(await publish({execute:process.argv.includes('--execute')}));
