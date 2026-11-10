'use strict';
const $ = id => document.getElementById(id);
const pageSize = 20;
let faceResults=null, faceBusy=false, pageItems=[], indexTimer=null;
let files = [], filtered = [], page = 0, selected = new Set(), activeJob = null, viewerId = null, refUrl = null, busy = false;
const storageKey = 'findme:selected';
const jobKey = 'findme:activeExport';
function size(n) { return n >= 1024**3 ? (n/1024**3).toFixed(2)+' GB' : (n/1024**2).toFixed(1)+' MB'; }
function notice(text='') { $('notice').textContent = text; $('notice').hidden = !text; }
async function api(path, options={}) {
  const r = await fetch(path, options);
  if (r.status === 401) { notice('เซสชันหมดอายุ กรุณาเข้าสู่ระบบใหม่'); throw new Error('กรุณาเข้าสู่ระบบใหม่'); }
  let data; try { data = await r.json(); } catch { throw new Error('ไม่สามารถอ่านข้อมูลจากเซิร์ฟเวอร์'); }
  if (!r.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'ทำรายการไม่สำเร็จ');
  return data;
}
function save() { try { localStorage.setItem(storageKey, JSON.stringify([...selected])); } catch {} }
function updateCounts() {
  const chosen = files.filter(f => selected.has(f.id));
  $('selectedCount').textContent = `เลือกแล้ว ${chosen.length} รูป`;
  $('barCount').textContent = chosen.length ? `เลือกแล้ว ${chosen.length} รูป` : 'เลือกภาพเพื่อดาวน์โหลด';
  $('barSize').textContent = chosen.length ? `ต้นฉบับรวม ${size(chosen.reduce((n,f)=>n+f.size,0))} · เก็บไฟล์ 1 ชั่วโมง` : 'ไฟล์ดาวน์โหลดเก็บชั่วคราว 1 ชั่วโมง';
  $('downloadSelected').disabled = !chosen.length || busy;
  $('downloadSelected').textContent = `ดาวน์โหลดที่เลือก${chosen.length ? ` (${chosen.length})` : ''}`;
  $('downloadAll').disabled = !files.length || busy;
  $('downloadAll').textContent = faceResults?`ดาวน์โหลดผลค้นหา (${filtered.length})`:`ดาวน์โหลดทั้งคลัง (${files.length})`;
}
function toggle(id) {
  if (selected.has(id)) selected.delete(id); else selected.add(id);
  save(); render(); updateViewer();
}
function render() {
  const query = $('search').value.trim().toLocaleLowerCase();
  const source=faceResults?faceResults.map(r=>({...files.find(f=>f.id===r.file_id),match:r})).filter(f=>f.id):files;
  filtered = source.filter(f => (!query || f.name.toLocaleLowerCase().includes(query)) && (!$('folder').value || f.folder === $('folder').value) && (!$('onlySelected').checked || selected.has(f.id)));
  const groups=[];
  const definite=filtered.filter(f=>f.match?.match_type!=='review');
  const uncertain=filtered.filter(f=>f.match?.match_type==='review');
  for(let i=0;i<definite.length;i+=pageSize)groups.push(definite.slice(i,i+pageSize));
  if(uncertain.length)groups.push(uncertain);
  const pages = Math.max(1,groups.length);
  page = Math.max(0,Math.min(page,pages-1));
  pageItems=groups[page]||[];
  const fragment = document.createDocumentFragment();
  for (const f of pageItems) {
    const card = document.createElement('article'); card.className = 'photo'+(selected.has(f.id)?' selected':'');
    const open = document.createElement('button'); open.className='open'; open.setAttribute('aria-label','ดูรูป '+f.name);
    const img = document.createElement('img'); img.src='/api/photos/'+encodeURIComponent(f.id)+'/thumbnail'; img.alt=f.name; img.loading='lazy'; img.decoding='async';
    img.addEventListener('error',()=>{img.alt='โหลดภาพย่อไม่ได้ — '+f.name;});
    open.append(img); open.addEventListener('click',()=>showViewer(f.id));
    const label=document.createElement('label'); label.className='pick';
    const input=document.createElement('input');input.type='checkbox';input.checked=selected.has(f.id);input.disabled=!f.downloadable;input.setAttribute('aria-label','เลือก '+f.name);input.addEventListener('change',()=>toggle(f.id));label.append(input);
    const caption=document.createElement('div');caption.className='caption';
    const name=document.createElement('span');name.className='name';name.textContent=f.name;name.title=f.name;
    const bytes=document.createElement('span');bytes.className='size';bytes.textContent=size(f.size);caption.append(name,bytes);
    card.append(open,label,caption);
    if(f.match){const badge=document.createElement('p');badge.className=f.match.match_type==='review'?'matchBadge review':'matchBadge';badge.textContent=(f.match.match_type==='review'?'ไม่แน่ใจ · ตรวจสอบอีกครั้ง':'ผ่านเกณฑ์จับคู่')+' · ระยะห่าง '+f.match.distance.toFixed(3);card.append(badge);}
    fragment.append(card);
  }
  $('grid').replaceChildren(fragment);
  $('empty').hidden=filtered.length!==0;
  $('visibleCount').textContent=`พบ ${filtered.length} รูป`;
  $('pageLabel').textContent=`หน้า ${page+1} / ${pages}${pageItems[0]?.match?.match_type==='review'?' · รูปที่ไม่แน่ใจ (หน้าสุดท้าย)':''}`;
  $('previous').disabled=page===0;$('next').disabled=page>=pages-1;
  updateCounts();
}
async function load() {
  notice('กำลังอ่านรายการรูปจาก Google Drive…');
  try {
    const data=await api('/api/library');files=data.files;
    $('album').textContent=data.name;$('total').textContent=files.length.toLocaleString();
    const previousFolder=$('folder').value;
    $('folder').replaceChildren(new Option('ทั้งหมด',''),...[...new Set(files.map(f=>f.folder))].sort().map(f=>new Option(f||'โฟลเดอร์หลัก',f)));
    $('folder').value=previousFolder;
    selected=new Set([...selected].filter(id=>files.some(f=>f.id===id&&f.downloadable)));save();render();notice();
  } catch(e) { notice(e.message); }
}
function updateViewer() {
  const f=files.find(f=>f.id===viewerId);if(!f)return;
  $('faceStatus').textContent='';$('faceCrops').replaceChildren();$('faceOverlay').width=0;$('detectFaces').disabled=false;
  $('viewerName').textContent=f.name;$('viewerImage').src='/api/photos/'+encodeURIComponent(f.id)+'/preview';
  $('viewerSelect').textContent=selected.has(f.id)?'เอาออกจากที่เลือก':'เลือกภาพนี้';$('viewerSelect').disabled=!f.downloadable;
  const i=filtered.findIndex(v=>v.id===viewerId);$('viewerPrevious').disabled=i<=0;$('viewerNext').disabled=i<0||i>=filtered.length-1;
}
function showViewer(id){viewerId=id;updateViewer();$('viewer').showModal();}
function moveViewer(delta){const i=filtered.findIndex(f=>f.id===viewerId);if(filtered[i+delta]){viewerId=filtered[i+delta].id;updateViewer();}}
function setBusy(value){busy=value;updateCounts();}
async function pollJob() {
  if(!activeJob)return;
  try{
    const j=await api('/api/exports/'+activeJob);$('jobPanel').hidden=false;
    $('jobProgress').value=j.total?Math.round(j.done/j.total*100):0;
    $('jobDetails').textContent=`${j.done} / ${j.total} รูป · รับข้อมูลแล้ว ${size(j.bytes)}`;
    if(j.status==='ready'){
      $('jobTitle').textContent=j.format.toUpperCase()+' พร้อมดาวน์โหลดแล้ว';$('zipLink').textContent='ดาวน์โหลด '+j.format.toUpperCase();$('zipLink').href='/api/exports/'+j.id+'/download';$('zipLink').hidden=false;$('cancelJob').hidden=true;$('dismissJob').hidden=false;
      $('jobDetails').textContent+= ' · ลิงก์หมดอายุ '+new Date(j.expires*1000).toLocaleTimeString('th-TH',{hour:'2-digit',minute:'2-digit'});
      setBusy(false);activeJob=null;return;
    }
    if(['failed','cancelled'].includes(j.status)){
      $('jobTitle').textContent=j.status==='failed'?'เตรียมไฟล์ไม่สำเร็จ':'ยกเลิกแล้ว';$('jobDetails').textContent=j.error||'ยกเลิกการเตรียมไฟล์แล้ว';$('cancelJob').hidden=true;$('dismissJob').hidden=false;
      setBusy(false);activeJob=null;try{sessionStorage.removeItem(jobKey);}catch{};return;
    }
    $('jobTitle').textContent='กำลังเตรียม '+j.format.toUpperCase();setTimeout(pollJob,2000);
  }catch(e){notice(e.message);setBusy(false);activeJob=null;try{sessionStorage.removeItem(jobKey);}catch{}}
}
async function download(ids){
  if(!ids.length||busy)return;
  setBusy(true);notice();$('zipLink').hidden=true;$('cancelJob').hidden=false;$('dismissJob').hidden=true;
  try{const j=await api('/api/exports',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ids,format:$('archiveFormat').value})});activeJob=j.id;try{sessionStorage.setItem(jobKey,j.id);}catch{};pollJob();}
  catch(e){notice(e.message);setBusy(false);}
}
$('search').addEventListener('input',()=>{page=0;render();});$('folder').addEventListener('change',()=>{page=0;render();});$('onlySelected').addEventListener('change',()=>{page=0;render();});
$('previous').onclick=()=>{page--;render();};$('next').onclick=()=>{page++;render();};
$('selectVisible').onclick=()=>{for(const f of pageItems)if(f.downloadable)selected.add(f.id);save();render();};
$('clearSelected').onclick=()=>{selected.clear();save();render();};
$('refresh').onclick=async()=>{const b=$('refresh');b.disabled=true;notice('กำลังรีเฟรชคลังรูป…');try{await api('/api/faces/index',{method:'POST'});await pollIndex();notice('เริ่มอ่านคลังรูปและสร้างดัชนีใบหน้าแล้ว');}catch(e){notice(e.message);}finally{b.disabled=false;}};
$('downloadSelected').onclick=()=>download(files.filter(f=>selected.has(f.id)).map(f=>f.id));$('downloadAll').onclick=()=>download((faceResults?filtered:files).filter(f=>f.downloadable).map(f=>f.id));
$('cancelJob').onclick=async()=>{if(!activeJob)return;try{await api('/api/exports/'+activeJob+'/cancel',{method:'POST'});}catch(e){notice(e.message);}};
$('dismissJob').onclick=()=>{$('jobPanel').hidden=true;try{sessionStorage.removeItem(jobKey);}catch{}};
$('closeViewer').onclick=()=>$('viewer').close();$('viewerPrevious').onclick=()=>moveViewer(-1);$('viewerNext').onclick=()=>moveViewer(1);$('viewerSelect').onclick=()=>toggle(viewerId);
$('viewer').addEventListener('keydown',e=>{if(e.key==='ArrowLeft')moveViewer(-1);if(e.key==='ArrowRight')moveViewer(1);});
$('referenceInput').onchange=()=>{const f=$('referenceInput').files[0];if(!f||!f.type.startsWith('image/'))return;if(f.size>15*1024**2){notice('รูปอ้างอิงต้องไม่เกิน 15 MB');return;}if(refUrl)URL.revokeObjectURL(refUrl);refUrl=URL.createObjectURL(f);$('referenceImage').src=refUrl;$('referenceImage').hidden=false;$('refHint').hidden=true;$('clearReference').hidden=false;$('faceSearch').disabled=false;resetFaceResults();};
$('clearReference').onclick=()=>{if(refUrl)URL.revokeObjectURL(refUrl);refUrl=null;$('referenceImage').removeAttribute('src');$('referenceImage').hidden=true;$('refHint').hidden=false;$('clearReference').hidden=true;$('referenceInput').value='';$('faceSearch').disabled=true;resetFaceResults();};
try{const stored=JSON.parse(localStorage.getItem(storageKey)||'[]');if(Array.isArray(stored))selected=new Set(stored.filter(v=>typeof v==='string'));activeJob=sessionStorage.getItem(jobKey);}catch{}
load();pollIndex();if(activeJob){setBusy(true);pollJob();}

