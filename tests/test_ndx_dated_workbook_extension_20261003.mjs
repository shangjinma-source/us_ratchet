import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import {createHash} from 'node:crypto';
import {restoreTaskDisplay,inspectPackage,streamDisplayPackages,run,SOURCE_PINS} from '../scripts/ndx_dated_workbook_extension_20261003.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
const saved=JSON.parse(fs.readFileSync(new URL('../tmp/dated_workbook_qa_20261003/path-chart-fixture.json',import.meta.url),'utf8'));
function fixture(){
 const tasks=structuredClone(saved),shared={schema:'DATED_WORKBOOK_EXTENSION_SHARED_DATA_V1',series:{},risk:{}};
 const roles=['incumbent_integer','incumbent_continuous','STRICT_SAME_SESSION_FX','BACKWARD_LATEST_VALID_FX'];
 const compact=tasks.map((t,i)=>{t.task_ordinal=i;const row=structuredClone(t);for(const [n,role]of roles.entries()){
  const id=String(n+5).repeat(64),identity={role,source_reference:t.source_index[role]};
  shared.series[id]={identity,series:structuredClone(t.series[role])};row.series[role]={shared_series_id:id};
  if(role.startsWith('incumbent')){shared.risk[id]={identity,risk:structuredClone(t.risk_tracks[role])};row.risk_tracks[role]={shared_risk_id:id};}
 }return row;});
 const lines=compact.map(t=>Buffer.from(JSON.stringify(t)+'\n'));let offset=0;
 const entries=lines.map((b,i)=>{const e={numerical_task_id:tasks[i].numerical_task_id,task_ordinal:i,status:'DISPLAY_PROJECTED',jsonl_record:{record_index:i,byte_start:offset,byte_stop:offset+b.length,row_sha256:hash(b)}};offset+=b.length;return e;});
 const index={planned_task_count:3,task_index:entries,task_jsonl_reference:{sha256:hash(Buffer.concat(lines)),byte_count:offset,record_count:3},package_plan:{packages:[{tasks:entries}]}};
 return{tasks,shared,compact,lines,index,expectedTaskIds:tasks.map(t=>t.numerical_task_id)};
}
function adapters(f,threshold=1){const attempts=[],failed=[];return{...f,attempts,failed,maxXlsxBytes:10,
 exportPackage:async tasks=>({bytes:Buffer.alloc(tasks.length>threshold?11:8),chartSources:[{categoryRange:'saved'}]}),
 preserveAttempt:async(e,b)=>{attempts.push(e);return{path:'attempt-'+e.attempt_index,sha256:hash(b)};},onFailure:async e=>{failed.push(e);}};}
test('restore all shared identities without mutating evidence',()=>{
 const f=fixture(),before=structuredClone(f.compact);for(let i=0;i<3;i++)assert.deepEqual(restoreTaskDisplay(f.compact[i],f.shared),f.tasks[i]);assert.deepEqual(f.compact,before);
 for(const attack of ['identity','riskid','source']){const bad=structuredClone(f);if(attack==='identity')bad.shared.series['5'.repeat(64)].identity.role='wrong';else if(attack==='riskid')bad.compact[0].risk_tracks.incumbent_integer.shared_risk_id='6'.repeat(64);else bad.shared.series['5'.repeat(64)].series.source_reference.path='wrong';assert.throws(()=>restoreTaskDisplay(bad.compact[0],bad.shared));}
});
test('actual oversize splits contiguous domain and preserves attempts before success',async()=>{
 const f=adapters(fixture());const out=await streamDisplayPackages(f);
 assert.equal(out.taskCount,3);assert.equal(out.packages.length,3);assert.equal(out.preservedOversizeAttemptCount,2);
 assert.deepEqual(out.packages.flatMap(p=>p.tasks.map(t=>t.numerical_task_id)),f.expectedTaskIds);
 assert.equal(out.attempts.length,5);assert.equal(out.workbookDelivered,false);assert.equal(out.sourceBytesAuthenticated,false);assert.equal(f.failed.length,0);
});
test('late source hash failure invalidates all pending outputs and no retry',async()=>{
 const f=adapters(fixture(),3);f.index.task_jsonl_reference.sha256='0'.repeat(64);
 await assert.rejects(streamDisplayPackages(f),/EOF hash/);assert.equal(f.attempts.length,1);assert.equal(f.failed.length,1);assert.equal(f.failed[0].retryAllowed,false);
});
test('byte position/task reorder/missing tail are not compressed',async()=>{
 for(const attack of ['offset','tail','reorder']){const f=adapters(fixture(),3);if(attack==='offset')f.index.task_index[1].jsonl_record.byte_start++;else if(attack==='tail')f.lines.pop();else [f.lines[0],f.lines[1]]=[f.lines[1],f.lines[0]];await assert.rejects(streamDisplayPackages(f));assert.equal(f.failed.length,1);}
});
test('single oversized task blocked, bounds cannot weaken 50MiB, publisher absent',async()=>{
 const f=adapters(fixture(),0);await assert.rejects(streamDisplayPackages(f),/SINGLE_TASK/);assert(f.attempts.every(x=>x.status==='OVERSIZE_ATTEMPT_NOT_ACCEPTED'));
 await assert.rejects(streamDisplayPackages({...adapters(fixture()),maxXlsxBytes:50*1024*1024+1}));assert.throws(()=>run(),/NOT_IMPLEMENTED/);assert.equal(SOURCE_PINS.index,null);
 assert.throws(()=>inspectPackage(f.tasks,f.expectedTaskIds,{maxTotalRows:1}),/BLOCKED/);
});

