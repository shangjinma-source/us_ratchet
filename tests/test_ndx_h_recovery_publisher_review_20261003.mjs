import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createHash} from 'node:crypto';
import {fixture} from './test_ndx_h_failed_export_recovery_publish_20261003.mjs';
import {executeRecovery,SOURCE_PHASE} from '../scripts/ndx_h_failed_export_recovery_publish_20261003.mjs';
import {parseDisplayRow} from '../scripts/ndx_dated_singleton_overlay_publish_20261003.mjs';
import {parseMetadata} from '../scripts/ndx_dated_workbook_extension_publish_20261003.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');

test('review fixed source pin and exact integer survive recovered metadata without granting parent success',async()=>{
 assert.equal(hash(await fs.readFile(SOURCE_PHASE.path)),SOURCE_PHASE.sha256);
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'h-review-exact-'));
 try{
  const a=await fixture(root);a.c.machine.saved_denominator=6222659648236112670n;
  const r=await executeRecovery(a),m=JSON.parse(await fs.readFile(r.path));
  assert.equal(m.parent_status,'FAILED_DO_NOT_CONSUME');assert.equal(m.old_publication_existed,false);
  for(const k of ['workbook_delivered','independent_export_readback_passed','visual_acceptance_passed','economics_recomputed','native_excel_open_verified'])assert.equal(m[k],false);
  const raw=await fs.readFile(m.machine_index_reference.path);
  assert.equal(parseDisplayRow(raw).saved_denominator,6222659648236112670n);
  assert.equal(parseMetadata(raw).value.saved_denominator,'6222659648236112670');
  assert.equal(parseMetadata(raw).value.record_count,1632);
  assert(raw.includes(Buffer.from('6222659648236112670')));
  assert.equal(m.parent_failure_reference.sha256,a.refs.failure.sha256);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});

test('review final package mutation and extra file both reject even after publication exists',async()=>{
 for(const attack of ['package','extra']){
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'h-review-final-'));
  try{
   const a=await fixture(root);let calls=0;
   a.parentGuard=async()=>{if(++calls===2)await fs.writeFile(path.join(a.output,attack==='package'?'package-0001.xlsx':'foreign.bin'),'late drift');};
   await assert.rejects(executeRecovery(a));assert.equal(calls,2);
   const f=JSON.parse(await fs.readFile(path.join(a.output,'failure.json')));
   assert.equal(f.status,'FAILED_NO_RETRY');assert.equal(f.workbook_delivered,false);
   assert(f.saved_references.some(x=>x.path.endsWith('publication.json')));
   await assert.rejects(executeRecovery(a),/Exclusive new recovery/);
  }finally{await fs.rm(root,{recursive:true,force:true});}
 }
});

test('review SDK returned blob partially saved then threw: preserve physical evidence and prohibit final publication',async()=>{
 const root=await fs.mkdtemp(path.join(os.tmpdir(),'h-review-partial-'));
 try{
  const a=await fixture(root),p=a.c.plan.packages[0],id=p.task_ids[0];
  p.action='REBUILD_SINGLETON_WITH_REGISTERED_B5_ONLY_DELTA';p.stop_task_ordinal=1;p.task_ids=[id];
  const raw=Buffer.from(JSON.stringify({task_ordinal:0,numerical_task_id:id})+'\n');
  await fs.writeFile(a.refs.tasks.path,raw);a.refs.tasks.sha256=hash(raw);
  a.d.index.task_index[0].jsonl_record={record_index:0,byte_start:0,byte_stop:raw.length,row_sha256:hash(raw)};
  const pending=a.c.attempts[0].pending;
  pending.expected_cells_reference.ranges=[];
  const chart=Buffer.from(JSON.stringify({charts:[],risk_source_index:[],task_evidence:[],engine_evidence:[]}));
  await fs.writeFile(pending.chart_source_index_reference.path,chart);pending.chart_source_index_reference.sha256=hash(chart);
  // Real capture parser needs at least one record; its content gate is independently
  // covered by the frozen preservation tests, while this case isolates SDK failure.
  pending.expected_cells_reference.ranges=[{worksheet:'x',rows:1,columns:1}];
  const wb={worksheets:{getItem:()=>({getRangeByIndexes:()=>({values:[[null]],formulas:[[null]]})})}};
  a.modules.core.restoreTaskDisplay=x=>x;
  a.modules.core.buildDisplayPackage=()=>({workbook:wb,costs:pending.costs,charts:[],riskSourceIndex:[],taskEvidence:[],engineEvidence:[]});
  a.repair.repairSingletonPathLabel=()=>({});a.preserved.compareCellCaptures=()=>({changed_cells:1});
  let returned=0;
  a.artifact.SpreadsheetFile={exportXlsx:async()=>{returned++;return {save:async file=>{await fs.writeFile(file,'partial SDK bytes');throw Error('SDK save interrupted');}};}};
  await assert.rejects(executeRecovery(a),/SDK save interrupted/);assert.equal(returned,1);
  assert.equal(await fs.readFile(path.join(a.output,p.filename),'utf8'),'partial SDK bytes');
  const f=JSON.parse(await fs.readFile(path.join(a.output,'failure.json')));assert.equal(f.status,'FAILED_NO_RETRY');
  assert.equal(f.saved_references.some(x=>x.path.endsWith(p.filename)),false);
  await assert.rejects(fs.stat(path.join(a.output,'export_manifest.json')),/ENOENT/);
  await assert.rejects(executeRecovery(a),/Exclusive new recovery/);
 }finally{await fs.rm(root,{recursive:true,force:true});}
});
