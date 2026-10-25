import test from 'node:test';
import assert from 'node:assert/strict';
import {compareCellCaptures,parseDisplayRow} from '../scripts/ndx_dated_singleton_overlay_publish_20261003.mjs';

function fixture(){
 const id='d'.repeat(64),wrap=x=>`=IF(ISNUMBER($B$4),IF(AND($B$4=INT($B$4),$B$4>=1,$B$4<=1),${x},NA()),NA())`;
 const old=[{worksheet:'路径查看',start_row_zero_based:4,start_column_zero_based:0,row_count:2,column_count:3,values:[['label','#VALUE!',null],[-.5,0,'000001']],formulas:[[null,wrap("INDEX('任务索引'!$B$2:$B$2,$B$4)"),null],[null,null,null]]}];
 const fresh=structuredClone(old);fresh[0].values[0][1]=`ID: ${id}`;fresh[0].formulas[0][1]=wrap("'任务索引'!$B$2");
 return {old,fresh,id};
}
test('only B5 delta; null zero negatives and text identifiers preserved',()=>{
 const {old,fresh,id}=fixture(),before=structuredClone([old,fresh]);
 assert.equal(compareCellCaptures(old,fresh,id).checked_cells,6);assert.deepEqual([old,fresh],before);
 for(const change of [x=>x[0].values[0][2]=0,x=>x[0].values[1][0]=.5,x=>x[0].values[1][2]=1,x=>x[0].formulas[1][0]='=0',x=>x[0].row_count=true,x=>x.push(structuredClone(x[0]))]){
  const bad=structuredClone(fresh);change(bad);assert.throws(()=>compareCellCaptures(old,bad,id));
 }
});
test('unrelated sheet B5 and missing repair cell cannot satisfy single repair proof',()=>{
 const {old,fresh,id}=fixture();old[0].worksheet=fresh[0].worksheet='风险查看';
 assert.throws(()=>compareCellCaptures(old,fresh,id));assert.throws(()=>compareCellCaptures([],[],id));
 assert.throws(()=>parseDisplayRow(Uint8Array.from([0xff])));
 assert.equal(parseDisplayRow(Buffer.from('{"x":6222659648236112670}')).x,6222659648236112670n);
});
