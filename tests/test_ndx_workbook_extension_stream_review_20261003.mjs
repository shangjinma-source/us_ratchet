import assert from 'node:assert/strict';
import test from 'node:test';
import {createHash} from 'node:crypto';
import {streamDisplayPackages,run,SOURCE_PINS} from '../scripts/ndx_dated_workbook_extension_20261003.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
const flags=Object.fromEntries(['source_bytes_authenticated','formal_comparison_passed','point_in_time_verified','promotion_allowed','future_independent_oos','account_executed','fit_performed','economic_metrics_recomputed','risk_reaggregated','workbook_delivered','charts_rendered','visual_acceptance_passed','xlsx_actual_size_limit_verified','full_transitive_source_closure_reverified'].map(k=>[k,false]));
function fixture(n=1632){
 const expectedTaskIds=Array.from({length:n},(_,i)=>(i+1).toString(16).padStart(64,'0'));
 const rows=expectedTaskIds.map((tid,i)=>{const entry={numerical_task_id:tid,task_ordinal:i,k:4+Math.floor(i/96),weight_spec:{kind:['equal','fixed','anchor'][Math.floor(i/32)%3]},status:'COMPARISON_NOT_SUPPLIED',jsonl_record:null};return{schema:'DATED_WORKBOOK_TASK_EXTENSION_MISSING_V1',numerical_task_id:tid,task_ordinal:i,status:'COMPARISON_NOT_SUPPLIED',original_path_index_row:structuredClone(entry),original_chain_index_row:structuredClone(entry),source_jsonl_records:{path:null,chain:null},...flags};});
 const f={expectedTaskIds,rows,shared:{schema:'DATED_WORKBOOK_EXTENSION_SHARED_DATA_V1',series:Object.fromEntries([1,2,3,4].map(i=>[String(i).repeat(64),{}])),risk:Object.fromEntries([1,2].map(i=>[String(i).repeat(64),{}]))}};reindex(f);return f;
}
function reindex(f){let offset=0;f.lines=f.rows.map(r=>Buffer.from(JSON.stringify(r)+'\n'));const entries=f.lines.map((b,i)=>{const e={...structuredClone(f.rows[i].original_path_index_row),jsonl_record:{record_index:i,byte_start:offset,byte_stop:offset+b.length,row_sha256:hash(b)}};offset+=b.length;return e;});f.index={planned_task_count:entries.length,task_index:entries,task_jsonl_reference:{sha256:hash(Buffer.concat(f.lines)),byte_count:offset,record_count:entries.length},package_plan:{packages:[{tasks:structuredClone(entries)}]}};}
function args(f){const attempts=[],failed=[];return{...f,attempts,failed,maxXlsxBytes:10,exportPackage:async()=>({bytes:Buffer.alloc(8,3),chartSources:[]}),preserveAttempt:async(e,b)=>{attempts.push(structuredClone(e));return{path:'attempt-'+e.attempt_index,sha256:hash(b)};},onFailure:async e=>failed.push(structuredClone(e))};}

test('full1632 one serial iterator bounded callbacks missing remains missing',async()=>{
 const f=args(fixture());let iterations=0,readCount=0,max=0;
 f.lines={async *[Symbol.asyncIterator](){iterations++;for(const line of fixture().lines){readCount++;yield line;}}};
 f.exportPackage=async(tasks,ids,draft)=>{max=Math.max(max,tasks.length);assert.equal(readCount,draft.stop_task_ordinal);assert(tasks.every(t=>t.status==='COMPARISON_NOT_SUPPLIED'&&!('series'in t)));return{bytes:Buffer.alloc(8),chartSources:[]};};
 const out=await streamDisplayPackages(f);assert.equal(iterations,1);assert.equal(max,8);assert.equal(out.taskCount,1632);assert.equal(out.packages.length,204);assert.deepEqual(out.packages.flatMap(p=>p.tasks.map(t=>t.numerical_task_id)),f.expectedTaskIds);assert.equal(out.sourceBytesAuthenticated,false);assert.equal(out.workbookDelivered,false);
 for(const key of ['index','publication','independent_readback','tasks','shared','classification'])assert.equal(SOURCE_PINS[key],null);assert.throws(()=>run(),/NOT_IMPLEMENTED/);
});
test('oversize attempts retained before continuous recursive splitting and EOF failure invalidates prefixes',async()=>{
 const f=args(fixture(8));f.exportPackage=async tasks=>({bytes:Buffer.alloc(tasks.length>2?11:8),chartSources:[]});const out=await streamDisplayPackages(f);
 assert.equal(out.attempts.length,7);assert.equal(out.preservedOversizeAttemptCount,3);assert.deepEqual(out.packages.map(p=>[p.start_task_ordinal,p.stop_task_ordinal]),[[0,2],[2,4],[4,6],[6,8]]);assert(out.attempts.every((a,i)=>a.attempt_index===i));
 const bad=args(fixture(9));bad.index.task_jsonl_reference.sha256='f'.repeat(64);await assert.rejects(streamDisplayPackages(bad));assert.equal(bad.failed.length,1);assert.equal(bad.failed[0].retryAllowed,false);assert.equal(bad.attempts.length,2);assert.equal(bad.failed[0].acceptedPendingPackages.length,2);
});
test('input index ordinal and missing authority cannot be resigned into acceptance',async()=>{
 const f=args(fixture(3));f.index.task_index[0].task_ordinal=2;await assert.rejects(streamDisplayPackages(f));
 const g=fixture(3);g.rows[0].point_in_time_verified=true;reindex(g);await assert.rejects(streamDisplayPackages(args(g)));
});
test('export callback must not mutate original task evidence or identity coordinates',async()=>{
 for(const mutate of [t=>t[0].task_ordinal=1,t=>t[0].original_path_index_row.k=99]){
  const f=args(fixture(3));f.exportPackage=async tasks=>{mutate(tasks);return{bytes:Buffer.alloc(8),chartSources:[]};};await assert.rejects(streamDisplayPackages(f));
 }
});
test('preserve callback cannot change declared byte evidence or mutate exported bytes',async()=>{
 for(const mutate of [(e,b)=>e.bytes=1,(e,b)=>b[0]=77]){
  const f=args(fixture(3));f.preserveAttempt=async(e,b)=>{const before=hash(b);mutate(e,b);return{path:'attempt',sha256:before};};await assert.rejects(streamDisplayPackages(f));
 }
});

