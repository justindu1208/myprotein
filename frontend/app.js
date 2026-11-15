"use strict";
const $=id=>document.getElementById(id);
const escapeHtml=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let current=null,version=0,poll=null,taskList=[];
const exampleId='example-il2-preview';
const terminal=new Set(['stopped','complete','failed','submission_uncertain','render_failed','ready','draft','resolution_failed']);
async function request(url,body){const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;}
function toast(message){$('toast').textContent=message;$('toast').classList.add('show');setTimeout(()=>$('toast').classList.remove('show'),5000);}
function navigate(page){
 if(!['design','tasks','ranking','experiment','visualization'].includes(page))page='design';
 if(['ranking','experiment','visualization'].includes(page)&&!current){page='tasks';toast('Choose a task first.');}
 document.querySelector('.task-subnav').hidden=!(current&&['ranking','experiment','visualization'].includes(page));
 document.querySelectorAll('[data-page]').forEach(node=>node.hidden=node.dataset.page!==page);
 document.querySelectorAll('[data-page-link]').forEach(node=>{const active=node.dataset.pageLink===page;node.classList.toggle('is-active',active);if(active)node.setAttribute('aria-current','page');else node.removeAttribute('aria-current');});
 if(location.hash!=='#'+page)history.replaceState(null,'','#'+page);
 if(page==='tasks')refreshTasks();
 window.scrollTo({top:0,behavior:'smooth'});
}
document.querySelectorAll('[data-page-link]').forEach(a=>a.addEventListener('click',e=>{e.preventDefault();navigate(a.dataset.pageLink);}));
document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.go)));
window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));
function updateSlider(slider){const percent=(Number(slider.value)-Number(slider.min))/(Number(slider.max)-Number(slider.min))*100;slider.style.setProperty('--fill',percent+'%');slider.parentElement.querySelector('output').textContent=slider.value+'%';}
document.querySelectorAll('[data-priority]').forEach(slider=>{updateSlider(slider);slider.addEventListener('input',()=>updateSlider(slider));});
function clearCurrent(){version++;clearTimeout(poll);current=null;document.querySelector('.task-subnav').hidden=true;molecularEvidence.clear();$('results').hidden=true;$('experiment-shortlist').textContent='No candidates loaded yet.';$('export-json').disabled=true;clearTimeout(experimentTimer);experimentEpoch++;experimentResearchId=null;experimentData=null;experimentSelected=null;const v=$('experiment-video');v.pause();v.removeAttribute('src');v.hidden=true;$('experiment-placeholder').hidden=false;}
async function refreshTasks(){
 try{taskList=await request('/api/research/tasks');renderTasks();}catch(e){$('task-list').textContent='Unable to load local tasks: '+e.message;}
}
function renderTasks(){
 $('task-list').innerHTML=taskList.length?taskList.map(t=>`<button class="task-card" data-task="${escapeHtml(t.id)}"><span class="task-card-icon">✳</span><span class="task-card-info"><strong>${escapeHtml(t.task_name)}</strong><small>${escapeHtml(t.spec.symbol)} · ${escapeHtml(t.spec.accession)} · ${escapeHtml(t.spec.species)}</small></span><span class="task-card-meta"><b>${t.isExample?'EXAMPLE · NOT A NEW RUN':escapeHtml(t.stage)}</b><small>${escapeHtml(t.spec.count)} candidates</small></span><span class="task-arrow">↗</span></button>`).join(''):'<p class="task-empty">No tasks yet. Start one from New task.</p>';
 document.querySelectorAll('[data-task]').forEach(button=>button.onclick=()=>openTask(button.dataset.task));
}
async function openTask(id){
 clearCurrent();const token=version;
 try{let r;if(id===exampleId){const demos=await request('/api/research/demos');if(!demos.il2)throw Error('The bundled example is not available on this computer.');r={...demos.il2,task_name:'Example task · IL-2',isExample:true};}else r=await request('/api/research/'+id);if(token!==version)return;show(r);navigate('ranking');if(!r.isExample&&!terminal.has(r.stage))schedule(id,token);}catch(e){toast('Could not open task: '+e.message);navigate('tasks');}
}
function schedule(id,token){clearTimeout(poll);poll=setTimeout(async()=>{try{const r=await request('/api/research/'+id);if(token!==version||current?.id!==id)return;show(r);if(!terminal.has(r.stage))schedule(id,token);}catch(e){if(token===version){$('runtime').textContent='Status temporarily unavailable: '+e.message;schedule(id,token);}}},5000);}
function show(r){
 current=r;setExperimentResearch(r);molecularEvidence.setResearch(r);$('evidence-source-name').textContent='Design prediction';$('evidence-original').hidden=true;$('export-json').disabled=false;document.querySelector('.task-subnav').hidden=false;document.querySelectorAll('.example-notice').forEach(n=>n.hidden=!r.isExample);
 document.querySelectorAll('.current-task-name').forEach(n=>n.textContent=r.task_name||r.spec.symbol);
 document.querySelectorAll('.current-task-target').forEach(n=>n.textContent=r.spec.symbol+' · '+r.spec.accession+' · '+r.stage);
 $('runtime').textContent=[r.stage,r.provider_state,r.rendering_candidate,r.error,r.remote_warning].filter(Boolean).join(' · ');$('task-status-label').textContent=r.isExample?'EXAMPLE · Previously computed IL-2 data':([r.stage,r.provider_state,r.error].filter(Boolean).join(' · '));
 $('activity-log').replaceChildren(...[...(r.events||[]),r.jobName?'Tamarind job: '+r.jobName:'',r.selection_basis||'',r.error||''].filter(Boolean).map(text=>{const p=document.createElement('p');p.textContent=text;return p;}));
 const completed=r.stage==='complete'?6:['rendering','render_failed'].includes(r.stage)?5:r.stage==='screening'?3:['computing','preparing','submitting','ready','draft'].includes(r.stage)?1:0;
 document.querySelectorAll('.pipe-step').forEach((node,i)=>{const running=r.stage==='computing'?[1,2].includes(i):r.stage==='screening'?[3,4].includes(i):r.stage==='rendering'?i===5:['preparing','submitting'].includes(r.stage)&&i===1;node.querySelector('em').textContent=i<completed?'Done':running?'Active':'Waiting';node.classList.toggle('done',i<completed);node.classList.toggle('active',running);});
 document.querySelector('.activity-count').textContent=(r.rendered||[]).length+' media groups ready';
 $('run-screen').hidden=!['ready','draft','render_failed','resolution_failed'].includes(r.stage);$('run-screen').disabled=!['ready','draft','render_failed','resolution_failed'].includes(r.stage);$('run-screen').textContent=['ready','draft'].includes(r.stage)?'Start this real task':r.stage==='resolution_failed'?'Retry target lookup':'Retry local animation rendering';$('retry-task').hidden=!['ready','draft','render_failed','resolution_failed'].includes(r.stage)||!!r.isExample;
 $('results').hidden=!r.candidates?.length;if(r.candidates?.length)renderResults();
 $('ranking-empty').hidden=!!r.candidates?.length;
 if(!r.candidates?.length){
  const heading=$('ranking-empty').querySelector('h3'),message=$('ranking-empty').querySelector('p');
  if(['failed','submission_uncertain','resolution_failed','stopped'].includes(r.stage)){
   heading.textContent=r.stage==='resolution_failed'?'Target lookup failed':r.stage==='submission_uncertain'?'Submission status needs review':'Task did not complete';
   message.textContent=r.error||'Check the task status before starting another run.';
  }else if(['draft','ready'].includes(r.stage)){
   heading.textContent='Task saved';message.textContent='Start the real task to begin target lookup and candidate generation.';
  }else{
   const elapsed=r.created_at?Math.max(0,Math.floor((Date.now()-Date.parse(r.created_at))/60000)):null;
   heading.textContent=r.provider_state==='In Queue'?'Waiting for Tamarind':'Working on this task';
   message.textContent=(r.provider_state?`Tamarind: ${r.provider_state}. `:'Preparing the target and model settings. ')+(elapsed===null?'':`Elapsed: ${elapsed} min. `)+'Candidates appear when the model returns results; no percentage estimate is available.';
  }
 }

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
 $('candidate-body').innerHTML=ordered.map((c,i)=>({c,rank:i+1})).filter(({c})=>c.id.toLowerCase().includes(query)).map(({c,rank})=>{const top=ids.includes(c.id);const b=c.metrics.binding_confidence,st=c.metrics.structure_confidence;let note=c.passed?`Model gates met: binding ${fmt(b)} ≥ 0.700 and structure ${fmt(st)} ≥ 0.680.`:c.reasons?.length?`Did not pass: ${c.reasons.join(', ').replaceAll('_',' ')}.`:'Insufficient model evidence.';note+=' This is a score-based explanation, not proof of biological function.';return `<tr class="${top?'top-candidate':''}"><td>${rank}${top?' <span class="top-tag">TOP 3</span>':''}</td><td>${escapeHtml(c.id)}</td><td>${fmt(b)}</td><td>${fmt(st)}</td><td>${fmt(c.metrics.iptm)}</td><td>${c.passed?'PASS':'NOT PASSED'}</td><td>${escapeHtml(note)}</td><td>${top?`<button data-candidate="${escapeHtml(c.id)}">View ↗</button>`:''}</td></tr>`;}).join('');
 document.querySelectorAll('[data-candidate]').forEach(node=>{node.onclick=()=>{navigate('visualization');molecularEvidence.focusCandidate(node.dataset.candidate);};node.onkeydown=e=>{if(e.key==='Enter')node.click();};});
}

