import assert from 'node:assert/strict';
import {test} from 'node:test';
import fs from 'node:fs';
import {validatePathTasks} from '../scripts/ndx_dated_path_chart_component_20261003.mjs';
const original=JSON.parse(fs.readFileSync(new URL('../tmp/dated_workbook_qa_20261003/path-chart-fixture.json',import.meta.url),'utf8'));
const fresh=()=>structuredClone(original);
const check=tasks=>validatePathTasks(tasks,tasks.map(t=>t.numerical_task_id));
test('saved fixture, immutable literal IDs, order and shared reference changes',()=>{
 const t=fresh(),before=structuredClone(t);check(t);assert.deepEqual(t,before);
 assert.throws(()=>validatePathTasks(t,[...t.map(x=>x.numerical_task_id)].reverse()));
 t[1].series.incumbent_integer.source_reference.sha256='b'.repeat(64);assert.throws(()=>check(t));
});
test('missing account must never become finite cash line',()=>{
 const t=fresh();for(const s of t[1].series.candidate_integer.slots){s.display_value=1;s.display_status='FINITE_BINARY_FLOAT_DISPLAY';}
 assert.throws(()=>check(t));
});
test('finite and missing scalar correspondence; exact zero is not underflow',()=>{
 for(const [exact,value,status] of [[null,1,'FINITE_BINARY_FLOAT_DISPLAY'],['0',null,'OUTSIDE_DISPLAY_PRECISION'],['1e-400',0,'FINITE_BINARY_FLOAT_DISPLAY'],[true,1,'FINITE_BINARY_FLOAT_DISPLAY']]){
  const t=fresh();Object.assign(t[0].series.candidate_integer.slots[0],{exact_value:exact,display_value:value,display_status:status});assert.throws(()=>check(t));
 }
});
test('full canonical dates and first return predecessor',()=>{
 const t=fresh();for(const row of t){row.calendar[1]='2026-03-21';for(const v of Object.values(row.series))v.slots[1].session='2026-03-21';}assert.throws(()=>check(t));
});
test('source bindings and all authority flags, not just shared equality',()=>{
 for(const change of [t=>{t[0].risk_recomputed=true;},t=>{for(const x of t)x.series.STRICT_SAME_SESSION_FX.source_reference={};}]){const t=fresh();change(t);assert.throws(()=>check(t));}
});
test('rational overflow, binary64 subnormal and ties retain saved exact evidence',()=>{
 const power=10n**400n;
 const cases=[
  ['1/3',1/3,'FINITE_BINARY_FLOAT_DISPLAY'],
  [{numerator:String(power),denominator:String(3n*power)},1/3,'FINITE_BINARY_FLOAT_DISPLAY'],
  [{numerator:'1',denominator:String(2n**1075n)},null,'OUTSIDE_DISPLAY_PRECISION'],
  [{numerator:'1',denominator:String(2n**1074n)},Number.MIN_VALUE,'FINITE_BINARY_FLOAT_DISPLAY'],
  [{numerator:String(2n**53n+1n),denominator:String(2n**53n)},1,'FINITE_BINARY_FLOAT_DISPLAY'],
  [{numerator:String(2n**53n+3n),denominator:String(2n**53n)},1+2**-51,'FINITE_BINARY_FLOAT_DISPLAY'],
  ['1e400',null,'OUTSIDE_DISPLAY_PRECISION'],
 ];
 for(const [exact,value,status] of cases){const t=fresh();Object.assign(t[0].series.candidate_integer.slots[1],{exact_value:exact,display_value:value,display_status:status});check(t);assert.deepEqual(t[0].series.candidate_integer.slots[1].exact_value,exact);}
});
test('source index, finite display mismatch, malformed saved numerics and wrong mode reject',()=>{
 for(const change of [
  t=>{t[0].source_index.candidate_integer.sha256='f'.repeat(64);},
  t=>{t[0].series.candidate_integer.slots[1].display_value=2;},
  t=>{t[0].series.candidate_integer.slots[1].exact_value='=1+1';},
  t=>{t[0].series.candidate_integer.slots[1].exact_value={numerator:'1',denominator:'0'};},
  t=>{for(const r of t)r.series.STRICT_SAME_SESSION_FX.status='AVAILABLE';},
 ]){const t=fresh();change(t);assert.throws(()=>check(t));}
});
