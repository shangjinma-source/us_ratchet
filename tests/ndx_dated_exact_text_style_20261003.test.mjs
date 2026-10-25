import test from 'node:test';
import assert from 'node:assert/strict';
import {exactTextFormat, buildWorkbook} from '../scripts/ndx_dated_comparison_workbook_20261003.mjs';
import {fixture} from './ndx_dated_comparison_workbook_20261003.test.mjs';
test('bounded literal formats preserve exact strings',()=>{
 for(const s of ['6222659648236112670','6222659648236111038','0'.repeat(63)+'1','0'.repeat(63)+'a','001']) assert.equal(exactTextFormat(s),`"${s}"`);
 for(const s of ['word','C:/path','12','0','=formula']) assert.equal(exactTextFormat(s),'@');
 for(const v of [null,0,0.25,false]) assert.equal(exactTextFormat(v),null);
 assert.throws(()=>exactTextFormat('1'.repeat(65)));
});
test('mock build never changes source or assigned data values; numeric formats retained',()=>{
 const payload=fixture(),before=structuredClone(payload),writes=[],formats=[];
 const Workbook={create:()=>({worksheets:{add:name=>({getRange:()=>({format:{},setNumberFormat(){}}),getRangeByIndexes:(r,c,h,w)=>({format:{},set values(v){writes.push({name,r,c,h,w,v});},setNumberFormat(v){formats.push({name,r,c,h,w,v});}}),tables:{add(){}},freezePanes:{freezeRows(){},freezeColumns(){}}})},recalculate(){}})};
 buildWorkbook(Workbook,payload);assert.deepEqual(payload,before);
 for(const table of payload.display.tables){const actual=writes.find(x=>x.name===table.name&&x.r===4&&x.w===table.headers.length);assert.deepEqual(actual.v,table.rows);}
 assert(formats.some(x=>x.v==='"6222659648236112670"'));
 assert(formats.some(x=>x.v==='0.0%;(0.0%);0.0%'));
});
