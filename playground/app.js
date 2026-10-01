const $ = id => document.getElementById(id);
const canvas = $('map'), ctx = canvas.getContext('2d');
const level = {Water:6, Oil:7, Wine:8};
const names = {Water:'水', Oil:'油', Wine:'葡萄酒'};
let ingredients = [], bases = {}, settings = {}, scenes = {}, zones = {}, vortexes = {}, boundaries = {};
let view = {scale:1, panX:0, panY:0};
let state = freshState();
let undoStack = [];
let busy = false;
let ui = {ingredients:{}, effects:{}}, effectIcons = {};
const ingredientName = id => ui.ingredients[id]?.name || id;
const effectName = id => ui.effects[id]?.name || id;
function localizeText(text){
  const entries=[...Object.entries(ui.ingredients),...Object.entries(ui.effects)].sort((a,b)=>b[0].length-a[0].length);
  for(const [id,item] of entries)text=text.replaceAll(id,item.name);
  return text;
}

function closeIngredientPicker(restoreFocus=false){
  $('ingredientPopover').hidden=true;
  $('ingredientTrigger').setAttribute('aria-expanded','false');
  if(restoreFocus)$('ingredientTrigger').focus();
}
function selectIngredient(id){
  $('ingredient').value=id;
  const item=selectedIngredient();
  $('selectedIngredientName').textContent=ingredientName(id);
  $('selectedIngredientIcon').src=ui.ingredients[id].icon;
  $('selectedIngredientPrice').textContent=`基础价值 ${item.price.toFixed(1)}`;
  updateIngredientHint();
}
function renderIngredientOptions(){
  const query=$('ingredientSearch').value.trim().toLocaleLowerCase();
  const items=ingredients.filter(item=>item.name!=='Default'&&
    (ingredientName(item.name).includes(query)||item.name.toLowerCase().includes(query)));
  const fragment=document.createDocumentFragment();
  for(const item of items){
    const option=document.createElement('button');
    option.type='button';option.className='ingredientOption';
    option.setAttribute('role','option');option.setAttribute('aria-selected',String(item.name===$('ingredient').value));
    const img=document.createElement('img');img.src=ui.ingredients[item.name].icon;img.alt='';
    const label=document.createElement('span');label.textContent=ingredientName(item.name);
    const price=document.createElement('small');price.textContent=item.price.toFixed(1);
    option.append(img,label,price);
    option.onclick=()=>{selectIngredient(item.name);closeIngredientPicker(true)};
    option.onkeydown=event=>{
      const options=[...$('ingredientOptions').children],index=options.indexOf(option);
      if(event.key==='ArrowDown'||event.key==='ArrowUp'){
        event.preventDefault();options[(index+(event.key==='ArrowDown'?1:-1)+options.length)%options.length]?.focus();
      }
      if(event.key==='Home'){event.preventDefault();options[0]?.focus()}
      if(event.key==='End'){event.preventDefault();options.at(-1)?.focus()}
    };
    fragment.append(option);
  }
  $('ingredientOptions').replaceChildren(fragment);
  $('ingredientCount').textContent=items.length?`${items.length} 种药材 · 右侧为基础价值`:'没有找到匹配的药材';
}
$('ingredientTrigger').onclick=()=>{
  if(!$('ingredientPopover').hidden){closeIngredientPicker();return}
  $('ingredientPopover').hidden=false;$('ingredientTrigger').setAttribute('aria-expanded','true');
  $('ingredientSearch').value='';renderIngredientOptions();$('ingredientSearch').focus();
};
$('ingredientSearch').oninput=renderIngredientOptions;
$('ingredientSearch').onkeydown=event=>{
  if(event.key==='ArrowDown'){event.preventDefault();$('ingredientOptions').firstElementChild?.focus()}
  if(event.key==='Enter'){$('ingredientOptions').firstElementChild?.click()}
};
document.addEventListener('keydown',event=>{
  if(event.key==='Escape'&&!$('ingredientPopover').hidden){event.preventDefault();closeIngredientPicker(true)}
});
document.addEventListener('click',event=>{if(!event.target.closest('.ingredientPicker'))closeIngredientPicker()});
for(const panel of document.querySelectorAll('details.panel')){
  try{const saved=localStorage.getItem(panel.id);if(saved!==null)panel.open=saved==='open'}catch{}
  panel.addEventListener('toggle',()=>{
    try{localStorage.setItem(panel.id,panel.open?'open':'closed')}catch{}
    if(panel.id==='panel-ingredient'&&!panel.open)closeIngredientPicker();
  });
}

