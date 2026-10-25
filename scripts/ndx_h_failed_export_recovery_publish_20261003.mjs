/** New failed-parent recovery. No old-run restart and no economic computation. */
import fs from 'node:fs/promises';
import {createReadStream,constants} from 'node:fs';
import path from 'node:path';
import {fileURLToPath,pathToFileURL} from 'node:url';
import {createHash} from 'node:crypto';
import {createRequire} from 'node:module';
import {spawn} from 'node:child_process';
import assert from 'node:assert/strict';

const SOURCE=fileURLToPath(import.meta.url),ROOT=path.dirname(path.dirname(SOURCE));
const STORAGE='D:/CodexResearch/us_ratchet/01a0cc4a-c717-7813-843e-86aca0d15714';
export const OUTPUT=path.join(STORAGE,'dated_h_failed_export_recovery_20261003_v1');
export const SOURCE_PHASE=Object.freeze({path:path.join(ROOT,'scripts/ndx_h_failed_export_recovery_sources_20261003.py'),sha256:'96689f970ad1115047d1e0b6cde8e595c553e36dbd5a25de71b2508751057224'});
const DEP='C:/Users/Administrator/.cache/codex-runtimes/codex-primary-runtime/dependencies';
const FLAGS={source_bytes_authenticated:false,formal_comparison_passed:false,point_in_time_verified:false,promotion_allowed:false,future_independent_oos:false,economics_recomputed:false,risk_recomputed:false,fit_performed:false,account_executed:false,independent_export_readback_passed:false,visual_acceptance_passed:false,native_excel_open_verified:false,workbook_delivered:false};
const sha=b=>createHash('sha256').update(b).digest('hex');
const LOADED=sha(await fs.readFile(SOURCE));
const json=v=>Buffer.from(JSON.stringify(v,(_k,x)=>typeof x==='bigint'?JSON.rawJSON(x.toString()):x,2));
const ref=(p,h)=>({path:p,sha256:h});
const valid=r=>{assert(r&&path.isAbsolute(r.path));assert.match(r.sha256??'',/^[a-f0-9]{64}$/,'Pending immutable anchor');};
async function hashFile(p){const h=createHash('sha256');for await(const b of createReadStream(p))h.update(b);return h.digest('hex');}
async function read(r){valid(r);const b=await fs.readFile(r.path);assert.equal(sha(b),r.sha256);return b;}
async function moduleFrom(b,p){return import('data:text/javascript;base64,'+Buffer.from(b.toString('utf8').replaceAll('import.meta.url',JSON.stringify(pathToFileURL(p).href))).toString('base64'));}
async function space(p,n=0){while(!(await fs.stat(p).then(()=>true,()=>false)))p=path.dirname(p);const s=await fs.statfs(p,{bigint:true});assert(s.bavail*s.bsize>=5n*1024n**3n+BigInt(n),'Five GiB plus output reserve');}
async function save(p,b,{emergency=false}={}){if(!emergency)await space(path.dirname(p),b.length);const f=await fs.open(p,'wx');try{await f.writeFile(b);await f.sync();}finally{await f.close();}assert.equal(await hashFile(p),sha(b));return ref(p,sha(b));}
async function inventory(root){const out=[];async function walk(d){for(const e of await fs.readdir(d,{withFileTypes:true})){assert(!e.isSymbolicLink());const p=path.join(d,e.name);if(e.isDirectory())await walk(p);else{assert(e.isFile());out.push({path:path.relative(root,p).replaceAll('\\','/'),sha256:await hashFile(p),byte_count:(await fs.stat(p)).size});}}}await walk(root);return out.sort((a,b)=>a.path.localeCompare(b.path));}

/** Bytes-authenticated Python private namespace; explicit binary UTF-8 wire. */
async function python(source,sourceRef,operation,payload){
 assert.equal(sha(source),sourceRef.sha256);
 const boot="import sys,json,base64,hashlib\np=json.loads(sys.stdin.buffer.read().decode('utf-8'));s=base64.b64decode(p['source'],validate=True);assert hashlib.sha256(s).hexdigest()==p['sha'];m={'__name__':'_verified_recovery','__file__':p['file']};exec(compile(s,p['file'],'exec'),m);op=p['operation'];assert op in ('prepare','guard','native');out=m['load_sources']() if op=='prepare' else m['guard'](p['payload']) if op=='guard' else m['apply_navigation_request'](base64.b64decode(p['payload'],validate=True));sys.stdout.buffer.write(out if op=='native' else json.dumps(out,ensure_ascii=False,allow_nan=False).encode('utf-8'))";
 return new Promise((resolve,reject)=>{const c=spawn(path.join(DEP,'python/python.exe'),['-S','-B','-c',boot],{windowsHide:true,stdio:['pipe','pipe','pipe']}),out=[],err=[];let size=0;c.stdout.on('data',b=>{size+=b.length;if(size>128*1024**2){c.kill();reject(Error('Bounded source protocol'));}else out.push(b);});c.stderr.on('data',b=>err.push(b));c.on('error',reject);c.on('close',n=>n===0?resolve(Buffer.concat(out)):reject(Error(Buffer.concat(err).toString('utf8'))));c.stdin.on('error',reject);c.stdin.end(json({source:source.toString('base64'),sha:sourceRef.sha256,file:sourceRef.path,operation,payload}));});
}

