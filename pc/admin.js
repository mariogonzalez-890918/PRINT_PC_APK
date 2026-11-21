'use strict';
let token = sessionStorage.getItem('jadPrintAdmin') || '';
const $ = id => document.getElementById(id);
const message = text => { $('message').textContent = text; };
function el(tag,text,cls){const e=document.createElement(tag);if(text!==undefined)e.textContent=text;if(cls)e.className=cls;return e;}
async function api(path,body){
 const r=await fetch('/api/'+path,{method:body?'POST':'GET',headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
 const result=await r.json();if(!r.ok)throw Error(result.error||'No se pudo completar la solicitud.');return result;
}
function safely(fn){return async()=>{try{await fn();}catch(e){message(e.message);}};}
function toggleDevice(d){const b=el('button',d.enabled?'Desactivar':'Reactivar','secondary');b.onclick=safely(async()=>{await api('admin/device',{id:d.id,enabled:!d.enabled});await refresh();});return b;}
async function refresh(){
 const data=await api('admin/state');$('login').hidden=true;$('dashboard').hidden=false;$('account').textContent=data.email;
 const devices=new Map(data.devices.map(d=>[d.id,d]));
 $('pcs').replaceChildren();$('tablets').replaceChildren();$('jobs').replaceChildren();
 for(const d of data.devices){
  const card=el('div',undefined,'card');card.append(el('h3',d.name));
  if(d.role==='pc'){
   const online=d.enabled&&Date.now()/1000-d.seen<45;
   card.append(el('span',!d.enabled?'Desactivada':online?'Conectada':'Sin conexión','badge'));
   const list=el('ul');for(const p of data.printers.filter(p=>p.pc===d.id))list.append(el('li',p.name+(p.available?'':' · no disponible')));
   card.append(list,toggleDevice(d));if(!list.children.length)card.append(el('p','Inicia el agente de impresión en esta PC.','muted'));$('pcs').append(card);
  }else{
   card.append(el('span',d.enabled?'Vinculada':'Desactivada','badge'));
   for(const p of data.printers){const label=el('label',undefined,'check');const cb=el('input');cb.type='checkbox';cb.value=p.id;cb.checked=data.grants.some(g=>g.tablet===d.id&&g.printer===p.id);label.append(cb,document.createTextNode((devices.get(p.pc)?.name||'PC')+' · '+p.name));card.append(label);}
   if(!data.printers.length)card.append(el('p','Vincula e inicia una PC para ver sus impresoras.','muted'));
   const save=el('button','Guardar permisos');save.onclick=safely(async()=>{await api('admin/grants',{tablet:d.id,printers:[...card.querySelectorAll('input:checked')].map(c=>c.value)});message('Permisos guardados para '+d.name+'.');});card.append(save,toggleDevice(d));$('tablets').append(card);
  }
 }
 if(!$('pcs').children.length)$('pcs').append(el('p','Todavía no hay PCs. Genera un código y vincula el programa instalado en cada computadora.','muted'));
 if(!$('tablets').children.length)$('tablets').append(el('p','Genera un código de tablet e introdúcelo en la APK.','muted'));
 const names={queued:'En espera',claimed:'Entregado a PC · sin confirmar',submitted:'Enviado a Windows',error:'Error',unknown:'Resultado incierto · revisar'};
 for(const j of data.jobs){const row=el('tr');row.append(el('td',j.name),el('td',(devices.get(j.tablet)?.name||'Tablet')+' / '+(devices.get(j.pc)?.name||'PC')));const status=el('td');status.append(el('strong',names[j.status]||j.status),el('div',j.message,'muted'));row.append(status,el('td',new Date(j.created*1000).toLocaleString('es-MX')));$('jobs').append(row);}
}
async function pair(role){const r=await api('admin/code',{role});const box=$('pairing');box.replaceChildren(el('p','Código para '+(role==='pc'?'PC':'tablet')+' · vence en 15 minutos y se usa una vez:'));box.append(el('code',r.code),el('p','En el dispositivo indica la dirección de este servidor, el correo de la cuenta y este código.','muted'));}
$('loginForm').onsubmit=async e=>{e.preventDefault();try{const r=await api('login',{email:$('email').value,password:$('password').value});token=r.token;sessionStorage.setItem('jadPrintAdmin',token);$('password').value='';message('');await refresh();}catch(error){message(error.message);}};
$('addPC').onclick=safely(()=>pair('pc'));$('addTablet').onclick=safely(()=>pair('tablet'));$('refresh').onclick=safely(refresh);
$('logout').onclick=()=>{sessionStorage.removeItem('jadPrintAdmin');token='';$('dashboard').hidden=true;$('login').hidden=false;message('Sesión cerrada en este navegador.');};
if(token)safely(refresh)();
const refreshLogo=()=>{$('brandLogo').src='/branding/logo?v='+Date.now();};
$('saveLogo').onclick=safely(async()=>{
 const file=$('logoFile').files[0];if(!file)throw Error('Selecciona una imagen para el logo.');
 if(file.size>2*1024*1024)throw Error('El logo debe pesar hasta 2 MB.');
 const r=await fetch('/api/admin/logo',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':file.type||'application/octet-stream'},body:file});
 const result=await r.json();if(!r.ok)throw Error(result.error||'No se pudo guardar el logo.');
 $('logoFile').value='';refreshLogo();message('Logo guardado. También se actualizará al volver al panel de Windows.');
});
$('resetLogo').onclick=safely(async()=>{await api('admin/logo/reset',{});refreshLogo();message('Logo original restaurado.');});
$('passwordForm').onsubmit=async e=>{e.preventDefault();try{
 if($('newPassword').value!==$('repeatPassword').value)throw Error('Las contraseñas nuevas no coinciden.');
 await api('admin/password',{current:$('currentPassword').value,password:$('newPassword').value});
 $('passwordForm').reset();message('Contraseña actualizada. Las otras sesiones de administrador se cerraron.');
}catch(error){message(error.message);}};
$('saveIcon').onclick=safely(async()=>{
 const file=$('iconFile').files[0];if(!file)throw Error('Selecciona un archivo para el icono.');
 if(file.size>2*1024*1024)throw Error('El icono debe pesar hasta 2 MB.');
 const r=await fetch('/api/admin/icon',{method:'POST',headers:{Authorization:'Bearer '+token,'Content-Type':file.type||'application/octet-stream'},body:file});
 const result=await r.json();if(!r.ok)throw Error(result.error||'No se pudo guardar el icono.');
 $('iconFile').value='';message('Icono guardado. Vuelve al panel de Windows para aplicarlo a la ventana, bandeja y accesos directos.');
});
$('resetIcon').onclick=safely(async()=>{await api('admin/icon/reset',{});message('Icono original restaurado. Vuelve al panel de Windows para aplicarlo.');});