function freshState(){ return {base:'Water', pos:{x:0,y:0}, rotation:0, health:1, heat:0, failed_reason:null, pending:[], path_sections:[], traveled:[], teleports:[], steps:[], operations:[], used:[], salts:{}, effects:[], collected:[], hover:null}; }
function clone(v){return JSON.parse(JSON.stringify(v));}
function save(){undoStack.push(clone(state)); if(undoStack.length>80) undoStack.shift();}
function bezier(c,t){
  const u=1-t;
  return {x:u*u*u*c.PFirst.x+3*u*u*t*c.P1.x+3*u*t*t*c.P2.x+t*t*t*c.PLast.x,
          y:u*u*u*c.PFirst.y+3*u*u*t*c.P1.y+3*u*t*t*c.P2.y+t*t*t*c.PLast.y};
}
function distance(a,b){return Math.hypot(a.x-b.x,a.y-b.y);}
function lerp(a,b,t){return {x:a.x+(b.x-a.x)*t,y:a.y+(b.y-a.y)*t};}
function sampleIngredient(item,grind){
  // EvenlySpacedPointsPath.CalculateEvenlySpacedPoints: 10 divisions per
  // serialized curve length, then 0.05 map-unit spacing.
  const spacing=settings.RecipeMapManagerPathSettings[item.is_teleportation?'ingredientPathSpacingGraphics':'ingredientPathSpacingPhysics'];
  const curves=item.bezier_path, points=[clone(curves[0].PFirst)];
  let previous=points[0], remaining=0;
  for(const curve of curves){
    const n=Math.ceil(10*curve._length);
    for(let j=0;j<=n;j++){
      const point=bezier(curve,j/n);
      remaining+=distance(previous,point);
      while(remaining>=spacing){
        remaining-=spacing;
        const dx=previous.x-point.x,dy=previous.y-point.y;
        const mag=Math.hypot(dx,dy)||1;
        const next={x:point.x+dx/mag*remaining,y:point.y+dy/mag*remaining};
        points.push(next);previous=next;
      }
      previous=point;
    }
  }
  if(remaining>0)points.push(clone(curves.at(-1).PLast));
  return cutByLength(points,item.grinded_path_starts_from+grind*(1-item.grinded_path_starts_from));
}
function cutByLength(points,fraction){
  if(fraction>=1)return points;
  const total=points.slice(1).reduce((n,p,i)=>n+distance(points[i],p),0);
  const target=total*fraction,out=[points[0]];
  let sum=0;
  for(let i=1;i<points.length;i++){
    const d=distance(points[i-1],points[i]);
    if(sum+d>=target){out.push(lerp(points[i-1],points[i],d?((target-sum)/d):0));break;}
    out.push(points[i]);sum+=d;
  }
  return out;
}
function translated(points,start){return points.map(p=>({x:p.x+start.x,y:p.y+start.y}));}
function selectedIngredient(){return ingredients.find(x=>x.name===$('ingredient').value);}
function preview(){
  const item=selectedIngredient();if(!item)return[];
  const start=state.pending.length?state.pending.at(-1):state.pos;
  return translated(sampleIngredient(item,+$('grind').value/100),start);
}
async function applyOperation(action){
  if(busy)return;
  busy=true;update();
  try{
    const response=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({state,action})});
    const result=await response.json();
    if(!response.ok)throw Error(result.error||'操作失败');
    if(action.kind!=='inspect')save();
    state={...state,...result.state,steps:result.message?[...state.steps,result.message]:state.steps,
      operations:action.kind==='inspect'?state.operations:[...(state.operations||[]),clone(action)]};
    $('status').textContent=result.failure?`药剂失败：${result.failure}`:'统一酿药引擎 · 帧级碰撞、旋转动画与动作重叠仍在校准';
    if(action.kind==='vortex_demo')focusPath();
  }catch(error){$('status').textContent=error.message;}
  finally{busy=false;update();}
}
function addIngredient(){
  const item=selectedIngredient();if(!item)return;
  return applyOperation({kind:'add',name:item.name,grind:+$('grind').value/100});
}
function stir(){
  if(!state.pending.length)return;
  const pct=+$('stir').value/100;if(pct<=0)return;
  return applyOperation({kind:'stir',fraction:pct});
}
function ladle(){
  return applyOperation({kind:'pour',seconds:+$('pourTime').value,strength:+$('pourStrength').value/100});
}
function rotate(salt){
  const operation={kind:'salt',salt,amount:+$('saltAmount').value};
  if((salt==='sun'||salt==='moon')&&$('deferredRotation').checked)operation.deferred=true;
  return applyOperation(operation);
}
function fit(){
  const rect=canvas.getBoundingClientRect(),dpr=window.devicePixelRatio||1;
  canvas.width=Math.round(rect.width*dpr);canvas.height=Math.round(rect.height*dpr);
  ctx.setTransform(dpr,0,0,dpr,0,0);
  const size=bases[state.base].map_size;
  view.scale=Math.min(rect.width/size.x,rect.height/size.y)*0.90;
  view.panX=0;view.panY=0;draw();
}
function focusPath(includeHistory=false){
  const points=[state.pos,...state.pending,...preview(),
    ...(includeHistory?state.traveled.flat():[]),...(includeHistory?(state.teleports||[]).flatMap(event=>event.path):[])];
  const xmin=Math.min(...points.map(p=>p.x))-2,xmax=Math.max(...points.map(p=>p.x))+2;
  const ymin=Math.min(...points.map(p=>p.y))-2,ymax=Math.max(...points.map(p=>p.y))+2;
  view.scale=Math.min(canvas.clientWidth/(xmax-xmin),canvas.clientHeight/(ymax-ymin))*.9;
  view.panX=-(xmin+xmax)/2*view.scale;view.panY=(ymin+ymax)/2*view.scale;
  draw();
}
function screen(p){return {x:canvas.clientWidth/2+view.panX+p.x*view.scale,
                           y:canvas.clientHeight/2+view.panY-p.y*view.scale};}