test('full1632 missing metadata stays in order without invented paths',async()=>{
 const f=fixture();const expectedTaskIds=Array.from({length:1632},(_,i)=>i.toString(16).padStart(64,'0'));
 const missingFlags=Object.fromEntries(['source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','account_executed','fit_performed','economic_metrics_recomputed','risk_reaggregated','workbook_delivered','charts_rendered','visual_acceptance_passed','xlsx_actual_size_limit_verified','full_transitive_source_closure_reverified'].map(k=>[k,false]));
 const rows=expectedTaskIds.map((id,i)=>({...missingFlags,schema:'DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1',numerical_task_id:id,task_ordinal:i,status:'COMPARISON_NOT_SUPPLIED'}));
 const lines=rows.map(t=>Buffer.from(JSON.stringify(t)+'\n'));let offset=0;
 const entries=lines.map((b,i)=>{const e={numerical_task_id:expectedTaskIds[i],task_ordinal:i,status:'COMPARISON_NOT_SUPPLIED',jsonl_record:{record_index:i,byte_start:offset,byte_stop:offset+b.length,row_sha256:hash(b)}};offset+=b.length;return e;});
 const index={planned_task_count:1632,task_index:entries,task_jsonl_reference:{sha256:hash(Buffer.concat(lines)),byte_count:offset,record_count:1632},package_plan:{packages:[{tasks:entries}]}};
 let max=0;const args=adapters({lines,index,shared:f.shared,expectedTaskIds},32);args.exportPackage=async tasks=>{max=Math.max(max,tasks.length);assert(tasks.every(t=>t.status==='COMPARISON_NOT_SUPPLIED'));return{bytes:Buffer.alloc(8),chartSources:[]};};
 const out=await streamDisplayPackages(args);assert.equal(out.taskCount,1632);assert.equal(out.unprocessedTaskCount,0);assert(max<=8);assert.equal(out.packages.length,204);
 assert(out.packages.every(p=>p.tasks.every(t=>t.integer_status==='COMPARISON_NOT_SUPPLIED')));
});

test('present shared-restored tasks preserve original unsafe integer token end to end',async()=>{
 const f=fixture();
 f.lines=f.compact.map(t=>{t.original_task_summary_row.independent_report_preserved={full_plan_task_denominator:'LOSSLESS_TOKEN'};return Buffer.from(JSON.stringify(t).replace('"LOSSLESS_TOKEN"','6222659648236112670')+'\n');});
 let offset=0;f.lines.forEach((b,i)=>{f.index.task_index[i].jsonl_record={record_index:i,byte_start:offset,byte_stop:offset+b.length,row_sha256:hash(b)};offset+=b.length;});
 f.index.task_jsonl_reference={sha256:hash(Buffer.concat(f.lines)),byte_count:offset,record_count:3};
 const a=adapters(f);a.exportPackage=async tasks=>{for(const t of tasks)assert.equal(t.original_task_summary_row.independent_report_preserved.full_plan_task_denominator,6222659648236112670n);return{bytes:Buffer.alloc(8),chartSources:[]};};
 const out=await streamDisplayPackages(a);assert.equal(out.taskCount,3);assert.equal(out.streamSha256,hash(Buffer.concat(f.lines)));assert.equal(out.originalJsonlBytesReencoded,false);
});
