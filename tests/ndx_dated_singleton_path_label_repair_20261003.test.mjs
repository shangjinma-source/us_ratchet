import assert from 'node:assert/strict';
import {test} from 'node:test';
import {repairSingletonPathLabel, originalSingletonLabelFormula, repairedSingletonLabelFormula} from '../scripts/ndx_dated_singleton_path_label_repair_20261003.mjs';

function fixture() {
  const cells = {B4:{values:[[1]]}, B5:{formulas:[[originalSingletonLabelFormula]], values:[['#VALUE!']]}};
  const label = {values:[['ID: '+'a'.repeat(64)]]};
  const workbook = {worksheets:{getItem:name=>({getRange:address=>name==='路径查看'?cells[address]:label})},
    recalculate:()=>{cells.B5.values=label.values.map(row=>[...row]);}};
  return {workbook,cells,label};
}
test('only B5 formula changes; old error is replaced by bound source label',()=>{
  const {workbook,cells}=fixture();
  const report=repairSingletonPathLabel(workbook,['a'.repeat(64)]);
  assert.equal(cells.B5.formulas[0][0],repairedSingletonLabelFormula);
  assert.deepEqual(cells.B4.values,[[1]]);
  assert.equal(report.workbook_delivered,false);
});
test('reject unknown formula, wrong source identity and nondefault selector before mutation',()=>{
  for(const change of [x=>x.cells.B5.formulas=[['=1']],x=>x.label.values=[['wrong']],x=>x.cells.B4.values=[[2]]]){
    const value=fixture();change(value);const before=JSON.stringify(value.cells);
    assert.throws(()=>repairSingletonPathLabel(value.workbook,['a'.repeat(64)]));
    assert.equal(JSON.stringify(value.cells),before);
  }
});
test('reject larger packages and malformed identities',()=>{
  for(const ids of [[],['a'.repeat(64),'b'.repeat(64)],['bad']]){
    const {workbook,cells}=fixture();
    assert.throws(()=>repairSingletonPathLabel(workbook,ids));
    assert.equal(cells.B5.formulas[0][0],originalSingletonLabelFormula);
  }
});