function world(p){return {x:(p.x-canvas.clientWidth/2-view.panX)/view.scale,
                           y:-(p.y-canvas.clientHeight/2-view.panY)/view.scale};}
function drawPath(points,color,width=2,dash=[]){
  if(points.length<2)return;ctx.save();ctx.strokeStyle=color;ctx.lineWidth=width;ctx.setLineDash(dash);
  ctx.beginPath();points.forEach((p,i)=>{const q=screen(p);i?ctx.lineTo(q.x,q.y):ctx.moveTo(q.x,q.y)});
  ctx.stroke();ctx.restore();
}
function drawZones(){
  if(!$('showZones').checked)return;
  const palette={strong_danger:'#866555',weak_danger:'#b39474',swamp:'#7b9a84',heal:'#76ad8a'};
  for(const [zone,shapes] of Object.entries(zones[state.base])){
    ctx.fillStyle=palette[zone]||'#aaa';ctx.globalAlpha=zone==='strong_danger'?.35:.24;
    for(const s of shapes){
      const p=screen({x:s[1],y:s[2]});ctx.beginPath();
      if(s[0]==='circle')ctx.arc(p.x,p.y,Math.max(.4,s[3]*view.scale),0,Math.PI*2);
      else{ctx.save();ctx.translate(p.x,p.y);ctx.rotate(-s[5]);
        ctx.rect(-s[3]*view.scale/2,-s[4]*view.scale/2,s[3]*view.scale,s[4]*view.scale);ctx.restore();}
      ctx.fill();
    }
  }
  ctx.globalAlpha=1;
}
function drawBoundary(){
  const boundary=boundaries[state.base]?.[0];if(!boundary)return;
  ctx.save();ctx.strokeStyle='#6a5140';ctx.lineWidth=2.2;
  for(const path of boundary.paths){
    ctx.beginPath();path.forEach((p,i)=>{
      const q=screen({x:p.x+boundary.position.x+boundary.offset.x,
                      y:p.y+boundary.position.y+boundary.offset.y});
      i?ctx.lineTo(q.x,q.y):ctx.moveTo(q.x,q.y);
    });ctx.closePath();ctx.stroke();
  }
  ctx.restore();
}
function drawVortices(){
  if(!$('showVortices').checked)return;
  ctx.save();ctx.strokeStyle='#54778d';ctx.fillStyle='#779aad';ctx.lineWidth=1.2;
  for(const v of vortexes[state.base]||[]){
    const p=screen(v.entry);ctx.beginPath();ctx.arc(p.x,p.y,Math.max(2,v.entry_radius*view.scale),0,Math.PI*2);
    ctx.globalAlpha=.55;ctx.stroke();ctx.globalAlpha=.13;ctx.fill();
    if(view.scale>=2.5){
      const path=[];for(const c of v.path)for(let i=0;i<=24;i++){
        const q=bezier(c,i/24);path.push({x:v.entry.x+q.x,y:v.entry.y+q.y});
      }
      ctx.globalAlpha=.36;drawPath(path,'#55788e',1,[3,4]);
    }
  }
  ctx.restore();
}
function draw(){
  const w=canvas.clientWidth,h=canvas.clientHeight;
  ctx.clearRect(0,0,w,h);ctx.fillStyle='#ebd7a9';ctx.fillRect(0,0,w,h);
  ctx.strokeStyle='#bba477';ctx.lineWidth=1;
  for(let x=-80;x<=80;x+=10){const a=screen({x,y:-80}),b=screen({x,y:80});ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}
  for(let y=-80;y<=80;y+=10){const a=screen({x:-80,y}),b=screen({x:80,y});ctx.beginPath();ctx.moveTo(a.x,a.y);ctx.lineTo(b.x,b.y);ctx.stroke()}
  drawZones();drawBoundary();drawVortices();
  for(const e of bases[state.base].effects){
    const p=screen(e.Position),radius=Math.max(5,.79*view.scale);ctx.beginPath();ctx.arc(p.x,p.y,radius,0,Math.PI*2);
    ctx.fillStyle='#efe1b5';ctx.fill();ctx.strokeStyle='#865d3a';ctx.lineWidth=2;ctx.stroke();
    const icon=effectIcons[e.name];
    if(icon){
      // Native map keeps effect symbols upright (PotionEffectMapItem.cs).
      const size=radius*1.5,scale=size/Math.max(icon.width,icon.height);
      ctx.drawImage(icon,p.x-icon.width*scale/2,p.y-icon.height*scale/2,icon.width*scale,icon.height*scale);
    }
    if(view.scale>=4){ctx.fillStyle='#35271b';ctx.font='12px "Microsoft YaHei",sans-serif';ctx.textAlign='center';ctx.fillText(effectName(e.name),p.x,p.y-8-radius);}
  }
  for(const trace of state.traveled)drawPath(trace,'#8c5a3b',2.5);
  for(const event of state.teleports||[])drawPath(event.path,'#895d9c',2.5,[2,5]);
  let offset=0, start=state.pos;
  for(const section of state.path_sections||[]){
    const points=state.pending.slice(offset,offset+section.point_count);
    drawPath([start,...points],section.teleport?'#895d9c':'#596f73',2,section.teleport?[2,5]:[5,4]);
    start=points.at(-1)||start;offset+=section.point_count;
  }
  if(!state.path_sections?.length)drawPath([state.pos,...state.pending],'#596f73',2,[5,4]);
  drawPath(preview(),'#378697',2,[4,3]);
  const collision=screen(state.pos);ctx.beginPath();ctx.arc(collision.x,collision.y,.7400000095367432*view.scale,0,Math.PI*2);ctx.strokeStyle='#265c7d88';ctx.lineWidth=1;ctx.stroke();
  const p=screen(state.pos);ctx.beginPath();ctx.arc(p.x,p.y,7,0,Math.PI*2);ctx.fillStyle=state.failed_reason?'#a43c31':'#265c7d';ctx.fill();ctx.strokeStyle='white';ctx.lineWidth=2;ctx.stroke();
  ctx.beginPath();ctx.moveTo(p.x,p.y);ctx.lineTo(p.x+13*Math.cos(state.rotation*Math.PI/180),p.y-13*Math.sin(state.rotation*Math.PI/180));ctx.strokeStyle='#17364b';ctx.stroke();
  const hover=state.hover;if(hover){const q=screen(hover);ctx.fillStyle='#443525';ctx.font='12px sans-serif';ctx.textAlign='left';ctx.fillText(`(${hover.x.toFixed(2)}, ${hover.y.toFixed(2)})`,q.x+8,q.y-8)}
}
function update(){
  const score=state.nearest;
  $('readout').innerHTML=`位置：(${state.pos.x.toFixed(3)}, ${state.pos.y.toFixed(3)})<br>`+
    `朝向：${state.rotation.toFixed(2)}°${state.rotation_tween?.active?`（目标 ${(state.target_rotation??state.rotation).toFixed(2)}°，旋转中）`:''}<br>`+
    `生命值：${(state.health*100).toFixed(1)}%<br>`+
    `炉温：${((state.heat||0)*100).toFixed(1)}%<br>`+
    `起点：${state.start_mode==='vortex_demo'?'机制观察场景（非合法配方起点）':'基液中心'}<br>`+
    `接触漩涡：${state.touching_vortex||'无'}<br>`+
    `剩余路径：${(state.remaining_length||0).toFixed(3)} 单位<br>`+
    `已用药材：${state.used.length} 件<br>`+
    `盐用量：${Object.entries(state.salts).map(([salt,n])=>`${{sun:'太阳',moon:'月亮',life:'生命',void:'虚无',philosopher:'贤者'}[salt]} ${n}`).join('，')||'无'}<br>`+
    `已收集药效：${state.effects.map(([effect,tier])=>`${effectName(effect)} ${tier}级`).join('，')||'无'}<br>`+
    (score?`最近药效：${effectName(score.name)}，距离 ${score.distance.toFixed(3)}，角差 ${score.angle.toFixed(2)}°`+
    (score.tier?`<br>当前对齐等级：${'ⅠⅡⅢ'[score.tier-1]}`:'<br>当前不在药效碰撞圈内'):'最近药效：无');
  if(state.failed_reason)$('readout').append(Object.assign(document.createElement('p'),{textContent:`药剂失败：${state.failed_reason}`}));
  const teleport=state.teleports?.at(-1);
  if(teleport)$('readout').innerHTML+=`<br>最近传送：${localizeText(teleport.name)}，近似耗时 ${teleport.duration.toFixed(3)} 秒，最低生命值 ${(teleport.minimum_health*100).toFixed(1)}%`;
  $('history').innerHTML=state.steps.map(x=>`<li>${localizeText(x).replaceAll('&','&amp;').replaceAll('<','&lt;')}</li>`).join('');
  for(const id of ['stirButton','ladleSmall','ladleFull','sunSalt','moonSalt','lifeSalt','voidSalt','philosopherSalt','heat','pump','wait','add'])$(id).disabled=busy||!!state.failed_reason;
  for(const id of ['undo','reset','export'])$(id).disabled=busy;
  $('stirButton').disabled=busy||!!state.failed_reason||!state.pending.length;
  $('base').disabled=busy;
  $('ingredientTrigger').disabled=busy;
  $('replayFile').disabled=busy;
  $('loadVortexDemo').disabled=busy||!vortexes[state.base]?.length;
  draw();
}
function updateIngredientHint(){
  const item=selectedIngredient();
  const crystal=!!item?.is_teleportation;
  $('add').disabled=busy||!!state.failed_reason;
  $('ingredientHint').textContent=crystal?'晶体段以紫色点线显示。搅拌触发整段传送，落地后需再次搅拌后续路径。淡入淡出损伤采用近似帧模拟，仍在校准。':'虚线路径是预览。加入后用“搅拌”沿路径前进。';
  draw();
}
let referenceURL=null;
function updateReference(){
  const img=$('referenceImage');
  img.style.opacity=String(+$('referenceOpacity').value/100);
  img.style.height=$('referenceScale').value+'%';
  img.style.left=`calc(50% + ${$('referenceX').value}px)`;
  img.style.top=`calc(50% + ${$('referenceY').value}px)`;
  for(const [name,unit] of [['Opacity','%'],['Scale','%'],['X',' px'],['Y',' px']])
    $('reference'+name+'Value').value=$('reference'+name).value+unit;
}
async function load(){
  const paths=['data/ingredients.json','data/bases.json','data/brewing_settings.json',
    ...[6,7,8].flatMap(i=>[`data/level${i}_markers.json`,`data/level${i}_zones.json`,
                                `data/level${i}_vortices.json`,`data/level${i}_boundaries.json`]),'data/ui_manifest.json'];
  const data=await Promise.all(paths.map(p=>fetch(p).then(r=>{if(!r.ok)throw Error(p);return r.json()})));
  [ingredients,bases,settings]=data;
  ui=data.at(-1);
  await Promise.all(Object.entries(ui.effects).map(([name,item])=>new Promise((resolve,reject)=>{
    const image=new Image();image.onload=()=>{effectIcons[name]=image;resolve()};
    image.onerror=()=>reject(Error(`药效图标载入失败：${item.name}`));image.src=item.icon;
  })));
  for(const [i,name] of Object.entries(level)){
    const k=+name,offset=3+(k-6)*4;
    scenes[i]=data[offset];zones[i]=data[offset+1];
    vortexes[i]=data[offset+2];boundaries[i]=data[offset+3];
  }
  for(const base of Object.keys(bases))$('base').add(new Option(names[base],base));
  for(const item of ingredients.filter(x=>x.name!=='Default'))$('ingredient').add(new Option(ingredientName(item.name),item.name));
  $('base').value='Water';
  $('status').textContent='资源已加载 · 碰撞图形与药效坐标为原始数据；移动操作仍在校验';
  selectIngredient('Firebell');
  fit();update();updateIngredientHint();
  await applyOperation({kind:'inspect'});
  updateVortexList();
  const queued=sessionStorage.getItem('potionRecipeReplay');
  if(queued){sessionStorage.removeItem('potionRecipeReplay');await importRecipe(JSON.parse(queued));}
}
function updateVortexList(){
  $('vortexDemo').replaceChildren();
  for(const v of [...vortexes[state.base]].sort((a,b)=>Math.hypot(a.entry.x,a.entry.y)-Math.hypot(b.entry.x,b.entry.y)))
    $('vortexDemo').add(new Option(`${v.name} · (${v.entry.x.toFixed(2)}, ${v.entry.y.toFixed(2)})`,v.name));
  $('loadVortexDemo').disabled=busy||!vortexes[state.base].length;
}
$('grind').oninput=()=>{$('grindValue').value=$('grind').value+'%';draw()};
$('stir').oninput=()=>{$('stirValue').value=$('stir').value+'%'};
$('ingredient').onchange=updateIngredientHint;$('showZones').onchange=draw;$('showVortices').onchange=draw;
$('focusPath').onclick=()=>focusPath();$('focusHistory').onclick=()=>focusPath(true);$('fitMap').onclick=fit;
$('referenceFile').onchange=e=>{if(referenceURL)URL.revokeObjectURL(referenceURL);const file=e.target.files[0];referenceURL=file?URL.createObjectURL(file):null;$('referenceImage').src=referenceURL||'';$('referenceImage').hidden=!referenceURL;};
for(const name of ['Opacity','Scale','X','Y'])$('reference'+name).oninput=updateReference;
$('clearReference').onclick=()=>{if(referenceURL)URL.revokeObjectURL(referenceURL);referenceURL=null;$('referenceImage').hidden=true;$('referenceImage').removeAttribute('src');$('referenceFile').value='';};
$('add').onclick=addIngredient;$('stirButton').onclick=stir;
$('ladleSmall').onclick=ladle;$('ladleFull').onclick=()=>applyOperation({kind:'center'});
$('sunSalt').onclick=()=>rotate('sun');$('moonSalt').onclick=()=>rotate('moon');
$('lifeSalt').onclick=()=>rotate('life');$('voidSalt').onclick=()=>rotate('void');
$('philosopherSalt').onclick=()=>rotate('philosopher');
$('heat').onclick=()=>applyOperation({kind:'heat'});
$('pump').onclick=()=>applyOperation({kind:'pump',angle:+$('bellowsAngle').value,seconds:+$('heatTime').value});
$('wait').onclick=()=>applyOperation({kind:'wait',seconds:+$('heatTime').value});
$('loadVortexDemo').onclick=()=>applyOperation({kind:'vortex_demo',name:$('vortexDemo').value});
$('export').onclick=()=>{const blob=new Blob([JSON.stringify({gameVersion:'2.0.2',engineStatus:'calibrating',...state},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='potion-replay.json';a.click();URL.revokeObjectURL(url);};
async function importRecipe(document){
  if(busy)return;
  busy=true;update();
  try{
    if(document.gameVersion!=='2.0.2'||!Array.isArray(document.operations))throw Error('需要本实验台新版导出的 2.0.2 操作文件');
    const response=await fetch('/api/replay',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({base:document.base,operations:document.operations})});
    const result=await response.json();if(!response.ok)throw Error(result.error||'重放失败');
    save();state={...freshState(),...result.state,steps:result.steps,operations:result.operations};
    $('base').value=state.base;updateVortexList();focusPath();
    if(document.target&&!result.failure){
      const expected=JSON.stringify([[document.target.effect,document.target.tier]]);
      if(JSON.stringify(state.effects)!==expected)throw Error('回放药效与保存目标不一致，请查看当前状态');
    }
    $('status').textContent=result.failure?`重放至药剂失败：${result.failure}`:`已重放 ${result.operations.length} 个操作 · 引擎仍在校准`;
  }catch(error){$('status').textContent=error.message;}
  finally{busy=false;update();}
}
$('replayFile').onchange=async event=>{
  const file=event.target.files[0];if(!file||busy)return;
  try{await importRecipe(JSON.parse(await file.text()));}
  catch(error){$('status').textContent=error.message;}
  finally{event.target.value='';}
};
$('undo').onclick=()=>{if(undoStack.length){const previousBase=state.base;state=undoStack.pop();$('base').value=state.base;if(previousBase!==state.base)updateVortexList();update()}};
$('reset').onclick=()=>{save();state=freshState();state.base=$('base').value;applyOperation({kind:'inspect'})};
$('base').onchange=()=>{save();state=freshState();state.base=$('base').value;fit();updateVortexList();applyOperation({kind:'inspect'})};
let dragging=null;
canvas.onpointerdown=e=>{dragging={x:e.clientX,y:e.clientY,panX:view.panX,panY:view.panY};canvas.setPointerCapture(e.pointerId)};
canvas.onpointermove=e=>{if(dragging){view.panX=dragging.panX+e.clientX-dragging.x;view.panY=dragging.panY+e.clientY-dragging.y;draw()}else{const r=canvas.getBoundingClientRect();state.hover=world({x:e.clientX-r.left,y:e.clientY-r.top});draw()}};
canvas.onpointerup=()=>dragging=null;canvas.onpointerleave=()=>{if(!dragging){state.hover=null;draw()}};
canvas.onwheel=e=>{e.preventDefault();const r=canvas.getBoundingClientRect(),p={x:e.clientX-r.left,y:e.clientY-r.top};const before=world(p);
  view.scale=Math.max(.6,Math.min(120,view.scale*(e.deltaY<0?1.12:1/1.12)));
  view.panX=p.x-canvas.clientWidth/2-before.x*view.scale;view.panY=p.y-canvas.clientHeight/2+before.y*view.scale;draw()};
window.onresize=()=>{if(Object.keys(bases).length)fit()};
load().catch(e=>{$('status').textContent=`数据载入失败：${e.message}`;console.error(e)});
