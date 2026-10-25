import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import * as publisher from '../scripts/ndx_dated_workbook_extension_publish_20261003.mjs';
const {digest,executeDelivery,copyTaskLines,validateInputs,BOUND}=publisher;
async function fixture(){
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'h-publisher-review-')),ids=Array.from({length:1632},(_,i)=>(i+1).toString(16).padStart(64,'0'));
 const raw=Buffer.from(ids.map(numerical_task_id=>JSON.stringify({numerical_task_id})+'\n').join('')),source=path.join(dir,'source.jsonl');await fs.writeFile(source,raw);
 const bytes=Object.fromEntries(['index','publication','audit','shared','classification'].map(k=>[k,Buffer.from('{}')]));
 const references={tasks:{path:source,sha256:digest(raw)},native_helper:{path:'helper',sha256:'a'.repeat(64)},shared:{path:'shared',sha256:digest(bytes.shared)},classification:{path:'classification',sha256:digest(bytes.classification)}};
 const state={ids,bytes,references,sources:{},lossless:[],d:{index:{task_index:ids.map(()=>({jsonl_record:{}}))},shared:{},classification:{}}};
 const wb={worksheets:{getItem:()=>({getRangeByIndexes:(_a,_b,r,c)=>({values:Array.from({length:r},()=>Array(c).fill(null)),formulas:Array.from({length:r},()=>Array(c).fill(null))})})},render:async()=>({arrayBuffer:async()=>Buffer.from('synthetic-preview')})};
 const tasks=ids.map((numerical_task_id,task_ordinal)=>({schema:'DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1',numerical_task_id,task_ordinal}));
 const core={buildDisplayPackage:()=>({workbook:wb,costs:{taskCount:1632,dataRows:1632},charts:[],missingEvidence:true}),buildNavigation:()=>({workbook:wb,nativeHelperRequired:true,nativeHyperlinks:ids.map((id,i)=>({id,i}))}),streamDisplayPackages:async a=>{
  let n=0;for await(const _ of a.lines)n++;assert.equal(n,1632);
  const draft={attempt_index:0,start_task_ordinal:0,stop_task_ordinal:1632};const b=await a.exportPackage(tasks,ids,draft);const e={...draft,sha256:digest(b.bytes),bytes:b.bytes.length};const ref=await a.preserveAttempt(e,b.bytes);
  return{taskCount:1632,unprocessedTaskCount:0,preservedOversizeAttemptCount:0,attempts:[{...e,reference:ref}],packages:[{filename:'package-0001.xlsx',attempt_reference:ref,sha256:e.sha256,byte_count:e.bytes,tasks:ids.map(numerical_task_id=>({numerical_task_id}))}]};}};
 return{dir,state,output:path.join(dir,'out'),core,riskModule:{},artifact:{Workbook:{},SpreadsheetFile:{exportXlsx:async()=>({save:async f=>fs.writeFile(f,'FAKE_NOT_XLSX')})}},applyLinks:async b=>b,sourceGuard:async()=>{},resourceCheck:async()=>{}};
}
test('final output mutation or extra file after manifest is rejected with failed namespace retained',async()=>{
 for(const extra of [false,true]){
  const f=await fixture();f.sourceGuard=async()=>{if(await fs.stat(path.join(f.output,'publication.json')).then(()=>true,()=>false))await fs.writeFile(path.join(f.output,extra?'uninvited.bin':'package-0001.xlsx'),'MUTATED');};
  await assert.rejects(executeDelivery(f));const failure=JSON.parse(await fs.readFile(path.join(f.output,'failure.json')));assert.equal(failure.retry_allowed,false);assert.equal(failure.workbook_delivered,false);await assert.rejects(executeDelivery(f),/EEXIST/);
 }
});
test('full original machine bytes and per-shard pointers preserve UTF8 and missing terminal line fails',async()=>{
 const d=await fs.mkdtemp(path.join(os.tmpdir(),'h-bytes-review-'));const lines=['{"s":"汉字"}\n','{"n":6222659648236112670}\n'];const raw=Buffer.from(lines.join('')),src=path.join(d,'src');await fs.writeFile(src,raw);const out=path.join(d,'out');await fs.mkdir(out);const state={};const got=[];
 for await(const b of copyTaskLines(src,out,state,{maxShardBytes:64,maxShardRows:1,resourceCheck:async()=>{}}))got.push(b);
 assert.deepEqual(Buffer.concat(got),raw);assert.equal(state.sha256,digest(raw));for(let i=0;i<2;i++){assert.equal(state.task_locations[i].row_sha256,digest(Buffer.from(lines[i])));assert.equal(state.task_locations[i].byte_start,0);assert.equal(state.shards[i].record_count,1);}
 await fs.writeFile(src,raw.subarray(0,-1));const bad=path.join(d,'bad');await fs.mkdir(bad);const failed={};await assert.rejects(async()=>{for await(const _ of copyTaskLines(src,bad,failed,{resourceCheck:async()=>{}})){}},/Partial/);assert.notEqual(failed.complete,true);assert.equal(await fs.stat(path.join(bad,'tasks.jsonl')).then(()=>true),true);
});
test('authenticated component dependency graph accepts exact risk path import and rejects arbitrary relative dependency',async()=>{
 assert.equal(typeof publisher.loadCore,'function');const bytes={};for(const k of ['core','path_component','risk_component','navigation_component'])bytes[k]=await fs.readFile(BOUND[k].path);
 const modules=await publisher.loadCore(bytes);assert.equal(typeof modules.core.streamDisplayPackages,'function');assert.equal(typeof modules.risk_component.prepareRiskTables,'function');
 bytes.risk_component=Buffer.concat([bytes.risk_component,Buffer.from("\nimport './unexpected.mjs';\n")]);await assert.rejects(publisher.loadCore(bytes));
});
test('resource stop before export keeps started failure and refuses any same-namespace retry',async()=>{
 const f=await fixture();let exports=0;f.artifact.SpreadsheetFile.exportXlsx=async()=>{exports++;throw Error('should not export');};f.resourceCheck=async()=>{throw Error('RESOURCE_STOP_BEFORE_DISPATCH');};await assert.rejects(executeDelivery(f),/RESOURCE_STOP/);assert.equal(exports,0);const failed=JSON.parse(await fs.readFile(path.join(f.output,'failure.json')));assert.equal(failed.stream_completed,false);assert.equal(failed.retry_allowed,false);assert.equal(failed.formal_comparison_passed,false);await assert.rejects(fs.stat(path.join(f.output,'publication.json')));await assert.rejects(executeDelivery(f),/EEXIST/);
});
