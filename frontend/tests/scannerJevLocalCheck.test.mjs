import assert from "node:assert/strict";
import test from "node:test";
import { getJevCandidateLocalCheck } from "../src/services/jevApi.ts";

test("S31-P client requests only local candidate evidence by capture identity", async () => {
  const saved = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async (input, init) => {
    calls++;
    assert.equal(init, undefined); // GET only; no outbound market payload.
    const url = new URL(String(input), "http://localhost");
    assert.equal(url.pathname, "/api/simulation/jev/candidate-local-check");
    assert.equal(url.searchParams.get("capture_id"), "cap-a");
    assert.equal(url.searchParams.get("sample_index"), "2");
    assert.equal(url.searchParams.get("market"), "KOSDAQ");
    assert.equal(url.searchParams.get("ticker"), "123456");
    return {
      ok:true, status:200, text:async()=>JSON.stringify({
        capture_id:"cap-a",sample_index:2,market:"KOSDAQ",ticker:"123456",
        status:"LOCAL_CHECK_COMPLETE",local_semantic_status:"LOCAL_MATCH",
        provider_call_authorized:false,model_result_available:false,
        jev_model_calls:0,review_kind:"LOCAL_SEMANTIC_CHECK_NOT_JEV_MODEL",
      }),
    };
  };
  try {
    const result = await getJevCandidateLocalCheck({
      captureId:"cap-a",sampleIndex:2,market:"KOSDAQ",ticker:"123456",
    });
    assert.equal(result.model_result_available,false);
    assert.equal(result.provider_call_authorized,false);
    assert.equal(calls,1);
  } finally { globalThis.fetch = saved; }
});

test("S31-P local endpoint error is not converted into fake AI completion",async()=>{
  const saved=globalThis.fetch;
  globalThis.fetch=async()=>({ok:false,status:422,text:async()=>JSON.stringify({
    detail:{code:"NO_CAPTURE",message:"capture missing"},
  })});
  try{
    await assert.rejects(getJevCandidateLocalCheck({
      captureId:"missing",sampleIndex:0,market:"KOSPI",ticker:"000001",
    }),/capture missing/);
  }finally{globalThis.fetch=saved;}
});
