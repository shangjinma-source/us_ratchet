'use strict';
const assert=require('assert');
const path=require('path');
const source=process.env.DAILY_CONTROLLER_SOURCE||path.join(__dirname,'../web/strategy_daily_controller.js');
const ui=require(path.resolve(source));
assert.match(ui.waitingExplanation('WAIT_KNOWN_ACTION_REVIEW'),/尚待核验/);
assert.match(ui.waitingExplanation('WAIT_KNOWN_ACTION_REVIEW'),/旧价格不可用于挂单/);
assert.equal(ui.waitingExplanation('SUPPLEMENT_REVIEW_FAILED:OTHER'),null);
console.log('news preview reason message PASS');
