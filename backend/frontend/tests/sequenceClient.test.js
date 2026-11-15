import test from 'node:test';
import assert from 'node:assert/strict';
import { loadSequence } from '../src/services/sequenceClient.js';
const params={coordinates:'10, -20',settings:{fovArcmin:'6',detectorArray:'6'}};
const done={status:'done',manifest:{query:{ra_deg:10,dec_deg:-20,detector:'D6',fov_deg:.1},frames:[],visits:[]}};
test('202 is polled, input units and detector converted',async()=>{
 const calls=[];
 const result=await loadSequence(params,{wait:async()=>{},fetchImpl:async url=>{
 calls.push(url);return {ok:true,json:async()=> calls.length===1 ? {status:'running'} : done};
 }});
 assert.equal(calls.length,2);const q=new URL(calls[0],'http://localhost').searchParams;
 assert.equal(q.get('q'),'10, -20');assert.equal(q.get('fov'),'0.1');assert.equal(q.get('det'),'D6');
 assert.deepEqual(result.player.frames,[]);
});
test('backend error is surfaced, without endless polling',async()=>{
 await assert.rejects(loadSequence(params,{fetchImpl:async()=>({ok:false,status:502,json:async()=>({error:'Archive unavailable'})})}),/Archive unavailable/);
});
test('unsupported FOV fails before network request',async()=>{
 await assert.rejects(loadSequence({...params,settings:{...params.settings,fovArcmin:'10'}},{fetchImpl:()=>{throw Error('network must not run');}}),/Supported fields/);
});
test('abort stops pending polling',async()=>{
 const controller=new AbortController();
 await assert.rejects(loadSequence(params,{signal:controller.signal,fetchImpl:async()=>{controller.abort();return {ok:true,json:async()=>({status:'queued'})};}}),{name:'AbortError'});
});
test('invalid detectors and malformed job states fail immediately', async () => {
 await assert.rejects(loadSequence({...params,settings:{...params.settings,detectorArray:'9'}}), /Select detector/);
 await assert.rejects(loadSequence(params,{fetchImpl:async()=>({ok:true,json:async()=>({status:'unknown'})})}), /Unexpected processing state/);
});
