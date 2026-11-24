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
function rememberFold(details,key,initial=false){
 details.dataset.fold=key;let saved=null;try{saved=localStorage.getItem('printerTabFold:'+key);}catch{}
 details.open=saved===null?initial:saved==='1';details.addEventListener('toggle',()=>{try{localStorage.setItem('printerTabFold:'+key,details.open?'1':'0');}catch{}});return details;
}
function deviceFold(title,key,badge){
 const card=el('details',undefined,'device'),summary=el('summary'),body=el('div',undefined,'fold-body');summary.append(el('span',title));if(badge)summary.append(el('span',badge,'badge'));card.append(summary,body);rememberFold(card,key);return {card,body,summary};
}
function wrapSection(id,title,nodes,initial=false){
 const details=el('details',undefined,'fold'),summary=el('summary',title),body=el('div',undefined,'fold-body');
 nodes[0].before(details);for(const node of nodes){if(node.id===id)node.removeAttribute('id');if(node.tagName==='H2')node.remove();else{if(node.tagName==='SECTION')node.querySelector(':scope > h2')?.remove();body.append(node);}}
 details.id=id;details.append(summary,body);rememberFold(details,id,initial);return details;
}
function revealAnchor(){
 if($('dashboard').hidden||!location.hash)return;
 const target=$(decodeURIComponent(location.hash.slice(1)));if(!target)return;
 let parent=target;while(parent){if(parent.tagName==='DETAILS')parent.open=true;parent=parent.parentElement;}
 target.scrollIntoView({block:'start'});
}
function organizeSections(){
 const style=el('style',`.fold,.device{background:white;border:1px solid #dce5ee;border-radius:14px;margin:14px 0;overflow:hidden;padding:0}.fold>summary,.device>summary{padding:18px 22px;cursor:pointer;font-size:20px;font-weight:650;overflow-wrap:anywhere}.fold>summary::marker,.device>summary::marker{color:#1464c0}.fold[open]>summary,.device[open]>summary{border-bottom:1px solid #e7edf4}.fold-body{padding:18px 22px}.fold-body>section{margin:0;padding:0;border:0}.device{margin:0}.device>summary{padding:16px;font-size:16px}.device>summary .badge{display:block;width:fit-content;margin-top:8px}.device>.fold-body{padding:14px 16px}.grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr))}.check{overflow-wrap:anywhere}summary:focus-visible{outline:3px solid #1464c0;outline-offset:-4px}`);document.head.append(style);
 const accountSection=$('account').closest('section');accountSection.querySelector('p').textContent='Abre solo la sección y el equipo que necesitas administrar.';
 const toolbar=el('div');for(const [title,open] of [['Contraer todo',false],['Expandir todo',true]]){const button=el('button',title,'secondary');button.onclick=()=>document.querySelectorAll('details[data-fold]').forEach(d=>{d.open=open;});toolbar.append(button);}accountSection.append(toolbar);
 wrapSection('registration','Registrar equipos',[$('addPC'),$('addTablet'),$('pairing')]);
 wrapSection('connections','Conexión del servidor · LAN y VPN',[$('serviceUrl').closest('section')]);
 wrapSection('preparation','Cómo compartir y usar impresoras',[$('printerStatus').closest('section')]);
 wrapSection('computers','Computadoras',[$('pcs').previousElementSibling,$('pcs')]);
 const heading=$('permissions'),description=heading.nextElementSibling;wrapSection('permissions','Asignar impresoras a PCs y móviles',[heading,description,$('tablets')],true);
 wrapSection('jobsSection','Últimos trabajos',[$('jobs').closest('section')]);
 wrapSection('inventory','Inventario, Excel y respaldo',[$('inventory')]);
 const branding=$('branding');branding.classList.add('fold');const body=el('div',undefined,'fold-body');for(const node of Array.from(branding.children))if(node.tagName!=='SUMMARY')body.append(node);branding.append(body);rememberFold(branding,'branding');
 for(const link of document.querySelectorAll('a[href^="#"]'))link.addEventListener('click',()=>setTimeout(revealAnchor,0));
 window.addEventListener('hashchange',revealAnchor);
}
function toggleDevice(d){const b=el('button',d.enabled?'Desactivar':'Reactivar','secondary');b.onclick=safely(async()=>{await api('admin/device',{id:d.id,enabled:!d.enabled});await refresh();});return b;}
function deleteDevice(d){const b=el('button','Eliminar equipo','secondary');b.style.color='#a21d26';b.onclick=safely(async()=>{
 if(!confirm('¿Eliminar definitivamente '+d.name+'?\n\nSe retirarán su vinculación, inventario, impresoras publicadas y permisos. Los trabajos en espera se cancelarán; el historial de impresión se conservará. Para volver a usarlo necesitarás registrarlo con un código nuevo.'))return;
 b.disabled=true;
 try{const result=await api('admin/device/delete',{id:d.id,confirmation:d.id});await refresh();message('Equipo eliminado: '+d.name+'.'+(result.cancelled?' Trabajos en espera cancelados: '+result.cancelled+'.':'')+(result.cleanup_errors?.length?' Algunos archivos de trabajos cancelados no se pudieron limpiar; revisa el almacenamiento del servidor.':''));}finally{if(b.isConnected)b.disabled=false;}
 });return b;}
