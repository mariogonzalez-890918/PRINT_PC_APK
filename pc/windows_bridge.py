"""Per-profile loopback IPP printer bridge, using durable UUIDs and central grants."""
from contextlib import contextmanager
import hashlib
import http.server
import json
import os
from pathlib import Path
import re
import sqlite3
import struct
import subprocess
import sys
import threading
import time
import uuid
import urllib.parse
from agent import api,atomic_json,ApiFailure
from client import send_file
import ipp_protocol as ipp

MAX_INPUT=64*1024*1024
TERMINAL=('completed','failed','cancelled')

class Broker:
    def __init__(self,home,config_path):
        self.home=Path(home);self.home.mkdir(parents=True,exist_ok=True)
        self.config_path=Path(config_path);self.lock=threading.RLock();self.stop=threading.Event()
        self.cached=[];self.cache_time=-100
        try:
            cache=json.loads((self.home/'authorized.json').read_text(encoding='utf-8'))
            if cache['owner']==self.owner():self.cached=cache['printers']
        except (OSError,ValueError,KeyError):pass
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS jobs(id INTEGER PRIMARY KEY AUTOINCREMENT,uuid TEXT UNIQUE,printer TEXT,name TEXT,mime TEXT,options TEXT,state TEXT,message TEXT,created REAL,updated REAL,fingerprint TEXT,size INTEGER,document_hash TEXT)')
            if 'document_hash' not in {r[1] for r in db.execute('PRAGMA table_info(jobs)')}:db.execute('ALTER TABLE jobs ADD COLUMN document_hash TEXT')
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.home/'jobs.sqlite3',timeout=20);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def config(self):return json.loads(self.config_path.read_text(encoding='utf-8'))
    def owner(self):return hashlib.sha256(self.config()['token'].encode()).hexdigest()
    def allowed(self):
        with self.lock:
            if time.monotonic()-self.cache_time>10:
                try:
                    self.cached=api(self.config(),'client/printers')['printers'];self.cache_time=time.monotonic()
                    atomic_json(self.home/'authorized.json',{'owner':self.owner(),'printers':self.cached})
                except OSError:
                    if not self.cached:raise
                except RuntimeError:self.cached=[];raise
            return self.cached
    def printer(self,pid):
        printer=next((p for p in self.allowed() if p['id']==pid),None)
        if not printer:raise PermissionError('Esta impresora no está asignada a esta PC.')
        return printer
    def create(self,pid,attrs,document=b'',request_id=0):
        self.printer(pid)
        def first(name,default):return (attrs.get(name) or [default])[0]
        copies=int(first('copies',1));mime=first('document-format','application/pdf')
        if not 1<=copies<=20:raise ValueError('Selecciona de 1 a 20 copias.')
        if mime not in ('application/pdf','image/pwg-raster','image/jpeg','application/octet-stream'):raise ValueError('Formato de impresión no admitido.')
        if first('sides','one-sided')!='one-sided':raise ValueError('Esta cola admite impresión a una cara.')
        if first('compression','none')!='none':raise ValueError('Compresión IPP no admitida.')
        media=first('media','driver')
        options={'printer':pid,'copies':copies,'scale':'fit','paper':'A4' if media=='iso_a4_210x297mm' else 'letter' if media=='na_letter_8.5x11in' else 'driver','color':'monochrome' if first('print-color-mode','color')=='monochrome' else 'color'}
        fingerprint=self.owner();now=time.time()
        # Retransmission of the same Print-Job request returns its original receipt.
        request_key=hashlib.sha256((pid+'|'+str(first('job-uuid',request_id))+'|'+fingerprint+json.dumps([options,mime,str(first('job-name','Documento Windows'))],sort_keys=True)).encode()+document).hexdigest() if document else ''
        with self.lock,self.db() as db:
            if document:
                old=db.execute('SELECT * FROM jobs WHERE fingerprint=? AND created>?',(request_key,now-120)).fetchone()
                if old:return dict(old)
            if db.execute("SELECT count(*) FROM jobs WHERE state NOT IN ('completed','failed','cancelled')").fetchone()[0]>=100:raise ValueError('Cola local llena.')
            if db.execute('SELECT COALESCE(sum(size),0) FROM jobs').fetchone()[0]+len(document)>512*1024*1024:raise ValueError('Almacenamiento local de impresión lleno.')
            uid=str(uuid.uuid4());folder=self.home/uid;folder.mkdir()
            atomic_json(folder/'owner.json',{'owner':fingerprint})
            if document:(folder/'source.bin').write_bytes(document)
            cursor=db.execute('INSERT INTO jobs(uuid,printer,name,mime,options,state,message,created,updated,fingerprint,size,document_hash) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                (uid,pid,str(first('job-name','Documento Windows'))[:160],mime,json.dumps(options),'pending' if document else 'held','Guardado en PRINTER-TAB',now,now,request_key,len(document),hashlib.sha256(document).hexdigest() if document else ''))
            return dict(db.execute('SELECT * FROM jobs WHERE id=?',(cursor.lastrowid,)).fetchone())
    def get(self,job_id,pid):
        with self.db() as db:row=db.execute('SELECT * FROM jobs WHERE id=? AND printer=?',(job_id,pid)).fetchone()
        if not row:raise ValueError('Trabajo no disponible en esta cola.')
        return dict(row)
    def document(self,job_id,pid,data,mime=None):
        if not data:raise ValueError('Documento vacío.')
        self.printer(pid)
        with self.lock,self.db() as db:
            row=self.get(job_id,pid);source=self.home/row['uuid']/'source.bin'
            if row['state']!='held':
                if row['document_hash']==hashlib.sha256(data).hexdigest():return row
                raise ValueError('El trabajo ya tiene un documento diferente o fue procesado.')
            if db.execute('SELECT COALESCE(sum(size),0) FROM jobs').fetchone()[0]+len(data)>512*1024*1024:raise ValueError('Almacenamiento local lleno.')
            source.write_bytes(data)
            db.execute("UPDATE jobs SET state='pending',size=?,mime=?,updated=?,document_hash=? WHERE id=?",(len(data),mime or row['mime'],time.time(),hashlib.sha256(data).hexdigest(),job_id))
        return self.get(job_id,pid)
    def cancel(self,job_id,pid):
        row=self.get(job_id,pid)
        with self.db() as db:
            if row['state'] not in TERMINAL:db.execute("UPDATE jobs SET state='cancelling',updated=? WHERE id=?",(time.time(),job_id))
        return self.get(job_id,pid)
    def update(self,job_id,state,message):
        with self.db() as db:db.execute('UPDATE jobs SET state=?,message=?,updated=? WHERE id=?',(state,str(message)[:500],time.time(),job_id))
        if state in TERMINAL:
            with self.db() as db:row=db.execute('SELECT uuid FROM jobs WHERE id=?',(job_id,)).fetchone()
            if row:
                folder=self.home/row['uuid']
                for name in ('source.bin','document.pdf','document.tmp.pdf','owner.json','sender/pending.json','sender/pending.bin'):
                    target=folder/name
                    if folder.resolve() in target.resolve().parents:target.unlink(missing_ok=True)
                with self.db() as db:db.execute('UPDATE jobs SET size=0 WHERE id=?',(job_id,))
    def prepare(self,row):
        folder=self.home/row['uuid'];source=folder/'source.bin';target=folder/'document.pdf';temporary=folder/'document.tmp.pdf'
        if target.is_file():return target
        prefix=source.read_bytes()[:8]
        if prefix.startswith(b'%PDF-'):temporary.write_bytes(source.read_bytes())
        elif prefix.startswith(b'RaS2'):
            try:result=subprocess.run([sys.executable,str(Path(__file__).with_name('pwg_raster.py')),str(source),str(temporary)],capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
            except subprocess.TimeoutExpired:raise ValueError('La conversión Windows tardó demasiado. El documento no fue enviado.') from None
            if result.returncode:raise ValueError('No se pudo convertir la impresión Windows: '+result.stdout.decode('utf-8',errors='replace')[:300])
        elif prefix.startswith(b'\xff\xd8\xff'):
            from PIL import Image
            with Image.open(source) as image:
                if image.width*image.height>25_000_000:raise ValueError('Imagen demasiado grande.')
                image.convert('RGB').save(temporary,'PDF',resolution=300)
        else:raise ValueError('Windows envió un formato distinto de PDF, PWG Raster o JPEG.')
        if temporary.stat().st_size>25*1024*1024:raise ValueError('Documento convertido mayor de 25 MB.')
        os.replace(temporary,target)
        return target
    def process_once(self):
        with self.db() as db:rows=[dict(r) for r in db.execute("SELECT * FROM jobs WHERE state NOT IN ('completed','failed','cancelled','held') ORDER BY updated LIMIT 5")]
        for row in rows:
            folder=self.home/row['uuid']
            try:
                config=self.config()
                if json.loads((folder/'owner.json').read_text())['owner']!=hashlib.sha256(config['token'].encode()).hexdigest():
                    self.update(row['id'],'failed','Cambió la vinculación. No se envió el documento con otra cuenta.');continue
                if row['state']=='cancelling':
                    result=api(config,'client/jobs/'+row['uuid']+'/cancel',{})
                    self.update(row['id'],'cancelled' if result['cancelled'] else 'accepted','Cancelado' if result['cancelled'] else 'Ya entregado a la PC; revisa su cola Windows.');continue
                if row['state']=='pending':
                    target=self.prepare(row)
                    if self.get(row['id'],row['printer'])['state']=='cancelling':continue
                    options=dict(json.loads(row['options']),name=row['name'])
                    send_file(config,folder,options,target,row['uuid'])
                    with self.db() as db:db.execute("UPDATE jobs SET state='accepted',message='En espera de la PC destino',updated=? WHERE id=? AND state='pending'",(time.time(),row['id']))
                else:
                    result=api(config,'client/jobs/'+row['uuid'])
                    state={'submitted':'completed','error':'failed','unknown':'failed','cancelled':'cancelled'}.get(result['status'],'accepted')
                    self.update(row['id'],state,result.get('message','En proceso'))
            except ApiFailure as error:
                if error.status>=500 or error.status==429:
                    with self.db() as db:db.execute('UPDATE jobs SET message=?,updated=? WHERE id=?',('Servidor temporalmente no disponible; se conserva el identificador.',time.time(),row['id']))
                else:self.update(row['id'],'failed',str(error))
            except (ValueError,RuntimeError) as error:self.update(row['id'],'failed',str(error))
            except Exception as error:
                with self.db() as db:db.execute('UPDATE jobs SET message=?,updated=? WHERE id=?',('Sin confirmación; se conserva el identificador. '+str(error)[:300],time.time(),row['id']))
    def work(self):
        while not self.stop.is_set():
            try:self.process_once()
            except Exception:pass
            self.stop.wait(3)

def job_attributes(row,url):
    state={'held':4,'pending':3,'accepted':5,'cancelling':5,'completed':9,'failed':8,'cancelled':7}[row['state']]
    reason='job-data-insufficient' if state==4 else 'job-completed-successfully' if state==9 else 'aborted-by-system' if state==8 else 'job-canceled-by-user' if state==7 else 'none'
    return [('job-id',0x21,row['id']),('job-uri',0x45,url+'/jobs/'+str(row['id'])),('job-name',0x42,row['name']),('job-state',0x23,state),
        ('job-state-reasons',0x44,reason),('job-state-message',0x41,row['message']),('job-printer-uri',0x45,url)]

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def setup(self):super().setup();self.connection.settimeout(60)
    def read_input(self):
        if self.headers.get('Transfer-Encoding','').lower()=='chunked':
            data=bytearray()
            while True:
                line=self.rfile.readline(100)
                size=int(line.strip().split(b';')[0],16)
                if size==0:
                    for _ in range(32):
                        if self.rfile.readline(4096) in (b'\r\n',b'\n',b''):break
                    return bytes(data)
                if size<0 or len(data)+size>MAX_INPUT+65536:raise ValueError('Documento demasiado grande.')
                block=self.rfile.read(size)
                if len(block)!=size or self.rfile.read(2)!=b'\r\n':raise ValueError('Documento truncado.')
                data.extend(block)
        length=int(self.headers.get('Content-Length','0'))
        if not 0<length<=MAX_INPUT+65536:raise ValueError('Tamaño de documento no admitido.')
        data=self.rfile.read(length)
        if len(data)!=length:raise ValueError('Documento truncado.')
        return data
    def do_GET(self):
        from windows_queues import profile_tag
        data=json.dumps({'service':'PRINTER-TAB-Windows','profile':profile_tag(self.server.broker.config_path.parent)}).encode()
        self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
    def do_POST(self):
        request=1;body=b''
        try:
            body=self.read_input();operation,request,attrs,document=ipp.decode(body)
            pid=self.path.split('/')[2] if self.path.startswith('/ipp/') else ''
            if not re.fullmatch('[0-9a-f]{32}',pid):raise ValueError('Cola no válida.')
            broker=self.server.broker;printer=broker.printer(pid);url='ipp://127.0.0.1:'+str(self.server.server_port)+'/ipp/'+pid
            first=lambda key,default=None:(attrs.get(key) or [default])[0]
            groups=[];extra=b''
            if operation==11:
                from windows_queues import queue_name
                attributes,extra=ipp.printer_attributes(printer,url,queue_name(printer,broker.config_path.parent));groups=[(4,attributes)]
            elif operation==4:
                if first('document-format','application/pdf') not in ('application/pdf','image/pwg-raster','image/jpeg','application/octet-stream'):raise ValueError('Formato no admitido.')
            elif operation in (2,5):
                if operation==2 and not document:raise ValueError('Documento vacío.')
                row=broker.create(pid,attrs,document if operation==2 else b'',request);groups=[(2,job_attributes(row,url))]
            elif operation in (6,8,9):
                job_id=first('job-id')
                if job_id is None:job_id=int(str(first('job-uri','')).rsplit('/',1)[-1])
                if operation==6:
                    if not first('last-document',True):raise ValueError('Solo se admite un documento por trabajo.')
                    row=broker.document(int(job_id),pid,document,first('document-format'))
                elif operation==8:row=broker.cancel(int(job_id),pid)
                else:row=broker.get(int(job_id),pid)
                groups=[(2,job_attributes(row,url))]
            elif operation==10:
                with broker.db() as db:rows=[dict(r) for r in db.execute('SELECT * FROM jobs WHERE printer=? ORDER BY id DESC LIMIT 100',(pid,))]
                groups=[(2,job_attributes(row,url)) for row in rows]
            else:
                result=ipp.response(request,0x0501,message='Operación IPP no admitida.');self.send_ipp(result);return
            result=ipp.response(request,groups=groups);result=result[:-1]+extra+b'\x03'
        except PermissionError as error:result=ipp.response(request,0x0403,message=str(error))
        except (ValueError,KeyError,TypeError) as error:result=ipp.response(request,0x0400,message=str(error))
        except Exception as error:result=ipp.response(request,0x0502,message='Servidor no disponible: '+str(error)[:250])
        if body[:2] in (b'\x01\x01',b'\x02\x00'):result=body[:2]+result[2:]
        self.send_ipp(result)
    def send_ipp(self,data):
        self.send_response(200);self.send_header('Content-Type','application/ipp');self.send_header('Content-Length',str(len(data)));self.send_header('Connection','close');self.end_headers();self.wfile.write(data);self.close_connection=True

class Server(http.server.ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self,address,broker):self.broker=broker;self.slots=threading.BoundedSemaphore(8);super().__init__(address,Handler)
    def process_request(self,request,address):
        if not self.slots.acquire(blocking=False):self.shutdown_request(request);return
        try:super().process_request(request,address)
        except Exception:self.slots.release();raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

def start(home,config):
    home=Path(home);broker=Broker(home/'windows',home/'agent.json')
    port=config.get('windows_bridge_port') or 20000+int(hashlib.sha256(str(home).encode()).hexdigest()[:6],16)%10000
    server=Server(('127.0.0.1',port),broker)
    if config.get('windows_bridge_port')!=port:config['windows_bridge_port']=port;atomic_json(home/'agent.json',config)
    threading.Thread(target=server.serve_forever,daemon=True).start();threading.Thread(target=broker.work,daemon=True).start()
    return server,broker
