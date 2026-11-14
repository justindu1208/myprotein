// Run with node frontend/tests/molecular-evidence.test.cjs from the repository.
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../molecular-evidence.js'), 'utf8');
const timers = [];
const context = vm.createContext({URL, setTimeout: fn => (timers.push(fn), timers.length), clearTimeout() {}});
vm.runInContext(source.split('const molecularEvidence=')[0] + '\nthis.Viewer=SamsonViewer;', context);
const winners=context.deduplicateWinners([{id:'A',category:'Balanced'},{id:'B',category:'Affinity'},{id:'A',category:'Safety'},{id:'A',category:'Balanced'}]);
assert.deepEqual(JSON.parse(JSON.stringify(winners)),[{id:'A',categories:['Balanced','Safety']},{id:'B',categories:['Affinity']}]);
const frame={hidden:true,removeAttribute(name){delete this[name];}};
let fallbacks=0;
const viewer=new context.Viewer(frame,()=>{fallbacks++;viewer.clear();},()=>{});
assert.equal(viewer.load(null),false);
assert.equal(frame.src,undefined);
assert.throws(()=>viewer.load('https://example.com/documents/12345678-1234-1234-1234-123456789abc'));
// Synthetic URL tests parsing only; this test makes no network requests.
viewer.load('https://www.samson-connect.net/documents/12345678-1234-1234-1234-123456789abc');
assert.equal(frame.hidden,false);
frame.onerror();
assert.equal(fallbacks,1);
assert.equal(frame.src,undefined);
viewer.load('https://www.samson-connect.net/documents/12345678-1234-1234-1234-123456789abc');
timers.at(-1)();
assert.equal(fallbacks,2);
assert.equal(frame.hidden,true);
console.log('PASS: winner deduplication, missing document, URL validation, blocked iframe and timeout fallback');