async function refresh(){
 const data=await api('admin/state');$('login').hidden=true;$('dashboard').hidden=false;$('account').textContent=data.email;
 $('serviceUrl').value=data.service_url||'';
 $('printerStatus').textContent=data.printers.length?data.printers.length+' impresora(s) registradas. Controla cuáles se comparten y a qué equipos.':'Une las PCs con correo y código de registro; después pulsa Compartir impresoras en cada EXE.';
 const devices=new Map(data.devices.map(d=>[d.id,d]));
 $('pcs').replaceChildren();$('tablets').replaceChildren();$('jobs').replaceChildren();
 for(const d of data.devices){
  if(d.role==='pc'){
   const online=d.enabled&&Date.now()/1000-d.seen<45;
   const panel=deviceFold(d.name,'pc:'+d.id,!d.enabled?'Desactivada':online?'Conectada':'Sin conexión'),card=panel.card,content=panel.body;
   const report=(data.printer_reports||[]).find(r=>r.device===d.id);if(report?.warning)content.append(el('p','Impresoras de esta PC: '+report.warning,'muted'));
   for(const p of data.printers.filter(p=>p.pc===d.id)){
    const label=el('label',undefined,'check'),cb=el('input');cb.type='checkbox';cb.checked=p.shared!==0;
    label.append(cb,document.createTextNode('Compartir '+p.name+(p.available?'':' · no disponible')));content.append(label);
    cb.onchange=async()=>{const requested=cb.checked;cb.disabled=true;try{await api('admin/printer-sharing',{printer:p.id,enabled:requested});p.shared=requested?1:0;message(p.name+(requested?' habilitada para compartir.':' deshabilitada para compartir.'));}catch(error){cb.checked=!requested;message(error.message);}finally{cb.disabled=false;}};
   }
   content.append(toggleDevice(d));if(!d.enabled)content.append(deleteDevice(d));$('pcs').append(card);
  }
  const assigned=data.grants.filter(g=>g.tablet===d.id).length,panel=deviceFold((d.role==='pc'?'PC · ':'Móvil · ')+d.name,'receiver:'+d.id,(d.enabled?'Registrado':'Desactivado')+' · '+assigned+' asignada(s)'),receiver=panel.body;
  for(const p of data.printers){const label=el('label',undefined,'check'),cb=el('input');cb.type='checkbox';cb.value=p.id;cb.checked=data.grants.some(g=>g.tablet===d.id&&g.printer===p.id);label.append(cb,document.createTextNode((devices.get(p.pc)?.name||'PC')+' · '+p.name+(p.shared===0?' · compartición desactivada':'')));receiver.append(label);}
  if(!data.printers.length)receiver.append(el('p','No hay impresoras publicadas todavía.','muted'));
  const save=el('button','Guardar asignación');save.onclick=safely(async()=>{const selected=[...receiver.querySelectorAll('input:checked')].map(c=>c.value);await api('admin/grants',{tablet:d.id,printers:selected});panel.summary.querySelector('.badge').textContent=(d.enabled?'Registrado':'Desactivado')+' · '+selected.length+' asignada(s)';message('Asignación guardada para '+d.name+'.');});receiver.append(save);if(d.role!=='pc')receiver.append(toggleDevice(d));if(!d.enabled)receiver.append(deleteDevice(d));$('tablets').append(panel.card);
 }
 if(!$('pcs').children.length)$('pcs').append(el('p','Genera un código de PC y únela con su correo.','muted'));
 if(!$('tablets').children.length)$('tablets').append(el('p','Todavía no hay equipos registrados.','muted'));
 const names={queued:'En espera',claimed:'Entregado a PC · sin confirmar',submitted:'Enviado a Windows',error:'Error',unknown:'Resultado incierto · revisar'};
 for(const j of data.jobs){const row=el('tr');row.append(el('td',j.name),el('td',(devices.get(j.tablet)?.name||'Equipo')+' / '+(devices.get(j.pc)?.name||'PC')));const status=el('td');status.append(el('strong',names[j.status]||j.status),el('div',j.message,'muted'));row.append(status,el('td',new Date(j.created*1000).toLocaleString('es-MX')));$('jobs').append(row);}
 await refreshInventory();
 if(!refresh.anchorShown){revealAnchor();refresh.anchorShown=true;}
}
async function refreshInventory(){
 const data=await api('admin/inventory');$('inventoryRows').replaceChildren();
 for(const d of data.devices){
  const snapshot=d.inventory||{},summary=snapshot.summary||{},row=el('tr');
  const old=snapshot.platform==='Windows'&&(!snapshot.schema_version||snapshot.schema_version<2);
  const field=key=>{const value=summary[key];if(value&&value!=='No disponible')return String(value);if(old)return 'Reporte anterior: actualizar agente y solicitar auditoría';if(snapshot.platform==='Android')return 'Android no permite consultar este dato';return (snapshot.field_status||{})[key]||'No disponible: consultar diagnóstico';};
  row.append(el('td',d.name),el('td',snapshot.platform||(d.role==='pc'?'PC':'Móvil')),el('td',[summary.manufacturer,summary.model,summary.os,summary.os_version].filter(Boolean).join(' · ')));
  const hardware=el('td');hardware.append(el('div',summary.cpu||'CPU pendiente'),el('div',summary.ram_bytes?((Number(summary.ram_bytes)/1073741824).toFixed(1)+' GB RAM'):'RAM pendiente'),el('div',summary.storage_bytes?((Number(summary.storage_bytes)/1073741824).toFixed(1)+' GB almacenamiento'):'Almacenamiento pendiente'));row.append(hardware);
  const asset=el('td');asset.append(el('div','Serie: '+field('serial_number')),el('div','Service Tag: '+field('service_tag')),el('div','Asset Tag: '+field('asset_tag')));row.append(asset);
  const types=el('td');types.append(el('div','RAM: '+field('ram_types')),el('div','Discos: '+field('disk_types')),el('div','Conexión: '+field('disk_connections')),el('div','Formato: '+field('disk_formats')));row.append(types);
  const software=el('td');software.append(el('div','Antivirus: '+field('antivirus')),el('div',field('antivirus_status')),el('div','Office: '+field('office_type')),el('div','Versión: '+field('office_version')));row.append(software);
  row.append(el('td',d.pending?'Auditoría solicitada':d.received?new Date(d.received*1000).toLocaleString('es-MX'):'Sin auditoría'));
  const actions=el('td');const request=el('button','Solicitar auditoría');request.disabled=!d.enabled;request.onclick=safely(async()=>{await api('admin/inventory/request',{device:d.id});message('Auditoría solicitada a '+d.name+'. Se completará cuando su agente o APK esté conectado y activo.');await refreshInventory();});actions.append(request);
  if(d.inventory){const details=el('details');details.append(el('summary','Ver componentes / diagnóstico'));if(old)details.append(el('p','Reporte anterior a la auditoría ampliada. Actualiza el EXE del equipo e inicia impresión; enviará una auditoría nueva automáticamente.'));if(snapshot.collected_at)details.append(el('p','Recopilado: '+snapshot.collected_at+' · Agente: '+(snapshot.collector_version||'versión anterior')));for(const error of snapshot.errors||[])details.append(el('p',String(error)));const pre=el('pre',JSON.stringify(d.inventory,null,2));pre.style.whiteSpace='pre-wrap';details.append(pre);actions.append(details);}row.append(actions);$('inventoryRows').append(row);
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

organizeSections();

$('refreshInventory').onclick=safely(refreshInventory);
$('exportInventory').onclick=safely(async()=>{
 const response=await fetch('/api/admin/inventory.xlsx',{headers:{Authorization:'Bearer '+token}});
 if(!response.ok)throw Error('No se pudo exportar el inventario.');
 const url=URL.createObjectURL(await response.blob()),link=el('a');link.href=url;link.download='PRINTER-TAB-Inventario.xlsx';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
});
$('saveServiceUrl').onclick=safely(async()=>{await api('admin/service-url',{url:$('serviceUrl').value});message('Direcciones guardadas. Los códigos nuevos incluyen LAN, ZeroTier y Radmin; los clientes actualizados reciben la lista al conectarse y utilizan la dirección disponible.');});
$('detectServiceUrls').onclick=safely(async()=>{const data=await api('admin/network-addresses');$('serviceUrl').value=data.urls.join('\n');message('Direcciones detectadas en el servidor. Revisa la lista y pulsa Guardar direcciones LAN / VPN.');});
$('exportBackup').onclick=safely(async()=>{
 const response=await fetch('/api/admin/backup.zip',{headers:{Authorization:'Bearer '+token}});
 if(!response.ok)throw Error('No se pudo descargar el respaldo. Se requiere sesión administradora.');
 const url=URL.createObjectURL(await response.blob()),link=el('a');link.href=url;link.download='PRINTER-TAB-Respaldo-'+new Date().toISOString().slice(0,10)+'.zip';document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);
 message('Respaldo descargado. Contiene datos privados de la cuenta. Para restaurar usa Respaldo / restaurar / limpiar en el EXE del servidor nuevo. Los documentos pendientes no se trasladan.');
});