async function capture(workbook,ranges,file){const f=await fs.open(file,'wx'),h=createHash('sha256');let byte_count=0,record_count=0;try{for(const spec of ranges)for(let start=0;start<spec.rows;start+=1000){const rows=Math.min(1000,spec.rows-start),r=workbook.worksheets.getItem(spec.worksheet).getRangeByIndexes(start,0,rows,spec.columns),b=Buffer.from(JSON.stringify({worksheet:spec.worksheet,start_row_zero_based:start,start_column_zero_based:0,row_count:rows,column_count:spec.columns,values:r.values,formulas:r.formulas})+'\n');await space(path.dirname(file),b.length);await f.writeFile(b);h.update(b);byte_count+=b.length;record_count++;}await f.sync();}finally{await f.close();}return {path:file,sha256:h.digest('hex'),byte_count,record_count,ranges:structuredClone(ranges)};}
async function records(r,parse){const b=await read(r);assert.equal(b.at(-1),10);return b.toString('utf8').trimEnd().split('\n').map(s=>parse(Buffer.from(s)));}

export async function publish({execute=false}={}){
 assert.equal(execute,true);valid(SOURCE_PHASE); // pending before file IO
 const own=await fs.readFile(SOURCE),phase=await read(SOURCE_PHASE);assert.equal(sha(own),LOADED,'Loaded recovery publisher changed');
 // Source preparation is read-only and does not invoke any SDK or producer.
 const contextBytes=await python(phase,SOURCE_PHASE,'prepare',null);
 const context=JSON.parse(contextBytes.toString('utf8'));const refs=context.input_references;
 const preserved=await moduleFrom(await read(refs.preservation),refs.preservation.path),parse=preserved.parseDisplayRow;
 const c=parse(contextBytes),old=await moduleFrom(await read(refs.publisher),refs.publisher.path);
 // Preserve the frozen builder's metadata conversion policy, independently of
 // lossless BigInt parsing for compact task rows and cell/source snapshots.
 const d=old.parseMetadata(json(Object.fromEntries(['index','publication','audit','shared','classification'].map(k=>[k,c.documents[k]])))).value;old.validateInputs(d,old.BOUND);
 for(const [k,r] of Object.entries(old.BOUND))assert.deepEqual(r,refs[k]);
 const moduleBytes={};for(const k of ['core','path_component','risk_component','navigation_component'])moduleBytes[k]=await read(refs[k]);
 const modules=await old.loadCore(moduleBytes),repair=await moduleFrom(await read(refs.repair),refs.repair.path);
 const artifact=createRequire(path.join(DEP,'node/package.json'))('@oai/artifact-tool');
 const sourceHashes={...c.source_hashes,[SOURCE]:sha(own),[SOURCE_PHASE.path]:SOURCE_PHASE.sha256};
 const codeGuard=async()=>{for(const [p,h] of Object.entries(sourceHashes))if(p.endsWith('.py')||p.endsWith('.mjs'))assert.equal(await hashFile(p),h);};
 const parentGuard=async()=>{await python(phase,SOURCE_PHASE,'guard',c);await codeGuard();};
 return executeRecovery({c,refs,d,modules,repair,preserved,parse,artifact,sourceHashes,codeGuard,parentGuard,
  applyNative:async packet=>python(await read(refs.wire),refs.wire,'native',packet.toString('base64')),output:OUTPUT});
}