test('export failure records attempted range distinctly from saved and accepted attempts',async()=>{
 const f=args(fixture(3));f.exportPackage=async()=>{throw new Error('synthetic export failure');};await assert.rejects(streamDisplayPackages(f),/synthetic export failure/);assert.equal(f.failed.length,1);
 assert.equal(f.failed[0].exportAttemptCount,1);assert.equal(f.failed[0].attempts.length,0);assert.equal(f.failed[0].acceptedPendingPackages.length,0);assert.deepEqual(f.failed[0].unresolvedAttempt.task_ids,f.expectedTaskIds);assert.equal(f.failed[0].unresolvedAttempt.start_task_ordinal,0);assert.equal(f.failed[0].unresolvedAttempt.stop_task_ordinal,3);
});

test('lossless original integer token survives complete stream and typed mutation guard',async()=>{
 const make=()=>{
  const f=fixture(1);f.rows[0].original_task_summary_row={independent_report_preserved:{full_plan_task_denominator:'TOKEN'}};reindex(f);
  const line=Buffer.from(f.lines[0].toString().replace('"TOKEN"','6222659648236112670'));
  f.lines=[line];f.index.task_index[0].jsonl_record={record_index:0,byte_start:0,byte_stop:line.length,row_sha256:hash(line)};
  f.index.task_jsonl_reference={sha256:hash(line),byte_count:line.length,record_count:1};return args(f);
 };
 const f=make(),original=Buffer.from(f.lines[0]);
 f.exportPackage=async tasks=>{const n=tasks[0].original_task_summary_row.independent_report_preserved.full_plan_task_denominator;assert.equal(typeof n,'bigint');assert.equal(n,6222659648236112670n);return{bytes:Buffer.alloc(8),chartSources:[]};};
 const out=await streamDisplayPackages(f);assert.equal(out.streamSha256,hash(original));assert.deepEqual(f.lines[0],original);assert.equal(out.jsonRuntimeEncoding,'NATIVE_JSON_WITH_UNSAFE_INTEGER_TOKENS_AS_BIGINT_V1');assert.equal(out.originalJsonlBytesReencoded,false);
 const bad=make();bad.exportPackage=async tasks=>{tasks[0].original_task_summary_row.independent_report_preserved.full_plan_task_denominator='6222659648236112670';return{bytes:Buffer.alloc(8),chartSources:[]};};await assert.rejects(streamDisplayPackages(bad),/mutated/);
});

test('BigInt does not relax task indices and nonfinite or unsafe exponent remains rejected',async()=>{
 for(const [field,token] of [['task_ordinal','6222659648236112670'],['evidence','1e400'],['evidence','1e30']]){
  const f=fixture(1);if(field==='evidence')f.rows[0].evidence=0;reindex(f);
  const line=Buffer.from(f.lines[0].toString().replace('"'+field+'":0','"'+field+'":'+token));f.lines=[line];f.index.task_index[0].jsonl_record={record_index:0,byte_start:0,byte_stop:line.length,row_sha256:hash(line)};f.index.task_jsonl_reference={sha256:hash(line),byte_count:line.length,record_count:1};await assert.rejects(streamDisplayPackages(args(f)));
 }
});
