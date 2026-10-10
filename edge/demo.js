
let goals=[{name:'准备考试',min:60,done:false,icon:'♫'},{name:'阅读一本书',min:30,done:true,icon:'▤'},{name:'运动一下',min:45,done:false,icon:'✦'}];
let selected=0,elapsed=0,remaining=1500,running=false,endAt=0,toastTimeout,lastDeleted=null;
try{const saved=JSON.parse(localStorage.getItem('gugu-goals'));if(Array.isArray(saved)&&saved.every(g=>g&&typeof g.name==='string'&&Number.isFinite(g.min)&&g.min>0))goals=saved}catch{}
const modal=document.getElementById('modal');
function activeGoal(){return goals[selected]}
function duration(g){return g?Math.min(g.min,25)*60:0}
if(!goals.length){selected=-1;remaining=0}else remaining=duration(activeGoal());
function save(){try{localStorage.setItem('gugu-goals',JSON.stringify(goals))}catch{}}
function render(){
 const list=document.getElementById('goals'),scroll=list.scrollTop;list.replaceChildren();
 if(!goals.length){const empty=document.createElement('div');empty.className='empty-goals';empty.innerHTML='<strong>还没有目标</strong>添加一个小目标，开始今天的专注。';list.append(empty)}
 goals.forEach((g,i)=>{
  const row=document.createElement('div');row.className='goal'+(i===selected?' selected':'');
  const icon=document.createElement('span');icon.className='icon';icon.textContent=g.icon||'▤';
  const info=document.createElement('div');info.className='goal-info';info.tabIndex=0;info.setAttribute('role','button');info.setAttribute('aria-label','选择 '+g.name);
  const title=document.createElement('strong');title.textContent=g.name;title.title=g.name;const sub=document.createElement('small');sub.textContent=g.min+' 分钟';info.append(title,sub);
  const choose=()=>{if(running){say('请先暂停当前专注，再切换目标');return}selected=i;remaining=duration(g);render();update()};info.onclick=choose;info.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose()}};
  const check=document.createElement('button');check.className='check'+(g.done?' done':'');check.textContent=g.done?'✓':'';check.setAttribute('aria-label',(g.done?'取消完成 ':'标记完成 ')+g.name);check.setAttribute('aria-pressed',g.done);check.onclick=()=>{g.done=!g.done;save();render()};
  const remove=document.createElement('button');remove.className='goal-delete';remove.title='删除目标';remove.setAttribute('aria-label','删除 '+g.name);remove.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7"/></svg>';remove.onclick=()=>removeGoal(i);
  row.append(icon,info,check,remove);list.append(row);
 });
 list.scrollTop=scroll;const done=goals.filter(g=>g.done).length;document.getElementById('progresslabel').innerHTML='<b>'+done+'</b> / '+goals.length+' 个目标已完成';document.getElementById('fill').style.width=(goals.length?done/goals.length*100:0)+'%';document.getElementById('completed').textContent=done;document.getElementById('count').textContent=goals.length;document.getElementById('taskname').textContent=activeGoal()?'▤　'+activeGoal().name:'先添加一个目标';
 document.querySelectorAll('.controls button,.dock button.active').forEach(b=>b.disabled=!goals.length);
}
function update(){document.getElementById('timer').textContent=String(Math.floor(remaining/60)).padStart(2,'0')+':'+String(remaining%60).padStart(2,'0');document.getElementById('minutes').textContent=Math.floor(elapsed/60);document.getElementById('play').innerHTML=running?'Ⅱ<small>暂停</small>':'▷<small>开始</small>';document.getElementById('state').textContent=!activeGoal()?'添加目标，开始新一段专注':remaining===0?'这一段专注完成了！':running?'保持专注，你正在前进':'准备好，开始专注'}
function tick(){if(!running)return;if(!activeGoal()){running=false;update();return}const next=Math.max(0,Math.ceil((endAt-Date.now())/1000));elapsed+=Math.max(0,remaining-next);remaining=next;if(!remaining){running=false;activeGoal().done=true;save();render();say('太棒了！这一段专注已完成。')}update()}
function toggle(){if(!activeGoal()){openAdd();return}if(running){tick();running=false}else{if(remaining===0)remaining=duration(activeGoal());running=true;endAt=Date.now()+remaining*1000}update()}
function reset(){running=false;remaining=duration(activeGoal());update()}
function skip(){if(!goals.length)return;if(running)tick();running=false;selected=(selected+1)%goals.length;reset();render();say('已切换到下一个目标')}
function removeGoal(index){
 const goal=goals[index];if(!goal)return;const active=activeGoal();if(goal===active&&running)tick();const oldRemaining=remaining;
 goals.splice(index,1);if(goal===active){running=false;selected=goals.length?Math.min(index,goals.length-1):-1;remaining=duration(activeGoal())}else selected=goals.indexOf(active);
 lastDeleted={goal,index,remaining:oldRemaining};save();render();update();say('已删除「'+goal.name+'」',undoDelete);
}
function undoDelete(){if(!lastDeleted)return;const item=lastDeleted,active=activeGoal();lastDeleted=null;goals.splice(Math.min(item.index,goals.length),0,item.goal);selected=active?goals.indexOf(active):goals.indexOf(item.goal);if(!active){remaining=item.remaining;running=false}save();render();update();say('已恢复目标')}
function openAdd(){if(!modal.open)modal.showModal();document.getElementById('name').focus()}
function say(message,undo){const t=document.getElementById('toast');t.replaceChildren(document.createTextNode(message));if(undo){const b=document.createElement('button');b.textContent='撤销';b.onclick=undo;t.append(b)}t.classList.add('show');clearTimeout(toastTimeout);toastTimeout=setTimeout(()=>t.classList.remove('show'),undo?7000:3200)}
document.getElementById('form').onsubmit=e=>{e.preventDefault();const name=document.getElementById('name').value.trim(),min=Number(document.getElementById('duration').value);if(!name||!Number.isFinite(min)||min<1||min>240)return;goals.push({name,min,done:false,icon:'▤'});if(selected<0){selected=0;remaining=duration(activeGoal())}save();render();update();modal.close();e.target.reset();document.getElementById('goals').scrollTop=document.getElementById('goals').scrollHeight;say('新目标已添加，加油！')};
setInterval(tick,250);render();update();


