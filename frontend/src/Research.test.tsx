// @vitest-environment jsdom
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import Research from "./Research";
import scenarios from "../../mandate/demo_scenarios.json";

afterEach(() => { cleanup(); vi.unstubAllGlobals(); localStorage.clear(); });

it.each(scenarios)("uses the normal research cards and allocation form for $ticker", async (scenario) => {
  const ticker = 'DEMO-'+scenario.ticker;
  const cid = 'british_thoracic_society';
  const approved = scenario.cap > 0;
  const verdict = scenario.decision === 'REJECT' ? 'FAIL' : scenario.decision === 'TRUSTEE_REVIEW' ? 'FLAG' : 'PASS';
  const specialist = (agent:string,index:number) => ({ticker, agent, model:'Scripted demo',score:null,summary:scenario.notes[index],reasons:[]});
  const report = {simulated:true,devils_advocate:scenario.challenges,
    melchior:{ticker,agent:'melchior',model:'Scripted demo',verdicts:[{rule_id:'DEMO-R1', verdict,confidence:0,quote:scenario.notes[0],source_id:ticker+'-ASSUMPTION',reason:scenario.notes[0],verified:verdict!=='FLAG'}]},
    balthasar:specialist('balthasar',1),casper:specialist('casper',2),
    decision:{ticker,decision:scenario.decision,cap:scenario.cap/100,decided_by:'chair',reason:scenario.reason,source_ids:[],weighted_score:null}};
  vi.stubGlobal('fetch',vi.fn(async (path:string) => {
    const payload=path.endsWith('/refresh') ? {job_id:'demo-job'} : path.includes('/jobs/') ? {status:'done',progress:['[melchior:done] Simulated ethics review'],result:null,error:null} : path.endsWith('/investment-quote') ? {
      ticker,policy_revision:0,available_usd:100000,maximum_usd:scenario.cap*1000,suggested_usd:approved?1000:0,price:100,buy_allowed:approved,confidence_score:null,confidence_definition:'Demo assumptions',reason:scenario.reason,blocked_reason:approved?null:'Scenario does not permit an allocation.'
    } : report;
    return new Response(JSON.stringify(payload),{status:200});
  }));
  render(<Research charity={cid} name="BTS" externalBusy={false} onBusy={()=>{}} onComplete={()=>{}} openSource={()=>{}} onPurchased={()=>{}} />);
  fireEvent.change(screen.getByLabelText('Which stock would you like to research?'),{target:{value:ticker}});
  fireEvent.click(screen.getByRole('button',{name:'Research stock →'}));
  expect(await screen.findByText(scenario.label+' · simulated')).toBeTruthy();
  expect(screen.getByLabelText('Melchior research card')).toBeTruthy();
  expect(screen.getByLabelText('Balthasar research card')).toBeTruthy();
  expect(screen.getByLabelText('Casper research card')).toBeTruthy();
  expect(screen.getByRole('heading',{name:'How much should we invest?'})).toBeTruthy();
  expect(screen.getByLabelText('Research devil’s advocate')).toBeTruthy();
  expect(await screen.findByText(approved?'Demo assumptions':'Scenario does not permit an allocation.')).toBeTruthy();
  expect(screen.queryByText('Try a complete committee review')).toBeNull();
});
