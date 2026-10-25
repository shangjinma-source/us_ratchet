import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
import {publish,SOURCE_PHASE,executeRecovery} from '../scripts/ndx_h_failed_export_recovery_publish_20261003.mjs';
import {compareCellCaptures} from '../scripts/ndx_dated_singleton_overlay_publish_20261003.mjs';

test('pending source phase refuses before IO and static binding is immutable',async()=>{
 assert(Object.isFrozen(SOURCE_PHASE));
 const url=new URL('../scripts/ndx_h_failed_export_recovery_publish_20261003.mjs',import.meta.url);
 const source=(await fs.readFile(url,'utf8')).replace(`sha256:'${SOURCE_PHASE.sha256}'`,'sha256:null').replaceAll('import.meta.url',JSON.stringify(url.href));
 const pending=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));assert.equal(pending.SOURCE_PHASE.sha256,null);
 const saved=fs.readFile;fs.readFile=async()=>{throw Error('unexpected IO');};
 try{await assert.rejects(pending.publish({execute:true}),/Pending immutable anchor/);}finally{fs.readFile=saved;}
});

test('no implicit publisher execution',async()=>{
 await assert.rejects(publish(),/false !== true/);
});

export async function fixture(root){
 const parent=path.join(root,'failed'),output=path.join(root,'new');await fs.mkdir(parent);const inv=[];
 const digest=b=>createHash('sha256').update(b).digest('hex');
 async function put(name,b){b=Buffer.isBuffer(b)?b:Buffer.from(typeof b==='string'?b:JSON.stringify(b));const p=path.join(parent,name);await fs.mkdir(path.dirname(p),{recursive:true});await fs.writeFile(p,b);const r={path:p,sha256:digest(b)};inv.push({path:name,sha256:r.sha256,byte_count:b.length});return r;}
 const workbook={worksheets:{getItem:()=>({getRangeByIndexes:(_s,_c,n,m)=>({values:Array.from({length:n},()=>Array(m).fill(null)),formulas:Array.from({length:n},()=>Array(m).fill(null))})})},render:async()=>({arrayBuffer:async()=>Buffer.from('synthetic png')})};
 const ranges=[['使用说明',15,8],['全部任务',1633,12],['分类覆盖',102,14],['数据来源',3,4]],records=[];
 for(const [worksheet,total,columns] of ranges)for(let start=0;start<total;start+=1000){const n=Math.min(1000,total-start),r=workbook.worksheets.getItem(worksheet).getRangeByIndexes(start,0,n,columns);records.push({worksheet,start_row_zero_based:start,start_column_zero_based:0,row_count:n,column_count:columns,...r});}
 await put('navigation_expected_cells.jsonl',records.map(r=>JSON.stringify(r)+'\n').join(''));await put('attempts/navigation-artifact.xlsx','synthetic saved navigation');
 const tasksRef=await put('tasks.jsonl','synthetic tasks');await put('shared_display.json','{}');await put('classification.json','{}');await put('machine/tasks-00000.jsonl','synthetic tasks');
 const failure=await put('failure.json','{}'),source=await put('native.py','synthetic source'),native=source;
 const artifactRef=await put('package-0001.xlsx','unchanged package'),pendingRef=await put('pending.json','{}'),cells=await put('cells.jsonl','{}\n'),chart=await put('chart.json','{}');
 const ids=Array.from({length:1632},(_,i)=>i.toString(16).padStart(64,'0'));
 const links=ids.map((_,i)=>({worksheet:'全部任务',cell:`H${i+2}`,target:'package-0001.xlsx',location:`'任务索引'!A${i+2}`}));
 const plan={package_index:0,filename:'package-0001.xlsx',start_task_ordinal:0,stop_task_ordinal:1632,task_ids:ids,attempt_index:0,original_workbook_reference:artifactRef,byte_count:Buffer.byteLength('unchanged package'),pending_reference:pendingRef,action:'COPY_ORIGINAL_BYTES_NO_SDK_EXPORT'};
 const c={source_hashes:{},parent_inventory:inv,plan:{packages:[plan],navigation_links:links},attempts:[{pending:{expected_cells_reference:cells,chart_source_index_reference:chart,previews:[],costs:{dataRows:1}}}],task_metadata:ids.map((id,i)=>({task_ordinal:i,numerical_task_id:id,comparison_status:'DISPLAY_PROJECTED',integer_status:'AVAILABLE',continuous_status:'AVAILABLE'})),machine:{schema:'DATED_H_SAVED_MACHINE_STREAM_INSPECTION_V1',record_count:1632,shards:[{filename:'machine/tasks-00000.jsonl'}],task_locations:[]}};
 return {c,refs:{failure,tasks:tasksRef,native_helper:native,wire:source},d:{index:{task_index:ids.map(numerical_task_id=>({numerical_task_id}))},classification:{},shared:{}},modules:{core:{buildNavigation:()=>({workbook,nativeHyperlinks:links})}},repair:{},preserved:{},parse:b=>JSON.parse(b.toString('utf8')),artifact:{},sourceHashes:{},codeGuard:async()=>{},parentGuard:async()=>{},applyNative:async packet=>{const p=JSON.parse(packet);assert.equal(p.links.length,1632);return Buffer.from('synthetic native result');},output};
}

