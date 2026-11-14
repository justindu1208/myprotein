"use strict";
const $=id=>document.getElementById(id);
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let current=null,version=0,poll=null;
const terminal=new Set(['stopped','complete','failed','submission_uncertain','render_failed','ready']);
async function request(url,body){const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}
function toast(message){$('toast').textContent=message;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),5000);}
function invalidate(){$('build-brief').disabled=false;$('parsed-brief').querySelector('.confidence').textContent='Draft';$('run-screen').textContent='Run real Tamarind screen (10 candidates)';document.querySelector('.activity-count').textContent='No current task';document.querySelectorAll('.pipe-step').forEach(n=>{n.querySelector('em').textContent='Waiting';n.classList.remove('done','active');});version++;clearTimeout(poll);current=null;molecularEvidence.clear();$('results').hidden=true;$('brief-content').hidden=true;$('brief-empty').hidden=false;$('run-screen').disabled=true;$('export-json').disabled=true;$('runtime').textContent='Inputs changed — build the brief';$('activity-log').textContent='No task is attached to these inputs yet.';}
async function buildBrief(){
  invalidate();const token=version;$('build-brief').disabled=true;$('runtime').textContent='Resolving target from UniProt…';
  try{const r=await request('/api/research/resolve',{target:$('target').value,species:$('species').value,modality:$('modality').value,intent:$('intent').value});if(token!==version)return;
    attachBrief(r,token);
  }catch(e){if(token===version){$('runtime').textContent=e.message;toast(e.message);}}finally{if(token===version)$('build-brief').disabled=false;}
}
function attachBrief(r,token){
    current=r;const s=r.spec;$('brief-symbol').textContent=s.symbol;$('brief-name').textContent=s.name;$('brief-id').textContent=`${s.accession} · ${s.species}`;$('brief-domain').textContent=`${s.domain} · ${s.start}–${s.end} · ${s.length} aa`;$('brief-action').textContent=s.intent;$('brief-modality').textContent=`Miniprotein · ${s.count} candidates · ${s.binder_length} aa`;
    $('brief-content').hidden=false;$('brief-empty').hidden=true;$('parsed-brief').querySelector('.confidence').textContent='Verified target';show(r);if(!terminal.has(r.stage))schedule(r.id,token);
}
function schedule(id,token){clearTimeout(poll);poll=setTimeout(async()=>{try{const r=await request('/api/research/'+id);if(token!==version||current?.id!==id)return;show(r);if(!terminal.has(r.stage))schedule(id,token);}catch(e){if(token===version){$('runtime').textContent='Status temporarily unavailable: '+e.message;schedule(id,token);}}},5000);}
function show(r){
 current=r;molecularEvidence.setResearch(r);$('export-json').disabled=false;
 $('run-screen').disabled=!['ready','render_failed'].includes(r.stage);$('run-screen').textContent=r.stage==='ready'?'Run real Tamarind screen (10 candidates)':r.stage==='render_failed'?'Retry local animation rendering':'Real task submitted';
 $('runtime').textContent=[r.stage,r.provider_state,r.rendering_candidate,r.error,r.remote_warning].filter(Boolean).join(' · ');
 $('activity-log').replaceChildren(...[...r.events, r.jobName?'Tamarind job: '+r.jobName:'',r.selection_basis||'',r.error||''].filter(Boolean).map(text=>{const p=document.createElement('p');p.textContent=text;return p;}));
 const completed=r.stage==='complete'?6:['rendering','render_failed'].includes(r.stage)?5:r.stage==='screening'?3:['computing','preparing','submitting','ready'].includes(r.stage)?1:0;
 document.querySelectorAll('.pipe-step').forEach((node,i)=>{const running=r.stage==='computing'?[1,2].includes(i):r.stage==='screening'?[3,4].includes(i):r.stage==='rendering'?i===5:['preparing','submitting'].includes(r.stage)&&i===1;node.querySelector('em').textContent=i<completed?'Done':running?'Active':'Waiting';node.classList.toggle('done',i<completed);node.classList.toggle('active',running);});
 document.querySelector('.activity-count').textContent=(r.rendered||[]).length+' media groups ready';
 if(r.candidates?.length)renderResults();
}
function fmt(n){return typeof n==='number'&&Number.isFinite(n)?n.toFixed(3):'Not available';}
function renderResults(){
 if(!current)return;const r=current,rows=r.candidates||[];$('results').hidden=!rows.length;
 $('stat-screened').textContent=rows.length;$('stat-eligible').textContent=rows.filter(c=>c.passed).length;$('stat-excluded').textContent=rows.filter(c=>!c.passed).length;$('stat-frontier').textContent=(r.selected.length+r.diagnostic.length);
 $('selection-note').textContent=r.selected.length?`${r.selected.length} passed model gates; ${r.diagnostic.length} additional ranked structures are diagnostic only. Biological effect and developability remain untested.`:'No candidate passed both confidence gates. The best available structures below are diagnostic examples from this exact target, not successful binders.';
 const ids=[...r.selected,...r.diagnostic];
 $('winner-grid').innerHTML=ids.map((id,i)=>{const c=rows.find(c=>c.id===id);return `<article class="winner-card" tabindex="0" role="button" data-candidate="${escapeHtml(id)}"><header>${c.passed?'Selected · passed gates':'Diagnostic only · not passed'} ${i+1}</header><h3>${escapeHtml(id)}</h3><p>Binding confidence ${fmt(c.metrics.binding_confidence)}</p><p>Structure confidence ${fmt(c.metrics.structure_confidence)}</p><p>Inspect real protein and complex ↗</p></article>`;}).join('');
 const query=$('candidate-search').value.toLowerCase();
 const ordered=[...rows].sort((a,b)=>Number(b.qc_pass)-Number(a.qc_pass)||(b.metrics.binding_confidence??-1)-(a.metrics.binding_confidence??-1)||(b.metrics.structure_confidence??-1)-(a.metrics.structure_confidence??-1));
 $('candidate-body').innerHTML=ordered.filter(c=>c.id.toLowerCase().includes(query)).map((c,i)=>`<tr><td>${i+1}</td><td>${escapeHtml(c.id)}</td><td>${fmt(c.metrics.binding_confidence)}</td><td>${fmt(c.metrics.structure_confidence)}</td><td>${fmt(c.metrics.iptm)}</td><td>${c.passed?'PASS':'NOT PASSED'}</td><td>${escapeHtml(c.reasons.join(', '))}</td><td><button data-candidate="${escapeHtml(c.id)}">Inspect</button></td></tr>`).join('');
 document.querySelectorAll('[data-candidate]').forEach(node=>{node.onclick=()=>molecularEvidence.focusCandidate(node.dataset.candidate);node.onkeydown=e=>{if(e.key==='Enter')node.click();};});
}
const briefPresets={
 il2:{target:'P60568',intent:'Design a miniprotein binder to mature IL-2 for structural binding assessment. Biological effects remain to be tested.'},
 pdl1:{target:'Q9NZQ7',intent:'Design a miniprotein binder to the extracellular domain for structural binding assessment. Functional blockade remains to be tested.'},
 pd1:{target:'Q15116',intent:'Design a miniprotein binder to the extracellular domain for structural binding assessment. Functional blockade remains to be tested.'}
};
let demoRecords={};
const demoLabels={il2:'1 · IL-2 · P60568',pdl1:'2 · PD-L1 · Q9NZQ7',pd1:'3 · PD-1 · Q15116'};
async function refreshDemos(){
 try{demoRecords=await request('/api/research/demos');document.querySelectorAll('[data-brief]').forEach(button=>{const r=demoRecords[button.dataset.brief];const state=!r?'Not computed':r.stage==='complete'?'Ready to view':r.stage==='rendering'?`Rendering ${(r.rendered||[]).filter(id=>id!=='target').length}/3`:r.provider_state||r.stage;button.textContent=demoLabels[button.dataset.brief]+' · '+state;});}catch(e){/* Existing input remains usable when status is temporarily unavailable. */}
 setTimeout(refreshDemos,10000);
}
document.querySelectorAll('[data-brief]').forEach(button=>button.onclick=async()=>{
 const key=button.dataset.brief,b=briefPresets[key];$('target').value=b.target;$('species').value='Homo sapiens';$('modality').value='Protein binder';$('intent').value=b.intent;
 const cached=demoRecords[key];if(!cached){buildBrief();return;}
 invalidate();const token=version;
 try{const r=await request('/api/research/'+cached.id);if(token===version)attachBrief(r,token);}catch(e){if(token===version)toast(e.message);}
});
$('build-brief').onclick=buildBrief;
$('run-screen').onclick=async()=>{if(!current)return;const id=current.id,token=version;$('run-screen').disabled=true;try{const r=await request('/api/research/start',{id});if(token!==version)return;show(r);schedule(id,token);}catch(e){if(token===version){$('run-screen').disabled=false;toast(e.message);}}};
['target','species','modality','intent'].forEach(id=>$(id).addEventListener('input',invalidate));
document.querySelectorAll('[data-intent]').forEach(button=>button.onclick=()=>{$('intent').value=button.dataset.intent;invalidate();});
$('edit-brief').onclick=()=>{$('target').focus();$('design').scrollIntoView({behavior:'smooth'});};
$('candidate-search').oninput=renderResults;
function download(name,text,type){const a=document.createElement('a');const url=URL.createObjectURL(new Blob([text],{type}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('export-json').onclick=()=>{if(current)download(current.spec.symbol+'-research.json',JSON.stringify(current,null,2),'application/json');};
$('export-csv').onclick=()=>{if(!current)return;const lines=[['id','binding_confidence','structure_confidence','iptm','passed','reasons'],...current.candidates.map(c=>[c.id,c.metrics.binding_confidence,c.metrics.structure_confidence,c.metrics.iptm,c.passed,c.reasons.join('; ')])];download(current.spec.symbol+'-candidates.csv',lines.map(row=>row.map(v=>'"'+String(v??'').replace(/"/g,'""')+'"').join(',')).join('\n'),'text/csv');};
$('compare-top').onclick=()=>{const id=(current?.selected?.length?current.selected:current?.diagnostic)?.[0];if(id)molecularEvidence.focusCandidate(id);};
// Prefer the stored real demo on load; viewing completed results needs no external lookup.
refreshDemos().then(()=>{if(demoRecords.il2){invalidate();attachBrief(demoRecords.il2,version);}else buildBrief();});
