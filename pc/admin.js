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
 $('serviceUrl').value=data.service_url||'';
 $('printerStatus').textContent=data.printers.length?data.printers.length+' impresora(s) registradas. Controla cuáles se comparten y a qué equipos.':'Une las PCs con correo y código de registro; después pulsa Compartir impresoras en cada EXE.';
 const devices=new Map(data.devices.map(d=>[d.id,d]));
 $('pcs').replaceChildren();$('tablets').replaceChildren();$('jobs').replaceChildren();
 for(const d of data.devices){
  if(d.role==='pc'){
   const card=el('div',undefined,'card');card.append(el('h3',d.name));
   const online=d.enabled&&Date.now()/1000-d.seen<45;
   card.append(el('span',!d.enabled?'Desactivada':online?'Conectada':'Sin conexión','badge'));
   for(const p of data.printers.filter(p=>p.pc===d.id)){
    const label=el('label',undefined,'check'),cb=el('input');cb.type='checkbox';cb.checked=p.shared!==0;
    label.append(cb,document.createTextNode('Compartir '+p.name+(p.available?'':' · no disponible')));card.append(label);
    cb.onchange=async()=>{const requested=cb.checked;cb.disabled=true;try{await api('admin/printer-sharing',{printer:p.id,enabled:requested});p.shared=requested?1:0;message(p.name+(requested?' habilitada para compartir.':' deshabilitada para compartir.'));}catch(error){cb.checked=!requested;message(error.message);}finally{cb.disabled=false;}};
   }
   card.append(toggleDevice(d));$('pcs').append(card);
  }
  const receiver=el('div',undefined,'card');receiver.append(el('h3',(d.role==='pc'?'PC · ':'Móvil · ')+d.name),el('span',d.enabled?'Registrado':'Desactivado','badge'));
  for(const p of data.printers){const label=el('label',undefined,'check'),cb=el('input');cb.type='checkbox';cb.value=p.id;cb.checked=data.grants.some(g=>g.tablet===d.id&&g.printer===p.id);label.append(cb,document.createTextNode((devices.get(p.pc)?.name||'PC')+' · '+p.name+(p.shared===0?' · compartición desactivada':'')));receiver.append(label);}
  if(!data.printers.length)receiver.append(el('p','No hay impresoras publicadas todavía.','muted'));
  const save=el('button','Guardar asignación');save.onclick=safely(async()=>{await api('admin/grants',{tablet:d.id,printers:[...receiver.querySelectorAll('input:checked')].map(c=>c.value)});message('Asignación guardada para '+d.name+'.');});receiver.append(save);if(d.role!=='pc')receiver.append(toggleDevice(d));$('tablets').append(receiver);
 }
 if(!$('pcs').children.length)$('pcs').append(el('p','Genera un código de PC y únela con su correo.','muted'));
 if(!$('tablets').children.length)$('tablets').append(el('p','Todavía no hay equipos registrados.','muted'));
 const names={queued:'En espera',claimed:'Entregado a PC · sin confirmar',submitted:'Enviado a Windows',error:'Error',unknown:'Resultado incierto · revisar'};
 for(const j of data.jobs){const row=el('tr');row.append(el('td',j.name),el('td',(devices.get(j.tablet)?.name||'Equipo')+' / '+(devices.get(j.pc)?.name||'PC')));const status=el('td');status.append(el('strong',names[j.status]||j.status),el('div',j.message,'muted'));row.append(status,el('td',new Date(j.created*1000).toLocaleString('es-MX')));$('jobs').append(row);}
 await refreshInventory();
}
async function refreshInventory(){
 const data=await api('admin/inventory');$('inventoryRows').replaceChildren();
 for(const d of data.devices){
  const snapshot=d.inventory||{},summary=snapshot.summary||{},row=el('tr');
  row.append(el('td',d.name),el('td',snapshot.platform||(d.role==='pc'?'PC':'Móvil')),el('td',[summary.manufacturer,summary.model,summary.os,summary.os_version].filter(Boolean).join(' · ')));
  const hardware=el('td');hardware.append(el('div',summary.cpu||'CPU pendiente'),el('div',summary.ram_bytes?((Number(summary.ram_bytes)/1073741824).toFixed(1)+' GB RAM'):'RAM pendiente'),el('div',summary.storage_bytes?((Number(summary.storage_bytes)/1073741824).toFixed(1)+' GB almacenamiento'):'Almacenamiento pendiente'));row.append(hardware);
  row.append(el('td',d.pending?'Auditoría solicitada':d.received?new Date(d.received*1000).toLocaleString('es-MX'):'Sin auditoría'));
  const actions=el('td');const request=el('button','Solicitar auditoría');request.disabled=!d.enabled;request.onclick=safely(async()=>{await api('admin/inventory/request',{device:d.id});message('Auditoría solicitada a '+d.name+'. Se completará cuando su agente o APK esté conectado y activo.');await refreshInventory();});actions.append(request);
  if(d.inventory){const details=el('details');details.append(el('summary','Ver componentes'));const pre=el('pre',JSON.stringify(d.inventory,null,2));pre.style.whiteSpace='pre-wrap';details.append(pre);actions.append(details);}row.append(actions);$('inventoryRows').append(row);
 }
}
async function pair(role){const r=await api('admin/code',{role});const box=$('pairing');box.replaceChildren(el('p','Registro de '+(role==='pc'?'PC':'tablet o celular')+' · vence en 15 minutos y se usa una vez. Correo: '+$('account').textContent));const code=el('textarea');code.readOnly=true;code.value=r.registration;code.rows=5;code.style.width='100%';code.setAttribute('aria-label','Código de registro completo');const copy=el('button','Copiar código de registro');copy.onclick=async()=>{try{await navigator.clipboard.writeText(code.value);message('Código copiado. Úsalo con el correo registrado en el EXE o APK.');}catch{code.focus();code.select();message('Código seleccionado: cópialo completo con Ctrl+C.');}};box.append(code,copy);}
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

if(location.hash==='#branding')$('branding').open=true;
window.addEventListener('hashchange',()=>{if(location.hash==='#branding')$('branding').open=true;});

$('refreshInventory').onclick=safely(refreshInventory);
$('exportInventory').onclick=safely(async()=>{
 const response=await fetch('/api/admin/inventory.xlsx',{headers:{Authorization:'Bearer '+token}});
 if(!response.ok)throw Error('No se pudo exportar el inventario.');
 const url=URL.createObjectURL(await response.blob()),link=el('a');link.href=url;link.download='PRINTER-TAB-Inventario.xlsx';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
});
$('saveServiceUrl').onclick=safely(async()=>{await api('admin/service-url',{url:$('serviceUrl').value});message('Dirección guardada para los próximos códigos de registro. Los clientes no necesitan escribirla. Debe ser accesible desde sus redes.');});