test('physical synthetic copy lifecycle retains source and final machine schema',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'h-recovery-test-'));
 try{const args=await fixture(root),result=await executeRecovery(args),manifest=JSON.parse(await fs.readFile(result.path));
  assert.equal(manifest.schema,'DATED_H_FAILED_EXPORT_RECOVERY_V1');assert.equal(manifest.packaged_task_count,1632);
  assert.equal(manifest.packages[0].workbook_reference.sha256,args.c.plan.packages[0].original_workbook_reference.sha256);
  const machine=JSON.parse(await fs.readFile(manifest.machine_index_reference.path));assert.equal(machine.schema,'DATED_H_RECOVERED_MACHINE_DATA_INDEX_V1');
  assert.equal(manifest.navigation.link_count,1632);assert.equal(manifest.visual_acceptance_passed,false);
  await assert.rejects(executeRecovery(args),/Exclusive new recovery/);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('source guard failure retains copied package and explicit no retry failure',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'h-recovery-stop-'));
 try{const args=await fixture(root);args.parentGuard=async()=>{throw Error('physical source drift');};
  await assert.rejects(executeRecovery(args),/physical source drift/);
  const failure=JSON.parse(await fs.readFile(path.join(args.output,'failure.json')));assert.equal(failure.status,'FAILED_NO_RETRY');
  assert(failure.saved_references.some(r=>r.path.endsWith('package-0001.xlsx')));
  await assert.rejects(fs.stat(path.join(args.output,'export_manifest.json')),/ENOENT/);
  await assert.rejects(executeRecovery(args),/Exclusive new recovery/);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('singleton synthetic SDK branch uses real frozen all-cell preservation gate',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'h-recovery-singleton-'));
 try{const args=await fixture(root),parent=path.dirname(args.refs.failure.path),ids=args.c.plan.packages[0].task_ids,hash=b=>createHash('sha256').update(b).digest('hex');
  async function put(name,value){const b=Buffer.from(typeof value==='string'?value:JSON.stringify(value));const p=path.join(parent,name);await fs.writeFile(p,b);return {path:p,sha256:hash(b)};}
  const raw=Buffer.from(JSON.stringify({task_ordinal:0,numerical_task_id:ids[0]})+'\n');await fs.writeFile(args.refs.tasks.path,raw);args.refs.tasks.sha256=hash(raw);args.d.index.task_index[0].jsonl_record={record_index:0,byte_start:0,byte_stop:raw.length,row_sha256:hash(raw)};
  const original=args.c.plan.packages[0],other={...original,package_index:1,filename:'package-0002.xlsx',start_task_ordinal:1,task_ids:ids.slice(1),attempt_index:1};
  args.c.plan.packages=[{...original,stop_task_ordinal:1,task_ids:[ids[0]],action:'REBUILD_SINGLETON_WITH_REGISTERED_B5_ONLY_DELTA'},other];
  for(let i=1;i<args.c.plan.navigation_links.length;i++)Object.assign(args.c.plan.navigation_links[i],{target:'package-0002.xlsx',location:`'任务索引'!A${i+1}`});
  let repaired=false,exports=0;const selected=e=>`=IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=1),${e},NA()),NA())`;
  const wb={worksheets:{getItem:()=>({getRangeByIndexes:(_s,_c,n,m)=>{const values=Array.from({length:n},()=>Array(m).fill(null)),formulas=structuredClone(values);values[4][1]=repaired?'ID: '+ids[0]:'#VALUE!';formulas[4][1]=selected(repaired?"'任务索引'!$B$2":"INDEX('任务索引'!$B$2:$B$2,$B$4)");return {values,formulas};}})},render:async()=>({arrayBuffer:async()=>Buffer.from('new synthetic preview')})};
  const old=wb.worksheets.getItem().getRangeByIndexes(0,0,5,2),cells={...await put('single-cells.jsonl',JSON.stringify({worksheet:'路径查看',start_row_zero_based:0,start_column_zero_based:0,row_count:5,column_count:2,...old})+'\n'),ranges:[{worksheet:'路径查看',rows:5,columns:2}]};
  const chart=await put('single-chart.json',{charts:[],risk_source_index:[],task_evidence:[],engine_evidence:[]}),costs={missing:false,taskCount:1,taskIds:[ids[0]],dataRows:5};
  args.c.attempts=[{pending:{expected_cells_reference:cells,chart_source_index_reference:chart,previews:[],costs}},args.c.attempts[0]];
  args.modules.core.restoreTaskDisplay=t=>t;args.modules.core.buildDisplayPackage=()=>({workbook:wb,costs,charts:[],riskSourceIndex:[],taskEvidence:[],engineEvidence:[]});
  args.repair.repairSingletonPathLabel=()=>{repaired=true;return {allowed_cell:'路径查看!B5'};};args.preserved.compareCellCaptures=compareCellCaptures;
  args.artifact.SpreadsheetFile={exportXlsx:async()=>{exports++;return {save:async file=>fs.writeFile(file,'synthetic repaired xlsx')};}};
  const result=await executeRecovery(args),manifest=JSON.parse(await fs.readFile(result.path));assert.equal(exports,1);assert.equal(manifest.packages.length,2);
  const evidence=JSON.parse(await fs.readFile(manifest.packages[0].repair_evidence_reference.path));assert.equal(evidence.cell_preservation.changed_cells,1);assert.equal(evidence.cell_preservation.checked_cells,10);
  assert.equal(manifest.packages[1].workbook_reference.sha256,other.original_workbook_reference.sha256);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