function sizeFocusUI(){const narrow=innerWidth<700;const scale=narrow?Math.min(1.12,(innerWidth-42)/350):Math.min(1.65,Math.max(.72,(innerHeight-126)/740),Math.max(.72,(innerWidth-100)/760));document.documentElement.style.setProperty('--u',scale.toFixed(4));}
sizeFocusUI();addEventListener('resize',sizeFocusUI);

document.querySelector('[data-demo-action="0"]').addEventListener("click",function(event){say('今天也要向目标前进一点点')});
document.querySelector('[data-demo-action="1"]').addEventListener("click",function(event){say('点击目标文字选择计时，圆圈标记完成，垃圾桶删除目标')});
document.querySelector('[data-demo-action="2"]').addEventListener("click",function(event){openAdd()});
document.querySelector('[data-demo-action="3"]').addEventListener("click",function(event){openAdd()});
document.querySelector('[data-demo-action="4"]').addEventListener("click",function(event){reset()});
document.querySelector('[data-demo-action="5"]').addEventListener("click",function(event){say('找个安静的角落，开始这一段专注吧')});
document.querySelector('[data-demo-action="6"]').addEventListener("click",function(event){reset()});
document.querySelector('[data-demo-action="7"]').addEventListener("click",function(event){toggle()});
document.querySelector('[data-demo-action="8"]').addEventListener("click",function(event){skip()});
document.querySelector('[data-demo-action="9"]').addEventListener("click",function(event){document.getElementById('goals').scrollIntoView({behavior:'smooth',block:'center'})});
document.querySelector('[data-demo-action="10"]').addEventListener("click",function(event){openAdd()});
document.querySelector('[data-demo-action="11"]').addEventListener("click",function(event){toggle()});
document.querySelector('[data-demo-action="12"]').addEventListener("click",function(event){say('选择任务 → 开始计时 → 完成目标。目标会保存在此浏览器。')});
document.querySelector('[data-demo-action="13"]').addEventListener("click",function(event){modal.close()});
