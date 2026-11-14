"use strict";
function deduplicateWinners(winners) {
  const grouped = new Map();
  for (const winner of winners) {
    if (!grouped.has(winner.id)) grouped.set(winner.id, {id:winner.id,categories:[]});
    const categories=grouped.get(winner.id).categories;
    if(!categories.includes(winner.category))categories.push(winner.category);
  }
  return [...grouped.values()];
}

class SamsonViewer {
  constructor(frame, onUnavailable, onState) {
    this.frame=frame;this.onUnavailable=onUnavailable;this.onState=onState;this.timer=null;this.url=null;
  }
  clear() {
    clearTimeout(this.timer);this.frame.onload=null;this.frame.onerror=null;
    this.frame.hidden=true;this.frame.removeAttribute('src');this.url=null;
  }
  load(documentURL) {
    this.clear();
    if(!documentURL)return false;
    const url=new URL(documentURL);
    const match=url.pathname.match(/^\/documents\/([a-f0-9]{8}-[a-f0-9-]{27})\/?$/i);
    if(url.origin!=='https://www.samson-connect.net'||!match)throw Error('Invalid SAMSON document URL');
    this.url='https://app.samson-connect.net/?sam='+encodeURIComponent(match[1])+'&statcounter=0';
    this.frame.hidden=false;
    this.frame.onload=()=>{clearTimeout(this.timer);this.onState('SAMSON frame loaded. If access is blocked, use “Show fallback”.');};
    this.frame.onerror=()=>this.onUnavailable('SAMSON viewer unavailable or blocked.');
    this.timer=setTimeout(()=>this.onUnavailable('SAMSON did not finish loading. Check access or use fallback media.'),20000);
    this.frame.src=this.url;this.onState('Loading published SAMSON document…');return true;
  }
  reset() {if(this.url)this.frame.src=this.url;}
}