document.addEventListener('protolab:evidence-selection',event=>{
 const d=event.detail,c=current?.candidates?.find(row=>row.id===d.candidate);const box=$('candidate-evidence');
 if(!c){box.hidden=true;return;}
 box.hidden=false;$('trail-candidate').textContent=c.id;
 $('trail-verdict').textContent=c.passed?'Passed configured model-score gates; biological activity is not verified.':'Did not pass all configured gates; shown for diagnosis, not as a successful binder.';
 $('trail-binding').textContent=fmt(c.metrics?.binding_confidence);$('trail-structure').textContent=fmt(c.metrics?.structure_confidence);$('trail-iptm').textContent=fmt(c.metrics?.iptm);
 $('trail-basis').textContent='Why this outcome: '+(c.passed?'binding confidence ≥ 0.70 and structure confidence ≥ 0.68.':(c.reasons||[]).join(', ').replaceAll('_',' ')||'insufficient returned evidence')+'. This explanation is generated from the recorded scores and rules, not a model-generated mechanism.';
 $('trail-source').textContent='Design source: '+(current.jobName||'not available')+' · Target: '+current.spec.symbol+' / '+current.spec.accession+' · Current structure: '+(d.asset?.source||'not available')+' · Structure job: '+(d.asset?.source_job_id||'not available')+' · SHA256: '+(d.asset?.sha256||'not available');
 const f=d.interface;$('trail-contacts').textContent=f?('Predicted structure contacts: '+f.method+' · '+f.residues.length+' listed residues; proximity does not establish a hydrogen bond or cause.'):'Interface evidence not available.';
 const ex=experimentData?.jobs?.find(j=>j.candidate_id===c.id);$('trail-experiment').textContent=ex?.state==='complete'?'Independent Boltz-2 prediction: ipTM '+fmt(ex.metrics?.iptm)+', confidence '+fmt(ex.metrics?.confidence_score)+' · job '+ex.jobName+'.':'Independent follow-up prediction: '+(ex?.state||'not run')+'.';
});
let experimentResearchId=null,experimentData=null,experimentSelected=null,experimentTimer=null,experimentEpoch=0;
function experimentIds(r){return [...(r?.selected||[]),...(r?.diagnostic||[])].slice(0,3);}
function setExperimentResearch(r){
 if(experimentResearchId===r.id){renderExperiment(r);return;}
 experimentResearchId=r.id;experimentData=null;experimentSelected=experimentIds(r)[0]||null;clearTimeout(experimentTimer);const token=++experimentEpoch;
 $('experiment-video').pause();$('experiment-video').removeAttribute('src');$('experiment-video').hidden=true;$('experiment-placeholder').hidden=false;
 renderExperiment(r);loadExperiment(r.id,token);
}
async function loadExperiment(id,token){
 try{const d=await request('/api/experiments/'+id);if(token!==experimentEpoch||current?.id!==id)return;experimentData=d;renderExperiment(current);if(d.state==='running')experimentTimer=setTimeout(()=>loadExperiment(id,token),5000);}
 catch(e){if(token===experimentEpoch){$('experiment-progress').textContent='Could not load prediction status: '+e.message;experimentTimer=setTimeout(()=>loadExperiment(id,token),10000);}}
}
function renderExperiment(r){
 const ids=experimentIds(r),jobs=experimentData?.jobs||[];
 if(!ids.includes(experimentSelected))experimentSelected=ids[0]||null;
 $('experiment-selector').innerHTML=ids.map((id,i)=>`<button type="button" data-experiment-candidate="${escapeHtml(id)}" aria-pressed="${id===experimentSelected}"><small>0${i+1}</small>${escapeHtml(id)}</button>`).join('');
 document.querySelectorAll('[data-experiment-candidate]').forEach(b=>b.onclick=()=>{experimentSelected=b.dataset.experimentCandidate;renderExperiment(current);});
 $('experiment-shortlist').innerHTML=ids.length?ids.map(id=>{const j=jobs.find(x=>x.candidate_id===id),m=j?.metrics||{},status=j?.state||'not started',design=r.candidates?.find(c=>c.id===id);let explanation;
 if(status==='complete')explanation=`Complex prediction complete. ipTM ${fmt(m.iptm)}; overall confidence ${fmt(m.confidence_score)}. These describe model confidence, not confirmed binding or mechanism.`;
 else if(status==='failed'||status==='submission_uncertain')explanation=j.reason||'Prediction did not complete; inspect status before retrying.';
 else explanation=({pending:'Waiting to submit.',submitting:'Submitting to Tamarind.',queued:'Queued at Tamarind.',running:'Predicting the target–binder complex.',processing:'Checking returned structure and scores.',rendering:'Rendering the predicted structure.'})[status]||'Not run yet.';
 return `<button class="experiment-result ${id===experimentSelected?'is-selected':''}" data-experiment-result="${escapeHtml(id)}"><span><strong>${escapeHtml(id)}</strong><em>${escapeHtml(status.replaceAll('_',' '))}</em></span><small>${design?.passed?'Design gate passed':'Diagnostic candidate · design gate not passed'}</small><p>${escapeHtml(explanation)}</p></button>`;}).join(''):'No candidates yet — waiting for this task.';
 document.querySelectorAll('[data-experiment-result]').forEach(b=>b.onclick=()=>{experimentSelected=b.dataset.experimentResult;renderExperiment(current);});
 const job=jobs.find(j=>j.candidate_id===experimentSelected),movie=job?.state==='complete'?job.artifacts?.['complex.mp4']:null,v=$('experiment-video');
 $('open-simulation-view').hidden=!movie;
 if(movie){$('experiment-placeholder').hidden=true;v.hidden=false;if(v.getAttribute('src')!==movie){v.pause();v.loop=false;v.src=movie;v.onloadedmetadata=()=>{if(v.duration>=16)v.currentTime=10;v.play().catch(()=>{});};v.onended=()=>{v.currentTime=v.duration>=16?10:0;v.play().catch(()=>{});};v.play().catch(()=>{});}}
 else{v.pause();v.removeAttribute('src');v.hidden=true;$('experiment-placeholder').hidden=false;$('experiment-placeholder').innerHTML=`<span>◎ + ✳</span><p>${job?.state==='rendering'?'Preparing the predicted complex animation…':'Select a candidate to inspect its predicted complex when ready.'}</p>`;}
 const retryable=experimentData?.state==='finished_with_errors'&&jobs.some(j=>j.state==='submission_uncertain'&&(j.reason||'').startsWith('Tamarind HTTP 400'));
 const btn=$('start-experiment');btn.disabled=ids.length!==3||!!experimentData&&experimentData.state!=='not_started'&&!retryable;btn.dataset.retry=retryable?'true':'false';
 btn.textContent=experimentData?.state==='running'?'Predictions in progress':experimentData?.state==='complete'?'Predictions completed':experimentData?.state==='finished_with_errors'?(retryable?'Retry rejected predictions ↗':'Predictions finished with errors'):'Run 3 predictions ↗';
 $('experiment-progress').textContent=experimentData?.state==='running'?`${jobs.filter(j=>j.state==='complete').length} / 3 complete · ${jobs.map(j=>j.state).join(' / ')}`:ids.length!==3?'A shortlist of three is required':experimentData?.state==='finished_with_errors'?'Review each candidate status':experimentData?.state==='complete'?'3 / 3 predictions complete':'Ready for a separate Boltz-2 run';
}
$('open-selected-visualization').onclick=()=>{
 if(!current)return;
 const selected=experimentSelected;
 // The standard transition always shows the selected design's original protein.
 // The separate simulation button explicitly opens the follow-up complex.
 molecularEvidence.clear();molecularEvidence.setResearch(current);
 $('evidence-source-name').textContent='Design prediction';$('evidence-original').hidden=true;
 if(selected)molecularEvidence.focusCandidate(selected);
 navigate('visualization');
};
$('open-simulation-view').onclick=()=>{const job=experimentData?.jobs?.find(j=>j.candidate_id===experimentSelected);if(!current||job?.state!=='complete')return;molecularEvidence.clear();const passed=current.candidates.find(c=>c.id===job.candidate_id)?.passed;molecularEvidence.setResearch({...current,visualization_run:job.visualization_run,selected:passed?[job.candidate_id]:[],diagnostic:passed?[]:[job.candidate_id],rendered:[job.candidate_id]});$('evidence-source-name').textContent='Independent Boltz-2 simulation · '+job.candidate_id;$('evidence-original').hidden=false;navigate('visualization');};
$('evidence-original').onclick=()=>{if(!current)return;molecularEvidence.clear();molecularEvidence.setResearch(current);$('evidence-source-name').textContent='Design prediction';$('evidence-original').hidden=true;};
$('start-experiment').onclick=async()=>{if(!current)return;const id=current.id,token=experimentEpoch;$('start-experiment').disabled=true;try{experimentData=await request($('start-experiment').dataset.retry==='true'?'/api/experiments/retry':'/api/experiments/start',{id});if(token!==experimentEpoch||current?.id!==id)return;renderExperiment(current);loadExperiment(id,token);}catch(e){toast('Could not start predictions: '+e.message);if(token===experimentEpoch)renderExperiment(current);}};
$('build-brief').onclick=async()=>{
 const button=$('build-brief'),name=$('task-name').value.trim(),target=$('target').value.trim(),count=Number($('candidate-count').value);
 if(!name||!target){toast('Enter a task name and target first.');return;}
 if(!Number.isInteger(count)||count<10||count>100){toast('Candidate count must be 10–100.');return;}
 $('task-error').hidden=true;clearCurrent();button.disabled=true;button.textContent='Creating task…';const token=version;
 try{
  const priorities=Object.fromEntries([...document.querySelectorAll('[data-priority]')].map(x=>[x.dataset.priority,Number(x.value)]));
  const r=await request('/api/research/create',{target,species:$('species').value,modality:'Protein binder',intent:'Design a miniprotein binder for structural binding assessment.',task_name:name,count,priorities,new_task:true});
  if(token!==version)return;current=r;show(r);navigate('ranking');
  const started=await request('/api/research/start',{id:r.id});if(token!==version)return;show(started);if(!terminal.has(started.stage))schedule(r.id,token);refreshTasks();
 }catch(e){$('task-error').textContent='Could not start task: '+e.message;$('task-error').hidden=false;toast('Could not start task: '+e.message);if(current){show(current);refreshTasks();}}finally{button.disabled=false;button.innerHTML='Start real task <span>↗</span>';}
};
$('retry-task').onclick=()=>$('run-screen').click();
$('run-screen').onclick=async()=>{if(!current)return;const id=current.id,token=version;try{const r=await request('/api/research/start',{id});if(token!==version)return;show(r);schedule(id,token);}catch(e){toast(e.message);}};
$('candidate-search').oninput=renderResults;
function download(name,text,type){const a=document.createElement('a');const url=URL.createObjectURL(new Blob([text],{type}));a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$('export-json').onclick=()=>{if(current)download((current.task_name||current.spec.symbol)+'-research.json',JSON.stringify(current,null,2),'application/json');};
$('export-csv').onclick=()=>{if(!current)return;const lines=[['id','binding_confidence','structure_confidence','iptm','passed','reasons'],...current.candidates.map(c=>[c.id,c.metrics.binding_confidence,c.metrics.structure_confidence,c.metrics.iptm,c.passed,c.reasons.join('; ')])];download(current.spec.symbol+'-candidates.csv',lines.map(row=>row.map(v=>'"'+String(v??'').replace(/"/g,'""')+'"').join(',' )).join('\n'),'text/csv');};
$('compare-top').onclick=()=>{const id=(current?.selected?.length?current.selected:current?.diagnostic)?.[0];if(id){navigate('visualization');molecularEvidence.focusCandidate(id);}};
navigate(location.hash.slice(1));refreshTasks();
