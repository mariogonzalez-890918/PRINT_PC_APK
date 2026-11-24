"""Prepare a constrained Windows IPP installation plan, without changing the OS."""
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.request
import uuid
from agent import api,atomic_json,printers

def profile_tag(home):return hashlib.sha256(str(Path(home).absolute()).encode()).hexdigest()[:8]

def queue_name(printer,home):
    text=re.sub(r'[\x00-\x1f]',' ','PRINTER-TAB - '+printer['pc']+' - '+printer['name'])
    return text.encode('utf-8')[:180].decode('utf-8',errors='ignore')+' ['+profile_tag(home)+'-'+printer['id'][:8]+']'

def prepare(home,action):
    home=Path(home).absolute()
    if action not in ('install','remove'):raise ValueError('Acción de impresoras Windows no válida.')
    tag=profile_tag(home)
    installed=printers(include_managed=True)
    pattern=re.compile(r'^PRINTER-TAB - .*\['+tag+r'-[0-9a-f]{8}\]$')
    managed={name for name in installed if pattern.fullmatch(name)}
    desired=[];adds=[]
    if action=='install':
        path=home/'agent.json'
        health=None
        for attempt in range(10):
            config=json.loads(path.read_text(encoding='utf-8'));port=config.get('windows_bridge_port')
            if isinstance(port,int) and 20000<=port<30000:
                try:
                    with urllib.request.urlopen('http://127.0.0.1:'+str(port)+'/health',timeout=1) as response:health=json.load(response)
                    break
                except OSError:pass
            time.sleep(.5)
        if health is None:raise ValueError('Primero inicia impresión y espera a que aparezca Puente Windows activo. Cierra otros paneles de versiones anteriores si el agente ya estaba abierto.')
        if health.get('service')!='PRINTER-TAB-Windows' or health.get('profile')!=tag:raise ValueError('El puente de impresión Windows no está listo en este perfil.')
        for printer in api(config,'client/printers')['printers']:
            pid=printer['id']
            if not re.fullmatch('[0-9a-f]{32}',pid):raise ValueError('Identificador de impresora no válido.')
            display=queue_name(printer,home)
            desired.append(display)
            if display not in installed:adds.append({'name':display,'url':'http://127.0.0.1:'+str(port)+'/ipp/'+pid})
    removals=sorted(managed-set(desired))
    plan={'profile':tag,'add':adds,'remove':removals,'action':action}
    folder=home/'windows';folder.mkdir(parents=True,exist_ok=True)
    path=folder/('install-'+uuid.uuid4().hex+'.json');atomic_json(path,plan)
    return dict(plan,path=str(path))
