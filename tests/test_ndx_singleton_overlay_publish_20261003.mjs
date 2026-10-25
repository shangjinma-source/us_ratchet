import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs/promises';
import {loadInputs,parseDisplayRow} from '../scripts/ndx_dated_singleton_overlay_publish_20261003.mjs';
test('future terminal parent pins reject before filesystem/source access',async()=>{const original=fs.readFile;let read=false;fs.readFile=async()=>{read=true;throw Error('unexpected read');};try{await assert.rejects(loadInputs());assert.equal(read,false);}finally{fs.readFile=original;}});
test('display parser retains bigint exact tokens and rejects fake exponent overflow',()=>{const row=parseDisplayRow(Buffer.from('{"denominator":6222659648236112670,"x":0.01}'));assert.equal(row.denominator,6222659648236112670n);assert.equal(row.x,.01);assert.throws(()=>parseDisplayRow(Buffer.from('{"x":1e400}')));assert.throws(()=>parseDisplayRow(Buffer.from('{"x":1e30}')));});
import {compareCellCaptures} from '../scripts/ndx_dated_singleton_overlay_publish_20261003.mjs';
test('all saved cells preserve values and formulas except exact registered B5 delta',()=>{
 const id='a'.repeat(64),f=e=>`=IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=1),${e},NA()),NA())`;
 const old=[{worksheet:'路径查看',start_row_zero_based:4,start_column_zero_based:1,row_count:2,column_count:2,values:[['#VALUE!',null],[1,'source']],formulas:[[f("INDEX('任务索引'!$B$2:$B$2,$B$4)"),null],[null,'=A1']]}];
 const fresh=structuredClone(old);fresh[0].values[0][0]='ID: '+id;fresh[0].formulas[0][0]=f("'任务索引'!$B$2");assert.equal(compareCellCaptures(old,fresh,id).checked_cells,4);
 for(const edit of [r=>r[0].values[0][1]=0,r=>r[0].values[1][0]=2,r=>r[0].formulas[1][1]='=A2',r=>r[0].values[0][0]='wrong',r=>r[0].start_row_zero_based=5]){const bad=structuredClone(fresh);edit(bad);assert.throws(()=>compareCellCaptures(old,bad,id));}
});