$('detectFaces').onclick=async()=>{
  const id=viewerId, button=$('detectFaces');button.disabled=true;
  $('faceStatus').textContent='กำลังตรวจตำแหน่งใบหน้า…';
  try{
    const result=await api('/api/photos/'+encodeURIComponent(id)+'/faces');
    if(viewerId!==id)return;
    const img=$('viewerImage');if(!img.complete)await img.decode();
    const overlay=$('faceOverlay');overlay.width=result.width;overlay.height=result.height;
    const scale=Math.min(img.clientWidth/result.width,img.clientHeight/result.height);
    overlay.style.width=(result.width*scale)+'px';overlay.style.height=(result.height*scale)+'px';
    overlay.style.left=((img.clientWidth-result.width*scale)/2)+'px';overlay.style.top=((img.clientHeight-result.height*scale)/2)+'px';
    const ctx=overlay.getContext('2d');ctx.strokeStyle='#74ff9c';ctx.lineWidth=Math.max(1,result.width/180);
    $('faceCrops').replaceChildren();
    for(const b of result.boxes){
      ctx.strokeRect(b.x,b.y,b.width,b.height);
      const canvas=document.createElement('canvas');canvas.width=160;canvas.height=160;
      const sx=img.naturalWidth/result.width,sy=img.naturalHeight/result.height;
      canvas.getContext('2d').drawImage(img,b.x*sx,b.y*sy,b.width*sx,b.height*sy,0,0,160,160);
      canvas.setAttribute('aria-label','ภาพใบหน้าที่ตรวจพบ');$('faceCrops').append(canvas);
    }
    $('faceStatus').textContent=result.count?'พบ '+result.count+' ใบหน้า · ตรวจดูด้วยตนเองอีกครั้ง':'ไม่พบใบหน้า · ใบหน้าเล็ก หันข้าง หรือถูกบังอาจตรวจไม่พบ';
  }catch(e){if(viewerId===id)$('faceStatus').textContent=e.message;}
  finally{if(viewerId===id)button.disabled=false;}
};