const molecularEvidence=(()=>{
  const el=id=>document.getElementById(id);
  let manifest=null,record=null,selected='target',role='target',epoch=0,renderStatus=null,poll=null,blocked=false,loadedKey='';
  const samson=new SamsonViewer(el('samson-viewer'),()=>{blocked=true;samson.clear();fallback();},message=>el('evidence-status').textContent=message);
  const request=async(url,body)=>{const r=await fetch(url,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const d=await r.json();if(!r.ok)throw Error(d.error||'Request failed');return d;};
  function asset(){return role==='target'?manifest?.target:manifest?.candidates?.[selected]?.[role];}
  function cid(){return role==='target'?'target':selected;}
  function link(id,url){const a=el(id);a.hidden=!url;if(url)a.href=url;else a.removeAttribute('href');}
  function clearMedia(){samson.clear();const v=el('evidence-video');v.pause();v.removeAttribute('src');v.removeAttribute('poster');v.hidden=true;el('evidence-image').hidden=true;el('evidence-empty').hidden=false;el('evidence-animation-label').hidden=true;el('evidence-blocked').hidden=true;el('evidence-retry').hidden=true;}
  function fallback(){
    const files=renderStatus?.state==='ready'?renderStatus.artifacts:{};const movie=files?.[role+'.mp4'],image=files?.[role+'.png'];
    if(movie){const v=el('evidence-video');v.src=movie;if(image)v.poster=image;v.hidden=false;v.play().catch(()=>{});el('evidence-empty').hidden=true;el('evidence-animation-label').hidden=role!=='complex';}
    else if(image){el('evidence-image').src=image;el('evidence-image').hidden=false;el('evidence-empty').hidden=true;}
    else el('evidence-empty').textContent=asset()?'Real structure available. Animation is being prepared or has not yet been rendered.':'Waiting for this target’s real structures. No historical result is substituted.';
    el('evidence-retry').hidden=!blocked;
  }
  function choices(){return record?[...(record.selected||[]),...(record.diagnostic||[])]:[];}
  function tabs(){
    const ids=['target',...choices()];if(selected!=='target'&&!ids.includes(selected))ids.push(selected);
    el('evidence-candidates').replaceChildren(...ids.map(id=>{const b=document.createElement('button');b.textContent=id==='target'?'Target':id;b.type='button';b.setAttribute('aria-pressed',id===selected);b.onclick=()=>{selected=id;role=id==='target'?'target':'monomer';update();};return b;}));
    ['target','monomer','complex'].forEach(r=>{el('evidence-'+r).setAttribute('aria-pressed',r===role);el('evidence-'+r).disabled=r!=='target'&&selected==='target';});
  }
  async function status(token){
    if(!asset())return;
    try{const d=await request(`/api/visualizations/${manifest.run_id}/${cid()}/status?preset=${el('evidence-representation').value}`);if(token!==epoch)return;renderStatus=d;
      link('evidence-script',d.artifacts?.['render.cxc']);el('evidence-render').disabled=['queued','running'].includes(d.state);
      el('evidence-status').textContent=`ChimeraX: ${d.state}${d.reason?' · '+d.reason:''}`;
      if(el('samson-viewer').hidden)fallback();
      if(['queued','running'].includes(d.state)||(d.state==='not_rendered'&&record?.stage==='rendering'))poll=setTimeout(()=>status(token),3000);
    }catch(e){if(token===epoch)el('evidence-status').textContent=e.message;}
  }
  function update(){
    const token=++epoch;clearTimeout(poll);renderStatus=null;blocked=false;clearMedia();tabs();
    const a=asset();link('evidence-download-cif',a?.mmcif_url);link('evidence-download-pdb',a?.pdb_url);link('evidence-script',null);link('evidence-open-samson',null);el('evidence-render').disabled=!a;
    el('evidence-badge').textContent=a?'Predicted structure':'Awaiting current target';
    el('evidence-provenance').textContent=a?[record?.spec.symbol,record?.spec.accession,`${record?.spec.start}–${record?.spec.end}`,selected,a.source,a.source_job_id,a.note,'Not experimental evidence',`SHA256: ${a.sha256}`].filter(Boolean).join(' · '):'';
    const face=role==='complex'?manifest?.candidates?.[selected]?.interface:null;
    el('evidence-interface').textContent=face?`${face.method}. Residues: ${face.residues.map(r=>r.chain+':'+r.name+r.number).join(', ')}.`:'No interface contacts for this view.';
    const doc=a?.samson_views?.[el('evidence-representation').value]||(el('evidence-representation').value==='cartoon'?a?.samson_document_url:null);
    if(doc){link('evidence-open-samson',doc);samson.load(doc);el('evidence-empty').hidden=true;el('evidence-blocked').hidden=false;}else fallback();
    if(a)status(token);else el('evidence-status').textContent=record?`Current task: ${record.stage}`:'Build a design brief to resolve a target.';
  }
  function clear(){record=manifest=null;loadedKey='';selected=role='target';update();el('evidence-scope').textContent='Only results belonging to the current target are displayed.';}
  async function setResearch(next){
    if(record&&record.id!==next.id)clear();record=next;
    el('evidence-scope').textContent=`${next.spec.symbol} · ${next.spec.accession} · ${next.spec.species} · ${next.spec.domain} ${next.spec.start}–${next.spec.end}. ${next.selected?.length?`${next.selected.length} passed model gates; ${next.diagnostic?.length||0} additional ranked predictions are diagnostic only.`:next.diagnostic?.length?'No candidate passed; displayed structures are diagnostic predictions, not recommended binders.':'Real target-specific computation.'}`;
    if(!next.visualization_run){el('evidence-status').textContent=`Current task: ${next.stage}${next.provider_state?' · '+next.provider_state:''}`;return;}
    const key=next.id+':'+next.visualization_run+':'+choices().join(',')+':'+(next.rendered||[]).join(',');
    if(key===loadedKey)return;
    const identity=next.id,token=++epoch;
    try{const m=await request(`/api/visualizations/${next.visualization_run}/manifest`);
      if(token!==epoch||record?.id!==identity)return;
      if(m.research_id!==next.id||m.target_spec?.sequence_sha256!==next.spec.sequence_sha256)throw Error('Target identity mismatch: refusing unrelated structures');
      const firstLoad=!manifest;manifest=m;loadedKey=key;if(firstLoad&&choices().length){selected=choices()[0];role='monomer';}update();
    }catch(e){if(token===epoch)el('evidence-status').textContent=e.message;}
  }
  ['target','monomer','complex'].forEach(r=>el('evidence-'+r).onclick=()=>{role=r;update();});
  el('evidence-representation').onchange=update;
  el('evidence-reset').onclick=()=>{samson.reset();el('evidence-video').currentTime=0;};
  el('evidence-fullscreen').onclick=async()=>{if(document.fullscreenElement)await document.exitFullscreen();else await el('molecular-evidence').requestFullscreen();};
  el('evidence-blocked').onclick=()=>{blocked=true;samson.clear();fallback();};el('evidence-retry').onclick=update;
  el('evidence-render').onclick=async()=>{if(!asset())return;el('evidence-render').disabled=true;try{await request(`/api/visualizations/${manifest.run_id}/${cid()}/render`,{preset:el('evidence-representation').value});await status(epoch);}catch(e){el('evidence-status').textContent=e.message;el('evidence-render').disabled=false;}};
  clear();
  return {clear,setResearch,focusCandidate(id){if(!manifest?.candidates?.[id])return;selected=id;role='monomer';update();el('molecular-evidence').scrollIntoView({behavior:'smooth'});}};
})();
