const assert=require('node:assert/strict');
const {mapFills,candleSvg}=require('../web/selected_stock_charts.js');
const daily=[{date:'2026-10-14',open:1300,high:1400,low:1200,close:1350}];
const buy={fill_id:'f1',ticker:'SNDK',security_id:'sid',side:'BUY',quantity:14,price:'132221/100',executed_at:'2026-10-16T23:00:00+08:00'};
assert.equal(mapFills(daily,[buy]).outside.length,1);
assert(!candleSvg(daily,null,'day',[buy]).includes('actual-fill-reference'));
const inRange={...buy,executed_at:'2026-10-15T00:30:00+08:00'};
assert.equal(mapFills(daily,[inRange]).mapped[0].day,'2026-10-14');
assert.equal(mapFills(daily,[inRange]).mapped[0].price,1322.21);
assert.match(candleSvg(daily,null,'day',[inRange]),/actual-fill-reference/);
assert.match(candleSvg(daily,null,'day',[inRange]),/未核验/);
for(const interval of ['week','month']){
 const bars=[{...daily[0],first_date:'2026-10-12'}];
 assert.equal(mapFills(bars,[inRange],interval).mapped.length,1);
 assert.equal(mapFills(bars,[buy],interval).outside.length,1,'same incomplete week/month must not swallow future fills');
}
assert.equal(mapFills(daily,[{...inRange,side:'SELL'}]).mapped.length,1);
for(const fill of [{...buy,executed_at:'2026-10-14T10:00:00'},{...buy,price:'NaN'},{...buy,side:'OPEN'}])assert.equal(mapFills(daily,[fill]).invalid.length,1);
const crossYear=[{...daily[0],date:'2027-01-01',first_date:'2026-12-28'}];
assert.equal(mapFills(crossYear,[{...buy,executed_at:'2026-12-31T15:00:00Z'}],'week').mapped.length,1);
console.log('PASS actual fills: NY date, rational price, day/week/month, incomplete-period boundary, invalid inputs, BUY/SELL');