function resetFaceResults(){faceResults=null;page=0;$('clearFaceSearch').hidden=true;render();}
$('clearFaceSearch').onclick=resetFaceResults;
$('faceThreshold').oninput=()=>{$('thresholdValue').textContent=Number($('faceThreshold').value).toFixed(2);};
$('faceSearch').onclick=async()=>{
  const file=$('referenceInput').files[0];if(!file||faceBusy)return;
  faceBusy=true;$('faceSearch').disabled=true;$('referenceInput').disabled=true;$('clearReference').disabled=true;
  notice('กำลังค้นหาใบหน้าในคลัง…');
  try{
    const result=await api('/api/faces/search?threshold='+$('faceThreshold').value,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file});
    faceResults=[...result.matches.map(f=>({...f,match_type:'match'})),...result.review.map(f=>({...f,match_type:'review'}))];
    page=0;$('clearFaceSearch').hidden=false;render();
    notice(`พบรูปตรงกัน ${result.matches.length} รูป${result.review.length?' · รูปที่ไม่แน่ใจ '+result.review.length+' รูปอยู่หน้าสุดท้าย':''}`);
  }catch(e){notice(e.message);}finally{faceBusy=false;$('faceSearch').disabled=!$('referenceInput').files.length;$('referenceInput').disabled=false;$('clearReference').disabled=false;}
};
async function pollIndex(){
  clearTimeout(indexTimer);
  try{
    const s=await api('/api/faces/index');
    const names={idle:'พร้อมใช้งาน',running:'กำลังอ่านคลังรูป…',completed:'อ่านคลังรูปสำเร็จ',completed_with_errors:'อ่านสำเร็จบางส่วน',failed:'อ่านคลังรูปไม่สำเร็จ'};
    $('faceIndexStatus').textContent=`${names[s.status]||s.status} · ดัชนี ${s.photos} รูป / ${s.faces} ใบหน้า · อ่าน ${s.processed} ข้าม ${s.skipped} ผิดพลาด ${s.failed}${s.total?' จาก '+s.total+' รูป':''}`;
    $('refresh').disabled=s.status==='running';
    if(s.status==='running')indexTimer=setTimeout(pollIndex,2500);
    else if(s.status==='completed'||s.status==='completed_with_errors')await load();
  }catch(e){$('faceIndexStatus').textContent=e.message;}
}