/** Synthetic orchestration seam; publish supplies only authenticated fixed modules. */
export async function executeRecovery({c,refs,d,modules,repair,preserved,parse,artifact,sourceHashes,codeGuard,parentGuard,applyNative,output}){
 const root=path.dirname(refs.failure.path),byname=new Map(c.parent_inventory.map(r=>[r.path,r]));
 const parentRef=name=>{const r=byname.get(name);assert(r);return ref(path.join(root,name),r.sha256);};
 assert.equal(await fs.stat(output).then(()=>true,()=>false),false,'Exclusive new recovery/no retry');await space(output,200*1024**2);await fs.mkdir(output);const written=[];
 try{
  written.push(await save(path.join(output,'started.json'),json({schema:'DATED_H_FAILED_EXPORT_RECOVERY_STARTED_V1',input_references:refs,source_hashes:sourceHashes,parent_status:'FAILED_DO_NOT_CONSUME',...FLAGS})));
  const parentInventoryRef=await save(path.join(output,'parent_inventory.json'),json({parent_root:root,files:c.parent_inventory,parent_failure_reference:refs.failure,...FLAGS}));written.push(parentInventoryRef);
  const planRef=await save(path.join(output,'recovery_plan.json'),json(c.plan));written.push(planRef);const packages=[];
  const input=await fs.open(refs.tasks.path,'r');
  try{for(const plan of c.plan.packages){
   await codeGuard();await space(output,200*1024**2);const pending=c.attempts[plan.attempt_index].pending;
   const tasks=c.task_metadata.slice(plan.start_task_ordinal,plan.stop_task_ordinal).map((r,i)=>({...r,local_task_number:i+1,navigation_row:i+2}));
   let workbookRef,cells=pending.expected_cells_reference,chart=pending.chart_source_index_reference,previews=pending.previews,repairRef=null,byteCount=plan.byte_count;
   const file=path.join(output,plan.filename);
   if(plan.action==='COPY_ORIGINAL_BYTES_NO_SDK_EXPORT'){
    await fs.copyFile(plan.original_workbook_reference.path,file,constants.COPYFILE_EXCL);const handle=await fs.open(file,'r+');try{await handle.sync();}finally{await handle.close();}assert.equal(await hashFile(file),plan.original_workbook_reference.sha256);workbookRef=ref(file,plan.original_workbook_reference.sha256);
   }else{
    const ordinal=plan.start_task_ordinal,loc=d.index.task_index[ordinal].jsonl_record;assert.equal(loc.record_index,ordinal);assert(loc.byte_stop-loc.byte_start<=32*1024**2);
    const raw=Buffer.alloc(loc.byte_stop-loc.byte_start);assert.equal((await input.read(raw,0,raw.length,loc.byte_start)).bytesRead,raw.length);assert.equal(sha(raw),loc.row_sha256);assert.equal(raw.at(-1),10);
    const compact=parse(raw);assert.equal(compact.task_ordinal,ordinal);assert.equal(compact.numerical_task_id,plan.task_ids[0]);const task=modules.core.restoreTaskDisplay(compact,d.shared),built=modules.core.buildDisplayPackage(artifact.Workbook,[task],plan.task_ids);assert.deepEqual(built.costs,pending.costs);
    const delta=repair.repairSingletonPathLabel(built.workbook,plan.task_ids),oldChartBytes=await read(chart),oldChart=parse(oldChartBytes);
    assert.deepEqual(built.charts,oldChart.charts.map(({worksheet,chart_ordinal,...r})=>r));assert.deepEqual(built.riskSourceIndex,oldChart.risk_source_index);assert.deepEqual(built.taskEvidence,oldChart.task_evidence);assert.deepEqual(built.engineEvidence,oldChart.engine_evidence);
    const dir=path.join(output,`repair-${String(plan.package_index).padStart(4,'0')}`);await fs.mkdir(dir);
    cells=await capture(built.workbook,pending.expected_cells_reference.ranges,path.join(dir,'expected_cells.jsonl'));
    const preservation=preserved.compareCellCaptures(await records(pending.expected_cells_reference,parse),await records(cells,parse),plan.task_ids[0]);
    chart=await save(path.join(dir,'chart_source_index.json'),oldChartBytes);previews=[];
    for(const [i,v] of pending.previews.entries()){const image=await built.workbook.render({sheetName:v.worksheet,range:v.range,format:'png',scale:1});previews.push({...await save(path.join(dir,`preview-${i}.png`),Buffer.from(await image.arrayBuffer())),worksheet:v.worksheet,range:v.range});}
    const blob=await artifact.SpreadsheetFile.exportXlsx(built.workbook);await blob.save(file);const handle=await fs.open(file,'r+');try{await handle.sync();}finally{await handle.close();}byteCount=(await fs.stat(file)).size;assert(byteCount<=50*1024**2);workbookRef=ref(file,await hashFile(file));
    repairRef=await save(path.join(dir,'repair_evidence.json'),json({schema:'DATED_H_FAILED_PARENT_SINGLETON_REPAIR_V1',original_pending_reference:plan.pending_reference,original_workbook_reference:plan.original_workbook_reference,new_workbook_reference:workbookRef,new_byte_count:byteCount,source_record:loc,repair:delta,cell_preservation:preservation,original_attempt_is_not_new_export:true,...FLAGS}));written.push(cells,chart,repairRef,...previews);
   }
   written.push(workbookRef);packages.push({...plan,tasks,workbook_reference:workbookRef,byte_count:byteCount,sha256:workbookRef.sha256,actual_data_rows:pending.costs.dataRows,expected_cells_reference:cells,chart_source_index_reference:chart,previews,repair_evidence_reference:repairRef});
  }}finally{await input.close();}
  const ids=d.index.task_index.map(r=>r.numerical_task_id),nav=modules.core.buildNavigation(artifact.Workbook,d.index,d.classification,packages,ids);assert.deepEqual(nav.nativeHyperlinks,c.plan.navigation_links);
  const navRanges=[{worksheet:'使用说明',rows:15,columns:8},{worksheet:'全部任务',rows:1633,columns:12},{worksheet:'分类覆盖',rows:102,columns:14},{worksheet:'数据来源',rows:3,columns:4}];
  const navCells=await capture(nav.workbook,navRanges,path.join(output,'navigation_expected_cells.jsonl'));assert.deepEqual(await records(navCells,parse),await records(parentRef('navigation_expected_cells.jsonl'),parse),'Original navigation values/formulas unchanged');
  const packet=json({source:(await read(refs.native_helper)).toString('base64'),sha:refs.native_helper.sha256,xlsx:(await read(parentRef('attempts/navigation-artifact.xlsx'))).toString('base64'),links:c.plan.navigation_links});
  const native=await applyNative(packet);assert(native.length<=50*1024**2);
  const navRef=await save(path.join(output,'路径与风险导航.xlsx'),native),linksRef=await save(path.join(output,'navigation_links.json'),json({schema:'DATED_H_RECOVERED_NATIVE_LINKS_V1',links:c.plan.navigation_links,helper_reference:refs.native_helper,utf8_transport_reference:refs.wire,...FLAGS})),navPreviews=[];
  for(const [i,sheet] of ['使用说明','全部任务','分类覆盖'].entries()){const image=await nav.workbook.render({sheetName:sheet,range:sheet==='使用说明'?'A1:H15':'A1:N16',format:'png',scale:1});navPreviews.push({...await save(path.join(output,`navigation-preview-${i}.png`),Buffer.from(await image.arrayBuffer())),worksheet:sheet});}
  written.push(navCells,navRef,linksRef,...navPreviews);
  const machineRef=await save(path.join(output,'machine_index.json'),json({...c.machine,schema:'DATED_H_RECOVERED_MACHINE_DATA_INDEX_V1',full_tasks_reference:parentRef('tasks.jsonl'),shared_reference:parentRef('shared_display.json'),classification_reference:parentRef('classification.json'),shards:c.machine.shards.map(s=>({...s,reference:parentRef(s.filename)})),original_bytes_not_reencoded:true,...FLAGS}));written.push(machineRef);
  await parentGuard();const outputInventory=await inventory(output);
  const manifest={schema:'DATED_H_FAILED_EXPORT_RECOVERY_V1',status:'RECOVERED_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',parent_status:'FAILED_DO_NOT_CONSUME',old_publication_existed:false,recovery_is_new_attempt:true,parent_failure_reference:refs.failure,parent_started_reference:refs.started,parent_inventory_reference:parentInventoryRef,recovery_plan_reference:planRef,input_references:refs,source_hashes:sourceHashes,planned_task_count:1632,packaged_task_count:1632,unprocessed_task_count:0,packages,machine_index_reference:machineRef,navigation:{workbook_reference:navRef,expected_cells_reference:navCells,native_links_reference:linksRef,previews:navPreviews,link_count:1632},output_inventory:outputInventory,output_inventory_excludes:['export_manifest.json','publication.json'],...FLAGS};
  const mr=await save(path.join(output,'export_manifest.json'),json(manifest)),pr=await save(path.join(output,'publication.json'),json({schema:'DATED_H_FAILED_EXPORT_RECOVERY_PUBLICATION_V1',status:'PUBLISHED_RECOVERY_PENDING_INDEPENDENT_READBACK_AND_VISUAL_ACCEPTANCE',manifest_reference:mr,source_hashes:sourceHashes,...FLAGS}));written.push(mr,pr);
  await parentGuard();for(const r of written)assert.equal(await hashFile(r.path),r.sha256);assert.deepEqual((await inventory(output)).filter(r=>!manifest.output_inventory_excludes.includes(r.path)),outputInventory);return {...mr,publication_reference:pr};
 }catch(error){await save(path.join(output,'failure.json'),json({schema:'DATED_H_FAILED_EXPORT_RECOVERY_FAILURE_V1',status:'FAILED_NO_RETRY',error:String(error),saved_references:written,parent_failure_reference:refs.failure,...FLAGS}),{emergency:true});throw error;}
}
if(process.argv[1]&&path.resolve(process.argv[1])===SOURCE)console.log(await publish({execute:process.argv.includes('--execute')}));
