"""PC sender with a durable retry identifier, independent of the print agent."""
import base64
import json
import os
from pathlib import Path
import urllib.request
import urllib.error
import uuid
import hashlib

def send_file(config,home,options=None,path=None,job_id=None):
    from agent import atomic_json
    folder=Path(home)/'sender';folder.mkdir(parents=True,exist_ok=True)
    pending=folder/'pending.json';document=folder/'pending.bin'
    if pending.exists():
        state=json.loads(pending.read_text(encoding='utf-8'))
    else:
        if not isinstance(options,dict) or str(uuid.UUID(job_id))!=job_id:raise ValueError('Opciones o identificador de trabajo inválidos.')
        source=Path(path)
        if source.stat().st_size>25*1024*1024:raise ValueError('El archivo supera 25 MB.')
        data=source.read_bytes()
        if data.startswith(b'%PDF-'):mime='application/pdf'
        elif data.startswith(b'\x89PNG\r\n\x1a\n'):mime='image/png'
        elif data.startswith(b'\xff\xd8\xff'):mime='image/jpeg'
        else:raise ValueError('Selecciona PDF, PNG o JPEG.')
        options=dict(options,name=source.name)
        state={'id':job_id,'options':options,'mime':mime,'server':config['url'],'identity':hashlib.sha256(config['token'].encode()).hexdigest()}
        temp=document.with_suffix('.tmp');temp.write_bytes(data);os.replace(temp,document)
        atomic_json(pending,state)
    from transport import addresses,request
    if (state.get('identity') and state['identity']!=hashlib.sha256(config['token'].encode()).hexdigest()) or (not state.get('identity') and state['server'] not in addresses(config)):
        raise ValueError('El envío pendiente pertenece a otro servidor o vinculación. Revisa su estado antes de cambiar la cuenta.')
    encoded=base64.b64encode(json.dumps(state['options']).encode()).decode()
    try:
        result=json.loads(request(config,'client/jobs/'+state['id'],document.read_bytes(),
            {'Authorization':'Bearer '+config['token'],'Content-Type':state['mime'],'X-Print-Options':encoded},timeout=60))
    except urllib.error.HTTPError as e:
        try:message=json.load(e).get('error','No se pudo registrar el trabajo.')
        finally:e.close()
        raise ValueError(message) from None
    pending.unlink();document.unlink(missing_ok=True)
    return result
