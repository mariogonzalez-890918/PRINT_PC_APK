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
    print('PREVIEW http://127.0.0.1:8766',flush=True)
    Server(('127.0.0.1',8766),s).serve_forever()
