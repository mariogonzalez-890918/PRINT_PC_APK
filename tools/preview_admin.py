"""Isolated UI fixture: never connects to or prints on a physical device."""
from pathlib import Path
import sys
import tempfile
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'pc'))
from hub import Service,Server,digest

with tempfile.TemporaryDirectory(prefix='jadprint-preview-') as folder:
    s=Service(folder)
    s.create_owner('demo@example.test','Demo-Only-12345')
    devices=[]
    for role,name in [('pc','PC1 · Recepción'),('pc','PC2 · Almacén'),('tablet','Tablet · Pedidos')]:
        code=uuid.uuid4().hex.upper()
        with s.db() as db:
            db.execute('INSERT INTO codes VALUES(?,?,?)',(digest(code),role,time.time()+60))
        devices.append(s.enroll('demo@example.test',code,name,role))
    s.heartbeat(devices[0]['id'],['EPSON · Documentos'])
    s.heartbeat(devices[1]['id'],['BIXOLON · Tickets 80 mm','Etiquetas · Almacén'])
    with s.db() as db:
        for p in db.execute('SELECT id FROM printers').fetchall():
            db.execute('INSERT INTO grants VALUES(?,?)',(devices[2]['id'],p['id']))
    s.save_inventory(devices[0]['id'],{'platform':'Windows','summary':{'manufacturer':'Fabricante de prueba','model':'PC de muestra','os':'Windows','os_version':'Versión de prueba','cpu':'CPU de muestra','processors':8,'ram_bytes':16*1024**3,'storage_bytes':512*1024**3},'components':[{'category':'RAM','data':{'Capacidad GB':16,'Tipo':'Memoria de muestra'}}],'errors':[]})
    s.save_inventory(devices[2]['id'],{'platform':'Android','summary':{'manufacturer':'Fabricante de prueba','model':'Tablet de muestra','os':'Android','os_version':'Versión de prueba','cpu':'CPU móvil de muestra','processors':8,'ram_bytes':4*1024**3,'storage_bytes':64*1024**3},'components':[{'category':'Pantalla','data':{'Ancho px':1280,'Alto px':800}}],'errors':[]})
    print('PREVIEW http://127.0.0.1:8766',flush=True)
    Server(('127.0.0.1',8766),s).serve_forever()
