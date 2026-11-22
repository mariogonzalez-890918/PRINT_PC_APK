"""JAD Print: local account, device enrollment, permissions and durable print queue."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import base64
import getpass
import hashlib
import hmac
import http.server
import io
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sqlite3
import threading
import time
import urllib.parse
import uuid

MAX_FILE = 25 * 1024 * 1024
MAX_PENDING = 100
STATES = {'submitted', 'error', 'unknown'}

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def password_hash(value, salt):
    return hashlib.pbkdf2_hmac('sha256', value.encode(), bytes.fromhex(salt), 600_000).hex()

class Service:
    def __init__(self, home):
        self.home = Path(home)
        self.home.mkdir(parents=True, exist_ok=True)
        self.files = self.home / 'queue'
        self.files.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS owner(email TEXT PRIMARY KEY, salt TEXT, password TEXT);
            CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, expires REAL);
            CREATE TABLE IF NOT EXISTS branding(key TEXT PRIMARY KEY, value BLOB);
            CREATE TABLE IF NOT EXISTS codes(code TEXT PRIMARY KEY, role TEXT, expires REAL);
            CREATE TABLE IF NOT EXISTS devices(id TEXT PRIMARY KEY, name TEXT, role TEXT,
              token TEXT UNIQUE, enabled INTEGER DEFAULT 1, seen REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS printers(id TEXT PRIMARY KEY, pc TEXT, name TEXT, available INTEGER);
            CREATE TABLE IF NOT EXISTS grants(tablet TEXT, printer TEXT, PRIMARY KEY(tablet,printer));
            CREATE TABLE IF NOT EXISTS printer_sharing(printer TEXT PRIMARY KEY, enabled INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS inventories(device TEXT PRIMARY KEY, received REAL, payload TEXT);
            CREATE TABLE IF NOT EXISTS inventory_requests(id TEXT PRIMARY KEY, device TEXT, created REAL, status TEXT);
            CREATE TABLE IF NOT EXISTS job_cancellations(id TEXT PRIMARY KEY, device TEXT);
            CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, tablet TEXT, printer TEXT, pc TEXT,
              name TEXT, mime TEXT, copies INTEGER, scale TEXT, paper TEXT, color TEXT,
              fingerprint TEXT, status TEXT, message TEXT, created REAL, updated REAL);
            ''')

    @contextmanager
    def db(self):
        db = sqlite3.connect(self.home / 'hub.sqlite3', timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def create_owner(self, email, password):
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email) or not 4 <= len(password) <= 200:
            raise ValueError('Usa un correo válido y contraseña de 4 a 200 caracteres.')
        salt = secrets.token_hex(16)
        with self.db() as db:
            if db.execute('SELECT 1 FROM owner').fetchone():
                raise ValueError('La cuenta ya está configurada.')
            db.execute('INSERT INTO owner VALUES(?,?,?)', (email.lower(), salt, password_hash(password, salt)))

    def change_password(self, current, new, keep_token):
        if not isinstance(new,str) or not 4 <= len(new) <= 200:
            raise ValueError('La contraseña debe tener de 4 a 200 caracteres.')
        with self.lock, self.db() as db:
            row = db.execute('SELECT * FROM owner').fetchone()
            if not row or not hmac.compare_digest(password_hash(current,row['salt']),row['password']):
                raise PermissionError('La contraseña actual no es correcta.')
            salt = secrets.token_hex(16)
            db.execute('UPDATE owner SET salt=?,password=?',(salt,password_hash(new,salt)))
            db.execute('DELETE FROM sessions WHERE token<>?',(digest(keep_token),))

    def logo(self):
        with self.db() as db:
            row = db.execute("SELECT value FROM branding WHERE key='logo'").fetchone()
            return bytes(row[0]) if row else None

    def set_logo(self, content):
        from PIL import Image, ImageOps, UnidentifiedImageError
        if not content or len(content) > 2*1024*1024:
            raise ValueError('Selecciona una imagen de hasta 2 MB.')
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height > 8_000_000:
                    raise ValueError('Usa PNG, JPG o WebP de hasta 8 megapíxeles.')
                normalized = ImageOps.exif_transpose(image).convert('RGBA')
                normalized.thumbnail((1024,1024))
                output = io.BytesIO()
                normalized.save(output,format='PNG')
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as e:
            raise ValueError('No se pudo leer la imagen del logo.') from e
        with self.lock, self.db() as db:
            db.execute("INSERT INTO branding VALUES('logo',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(output.getvalue(),))

    def reset_logo(self):
        with self.lock, self.db() as db:
            db.execute("DELETE FROM branding WHERE key='logo'")

    def icon(self):
        with self.db() as db:
            row = db.execute("SELECT value FROM branding WHERE key='icon'").fetchone()
            return bytes(row[0]) if row else None

    def set_icon(self, content):
        from PIL import Image, ImageOps, UnidentifiedImageError
        if not content or len(content)>2*1024*1024:
            raise ValueError('Selecciona un icono o imagen de hasta 2 MB.')
        try:
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ('ICO','PNG','JPEG','WEBP') or image.width*image.height>8_000_000:
                    raise ValueError('Usa ICO, PNG, JPG o WebP de hasta 8 megapíxeles.')
                image = ImageOps.exif_transpose(image).convert('RGBA')
                image.thumbnail((256,256))
                square = Image.new('RGBA',(256,256))
                square.alpha_composite(image,((256-image.width)//2,(256-image.height)//2))
                output = io.BytesIO()
                square.save(output,format='ICO',sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError) as e:
            raise ValueError('No se pudo leer la imagen del icono.') from e
        with self.lock, self.db() as db:
            db.execute("INSERT INTO branding VALUES('icon',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(output.getvalue(),))

    def reset_icon(self):
        with self.lock, self.db() as db:
            db.execute("DELETE FROM branding WHERE key='icon'")

    def owner_email(self):
        with self.db() as db:
            row = db.execute('SELECT email FROM owner').fetchone()
            return row[0] if row else None

    def public_url(self):
        with self.db() as db:
            row=db.execute("SELECT value FROM branding WHERE key='public_url'").fetchone()
            return str(row[0]) if row else ''

    def set_public_url(self, value):
        from network_config import normalize_url
        url=normalize_url(value) if value.strip() else ''
        with self.lock,self.db() as db:
            if url:db.execute("INSERT INTO branding VALUES('public_url',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(url,))
            else:db.execute("DELETE FROM branding WHERE key='public_url'")

    def registration_urls(self, port):
        from registration import server_urls
        return [self.public_url()] if self.public_url() else server_urls(port)

    def admin(self, token):
        with self.db() as db:
            return bool(db.execute('SELECT 1 FROM sessions WHERE token=? AND expires>?',
                                   (digest(token), time.time())).fetchone())

    def device(self, token, role=None):
        with self.db() as db:
            row = db.execute('SELECT * FROM devices WHERE token=? AND enabled=1', (digest(token),)).fetchone()
            if not row or (role and row['role'] != role):
                raise PermissionError('Dispositivo no autorizado o desactivado.')
            return dict(row)

    def enroll(self, email, code, name, role):
        if email.lower().strip() != self.owner_email() or role not in ('pc', 'tablet'):
            raise PermissionError('Correo o código incorrecto.')
        if not name.strip() or len(name) > 80:
            raise ValueError('Escribe un nombre de hasta 80 caracteres.')
        token, device_id = secrets.token_urlsafe(32), str(uuid.uuid4())
        with self.lock, self.db() as db:
            row = db.execute('SELECT * FROM codes WHERE code=? AND role=? AND expires>?',
                             (digest(code.strip().upper()), role, time.time())).fetchone()
            if not row:
                raise PermissionError('Código incorrecto, vencido o ya utilizado.')
            db.execute('DELETE FROM codes WHERE code=?', (row['code'],))
            db.execute('INSERT INTO devices(id,name,role,token) VALUES(?,?,?,?)',
                       (device_id, name.strip(), role, digest(token)))
        return {'token': token, 'id': device_id, 'email': self.owner_email()}

    def printer_list(self, tablet):
        with self.db() as db:
            return [dict(r) for r in db.execute('''SELECT p.id,p.name,d.name AS pc,
              CASE WHEN p.available=1 AND d.seen>? THEN 1 ELSE 0 END AS online
              FROM printers p JOIN devices d ON d.id=p.pc JOIN grants g ON g.printer=p.id
              LEFT JOIN printer_sharing ps ON ps.printer=p.id
              WHERE g.tablet=? AND d.enabled=1 AND COALESCE(ps.enabled,1)=1 ORDER BY d.name,p.name''', (time.time()-45, tablet))]

    def request_inventory(self, device):
        with self.lock,self.db() as db:
            if not db.execute('SELECT 1 FROM devices WHERE id=? AND enabled=1',(device,)).fetchone():
                raise ValueError('Equipo no disponible.')
            pending=db.execute("SELECT id FROM inventory_requests WHERE device=? AND status='pending'",(device,)).fetchone()
            if pending:return pending['id']
            request_id=str(uuid.uuid4())
            db.execute('INSERT INTO inventory_requests VALUES(?,?,?,?)',(request_id,device,time.time(),'pending'))
            return request_id

    def pending_inventory(self, device):
        with self.db() as db:
            row=db.execute("SELECT id FROM inventory_requests WHERE device=? AND status='pending' ORDER BY created LIMIT 1",(device,)).fetchone()
            return row['id'] if row else None

    def save_inventory(self, device, payload, request_id=None):
        if not isinstance(payload,dict) or payload.get('platform') not in ('Windows','Android'):
            raise ValueError('Inventario inválido.')
        if not isinstance(payload.get('summary'),dict) or not isinstance(payload.get('components',[]),list):
            raise ValueError('Resumen o componentes inválidos.')
        data=json.dumps(payload,ensure_ascii=False)
        if len(data.encode())>512*1024 or len(payload.get('components',[]))>500:
            raise ValueError('Inventario demasiado grande.')
        with self.lock,self.db() as db:
            if request_id:
                row=db.execute('SELECT 1 FROM inventory_requests WHERE id=? AND device=?',(request_id,device)).fetchone()
                if not row:raise PermissionError('Solicitud de auditoría ajena o inexistente.')
            db.execute('INSERT INTO inventories VALUES(?,?,?) ON CONFLICT(device) DO UPDATE SET received=excluded.received,payload=excluded.payload',(device,time.time(),data))
            if request_id:db.execute("UPDATE inventory_requests SET status='complete' WHERE id=?",(request_id,))

    def inventory_list(self):
        with self.db() as db:
            result=[]
            for row in db.execute('''SELECT d.id,d.name,d.role,d.enabled,i.received,i.payload,
                (SELECT count(*) FROM inventory_requests r WHERE r.device=d.id AND r.status='pending') AS pending
                FROM devices d LEFT JOIN inventories i ON i.device=d.id ORDER BY d.name'''):
                item=dict(row);payload=item.pop('payload');item['inventory']=json.loads(payload) if payload else None
                result.append(item)
            return result

    def heartbeat(self, pc, printers):
        if not isinstance(printers, list) or len(printers) > 200:
            raise ValueError('Lista de impresoras inválida.')
        with self.lock, self.db() as db:
            db.execute('UPDATE devices SET seen=? WHERE id=?', (time.time(), pc))
            db.execute('UPDATE printers SET available=0 WHERE pc=?', (pc,))
            for p in printers:
                name = str(p)[:256]
                pid = digest(pc + '\0' + name)[:32]
                db.execute('INSERT INTO printers VALUES(?,?,?,1) ON CONFLICT(id) DO UPDATE SET available=1',
                           (pid, pc, name))

    def register_pc(self, name, printers):
        if not isinstance(name,str) or not name.strip() or len(name)>80:
            raise ValueError('Escribe un nombre de PC de hasta 80 caracteres.')
        if not isinstance(printers,list) or len(printers)>200 or any(not isinstance(p,str) or not p or len(p)>256 for p in printers):
            raise ValueError('Lista de impresoras inválida.')
        device_id,token=str(uuid.uuid4()),secrets.token_urlsafe(32)
        with self.lock, self.db() as db:
            db.execute("INSERT INTO devices(id,name,role,token,seen) VALUES(?,?,'pc',?,?)",(device_id,name.strip(),digest(token),time.time()))
            for printer in set(printers):
                db.execute('INSERT INTO printers VALUES(?,?,?,1)',(digest(device_id+'\0'+printer)[:32],device_id,printer))
        return {'id':device_id,'token':token,'email':self.owner_email()}

    def enqueue(self, tablet, job_id, options, content, mime):
        if str(uuid.UUID(job_id)) != job_id:
            raise ValueError('Identificador inválido.')
        copies = int(options.get('copies', 1))
        if not 1 <= copies <= 20:
            raise ValueError('Elige entre 1 y 20 copias.')
        if mime not in ('application/pdf', 'image/png', 'image/jpeg'):
            raise ValueError('Solo se admite PDF, PNG o JPEG.')
        if not content or len(content) > MAX_FILE:
            raise ValueError('Archivo vacío o mayor de 25 MB.')
        signatures = {'application/pdf': b'%PDF-', 'image/png': b'\x89PNG\r\n\x1a\n', 'image/jpeg': b'\xff\xd8\xff'}
        if not content.startswith(signatures[mime]):
            raise ValueError('El contenido no corresponde al tipo de archivo.')
        scale, paper, color = (options.get(k, v) for k, v in [('scale', 'fit'), ('paper', 'driver'), ('color', 'color')])
        if scale not in ('fit', 'noscale') or paper not in ('driver', 'A4', 'letter') or color not in ('color', 'monochrome'):
            raise ValueError('Opciones de impresión inválidas.')
        pid = options['printer']
        fingerprint = hashlib.sha256(content + json.dumps([pid,copies,scale,paper,color,mime]).encode()).hexdigest()
        now = time.time()
        with self.lock, self.db() as db:
            cancelled = db.execute('SELECT device FROM job_cancellations WHERE id=?',(job_id,)).fetchone()
            if cancelled:
                if cancelled['device'] != tablet:
                    raise PermissionError('Identificador no disponible.')
                return {'id':job_id,'status':'cancelled','message':'Cancelado antes de entregarlo a la PC.'}
            old = db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
            if old:
                if old['tablet'] != tablet or old['fingerprint'] != fingerprint:
                    raise ValueError('El identificador ya pertenece a otro trabajo.')
                return dict(old)
            printer = db.execute('''SELECT p.* FROM printers p JOIN grants g ON g.printer=p.id
              JOIN devices d ON d.id=p.pc LEFT JOIN printer_sharing ps ON ps.printer=p.id
              WHERE p.id=? AND g.tablet=? AND d.enabled=1 AND COALESCE(ps.enabled,1)=1''', (pid,tablet)).fetchone()
            if not printer:
                raise PermissionError('Esta impresora no está compartida con tu tablet.')
            if db.execute("SELECT count(*) FROM jobs WHERE status IN ('queued','claimed')").fetchone()[0] >= MAX_PENDING:
                raise ValueError('Cola llena. Espera antes de enviar más trabajos.')
            if db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 10000:
                db.execute("DELETE FROM jobs WHERE status IN ('submitted','error','unknown') AND updated<?", (now-30*86400,))
                if db.execute('SELECT count(*) FROM jobs').fetchone()[0] >= 10000:
                    raise ValueError('Historial lleno; contacta al administrador.')
            temp = self.files / (job_id + '.tmp')
            temp.write_bytes(content)
            os.replace(temp, self.files / job_id)
            try:
                db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                  (job_id,tablet,pid,printer['pc'],str(options.get('name','Documento'))[:160],mime,
                   copies,scale,paper,color,fingerprint,'queued','En espera de la PC',now,now))
            except Exception:
                (self.files / job_id).unlink(missing_ok=True)
                raise
            return dict(db.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone())

    def cancel_client_job(self, device, job_id):
        if str(uuid.UUID(job_id)) != job_id:
            raise ValueError('Identificador inválido.')
        with self.lock, self.db() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=?',(job_id,)).fetchone()
            tombstone=db.execute('SELECT device FROM job_cancellations WHERE id=?',(job_id,)).fetchone()
            if (row and row['tablet']!=device) or (tombstone and tombstone['device']!=device):
                raise PermissionError('Trabajo no disponible para este equipo.')
            if row and row['status']!='queued' and not tombstone:
                return {'cancelled':False,'status':row['status'],'message':'Ya entregado a la PC. Revisa la cola de Windows.'}
            if not tombstone:
                if db.execute('SELECT count(*) FROM job_cancellations').fetchone()[0]>=10000:
                    raise ValueError('Límite de cancelaciones alcanzado. Contacta al administrador.')
                db.execute('INSERT INTO job_cancellations VALUES(?,?)',(job_id,device))
            if row and row['status']=='queued':
                db.execute("UPDATE jobs SET status='error',message='Cancelado por el remitente',updated=? WHERE id=?",(time.time(),job_id))
                (self.files/job_id).unlink(missing_ok=True)
            return {'cancelled':True,'status':'cancelled'}

    def client_job(self, device, job_id):
        with self.db() as db:
            row=db.execute('SELECT * FROM jobs WHERE id=? AND tablet=?',(job_id,device)).fetchone()
            cancelled=db.execute('SELECT 1 FROM job_cancellations WHERE id=? AND device=?',(job_id,device)).fetchone()
            if cancelled:return {'id':job_id,'status':'cancelled'}
            if not row:raise PermissionError('Trabajo no disponible para este equipo.')
            return dict(row)

    def claim(self, pc):
        with self.lock, self.db() as db:
            # Revoked permissions also stop jobs that have not yet been handed to a PC.
            revoked = db.execute('''SELECT j.id FROM jobs j WHERE j.pc=? AND j.status='queued' AND
              NOT EXISTS(SELECT 1 FROM grants g JOIN devices t ON t.id=g.tablet
                LEFT JOIN printer_sharing ps ON ps.printer=g.printer
                WHERE g.tablet=j.tablet AND g.printer=j.printer AND t.enabled=1 AND COALESCE(ps.enabled,1)=1)''', (pc,)).fetchall()
            for row in revoked:
                db.execute("UPDATE jobs SET status='error',message='Permiso retirado',updated=? WHERE id=?", (time.time(),row['id']))
                (self.files / row['id']).unlink(missing_ok=True)
            row = db.execute("SELECT j.*,p.name AS printer_name FROM jobs j JOIN printers p ON p.id=j.printer WHERE j.pc=? AND j.status='queued' ORDER BY j.created LIMIT 1", (pc,)).fetchone()
            if not row:
                return None
            db.execute("UPDATE jobs SET status='claimed',message='Entregado a la PC; pendiente de confirmación',updated=? WHERE id=?", (time.time(),row['id']))
            return dict(row)

    def finish(self, pc, job_id, status, message):
        if status not in STATES:
            raise ValueError('Estado inválido.')
        with self.lock, self.db() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=? AND pc=?', (job_id,pc)).fetchone()
            if not row or row['status'] not in ('claimed', status):
                raise ValueError('Trabajo no disponible para esta PC.')
            db.execute('UPDATE jobs SET status=?,message=?,updated=? WHERE id=?', (status,message[:500],time.time(),job_id))
            (self.files / job_id).unlink(missing_ok=True)

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.0'
    server_version = 'PRINTER-TAB/0.2'

    def setup(self):
        super().setup()
        self.connection.settimeout(30)

    @property
    def service(self):
        return self.server.service

    def log_message(self, *_):
        pass

    def respond(self, value, status=200, mime='application/json'):
        data = json.dumps(value, ensure_ascii=False).encode() if mime == 'application/json' else value
        self.send_response(status)
        self.send_header('Content-Type', mime + ('; charset=utf-8' if mime.startswith('text/') else ''))
        self.send_header('Content-Length', str(len(data)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(data)

    def read_body(self, limit):
        if self.headers.get('Transfer-Encoding'):
            raise ValueError('Se requiere Content-Length.')
        length = int(self.headers.get('Content-Length', '0'))
        if not 0 < length <= limit:
            raise ValueError('Tamaño de solicitud inválido.')
        content = self.rfile.read(length)
        if len(content) != length:
            raise ValueError('Transferencia incompleta.')
        return content

    def body_json(self, limit=128*1024):
        value = json.loads(self.read_body(limit))
        if not isinstance(value, dict):
            raise ValueError('Objeto JSON requerido.')
        return value

    def token(self):
        value = self.headers.get('Authorization','')
        return value[7:] if value.startswith('Bearer ') else ''

    def do_GET(self):
        self.dispatch('GET')

    def do_POST(self):
        self.dispatch('POST')

    def dispatch(self, method):
        try:
            self.route(method, urllib.parse.urlsplit(self.path).path)
        except PermissionError as e:
            if urllib.parse.urlsplit(self.path).path in ('/api/login','/api/enroll'):
                self.server.auth_failure(self.client_address[0])
            self.respond({'error':str(e)},403)
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            self.respond({'error': str(e)},400)
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        except Exception:
            self.respond({'error':'Error interno; consulta al administrador.'},500)

    def route(self, method, path):
        s = self.service
        if method=='POST' and path in ('/api/login','/api/enroll') and not self.server.auth_allowed(self.client_address[0]):
            # Consume a bounded auth body before closing. Unread request bytes can
            # make Windows reset the connection before the client receives HTTP 429.
            try:length=int(self.headers.get('Content-Length','0'))
            except ValueError:length=0
            if 0<length<=16*1024 and not self.headers.get('Transfer-Encoding'):
                self.read_body(16*1024)
            self.respond({'error':'Demasiados intentos incorrectos. Espera un minuto antes de volver a intentar.'},429)
            return
        if method=='GET' and path=='/api/health':
            self.respond({'service':'PRINTER-TAB','version':'0.4.1','ready':bool(s.owner_email())})
            return
        if method=='GET' and path=='/api/admin/backup.zip':
            if not s.admin(self.token()):raise PermissionError('Se requiere sesión administradora.')
            from backup_config import server_backup
            with s.lock:content=server_backup(s.home)
            self.respond(content,mime='application/zip')
            return
        if method == 'GET' and path == '/branding/logo':
            logo = s.logo()
            self.respond(logo if logo else (Path(__file__).parent/'default-logo.svg').read_bytes(),mime='image/png' if logo else 'image/svg+xml')
            return
        if method == 'GET' and path in ('/', '/admin.js'):
            name = 'admin.html' if path == '/' else 'admin.js'
            self.respond((Path(__file__).parent / name).read_bytes(), mime='text/html' if name.endswith('html') else 'text/javascript')
            return
        if method == 'POST' and path == '/api/login':
            # Bound concurrent requests and constant work for unknown accounts.
            b = self.body_json()
            with s.db() as db:
                row = db.execute('SELECT * FROM owner').fetchone()
                valid = row and hmac.compare_digest(password_hash(str(b.get('password',''))[:500],row['salt']),row['password'])
                if not valid or str(b.get('email','')).lower().strip() != row['email']:
                    time.sleep(1)
                    raise PermissionError('Correo o contraseña incorrectos.')
                token = secrets.token_urlsafe(32)
                db.execute('DELETE FROM sessions WHERE expires<?', (time.time(),))
                db.execute('INSERT INTO sessions VALUES(?,?)', (digest(token),time.time()+8*3600))
            self.respond({'token':token})
            return
        if method == 'POST' and path == '/api/enroll':
            b = self.body_json()
            self.respond(s.enroll(b['email'],b['code'],b['name'],b['role']))
            return
        if path.startswith('/api/admin/'):
            if not s.admin(self.token()):
                raise PermissionError('Inicia sesión como administrador.')
            if method=='GET' and path=='/api/admin/inventory':
                self.respond({'devices':s.inventory_list()})
                return
            if method=='GET' and path=='/api/admin/inventory.xlsx':
                from inventory import export_xlsx
                self.respond(export_xlsx(s.inventory_list()),mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                return
            if method=='POST' and path=='/api/admin/inventory/request':
                self.respond({'id':s.request_inventory(self.body_json()['device'])})
                return
            if method=='POST' and path=='/api/admin/service-url':
                s.set_public_url(self.body_json()['url'])
                self.respond({'ok':True})
                return
            if method == 'POST' and path == '/api/admin/register-pc':
                b=self.body_json()
                self.respond(s.register_pc(b['name'],b['printers']),201)
                return
            if method == 'POST' and path == '/api/admin/logo':
                s.set_logo(self.read_body(2*1024*1024))
                self.respond({'ok':True})
                return
            if method == 'POST' and path == '/api/admin/logo/reset':
                self.body_json()
                s.reset_logo()
                self.respond({'ok':True})
                return
            if method == 'POST' and path == '/api/admin/icon':
                s.set_icon(self.read_body(2*1024*1024))
                self.respond({'ok':True})
                return
            if method == 'POST' and path == '/api/admin/icon/reset':
                self.body_json()
                s.reset_icon()
                self.respond({'ok':True})
                return
            if method == 'POST' and path == '/api/admin/password':
                b = self.body_json()
                s.change_password(b['current'],b['password'],self.token())
                self.respond({'ok':True})
                return
            if method == 'GET' and path.endswith('/state'):
                with s.db() as db:
                    self.respond({'email':s.owner_email(),'service_url':s.public_url(),
                       'devices':[dict(r) for r in db.execute('SELECT id,name,role,enabled,seen FROM devices ORDER BY role,name')],
                       'printers':[dict(r) for r in db.execute('SELECT p.*,COALESCE(ps.enabled,1) AS shared FROM printers p LEFT JOIN printer_sharing ps ON ps.printer=p.id ORDER BY p.name')],
                       'grants':[dict(r) for r in db.execute('SELECT * FROM grants')],
                       'jobs':[dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 100')]})
                return
            if method == 'POST':
                b = self.body_json()
                with s.lock, s.db() as db:
                    if path.endswith('/code'):
                        if b['role'] not in ('pc','tablet'):
                            raise ValueError('Tipo inválido.')
                        code = secrets.token_hex(5).upper()
                        db.execute('DELETE FROM codes WHERE expires<?', (time.time(),))
                        db.execute('INSERT INTO codes VALUES(?,?,?)',(digest(code),b['role'],time.time()+900))
                        from registration import make_registration
                        registration=make_registration(s.owner_email(),code,b['role'],s.registration_urls(self.server.server_port))
                        db.commit()
                        self.respond({'code':code,'registration':registration,'minutes':15})
                    elif path.endswith('/device'):
                        db.execute('UPDATE devices SET enabled=? WHERE id=?',(1 if b['enabled'] else 0,b['id']))
                        db.commit()
                        self.respond({'ok':True})
                    elif path.endswith('/printer-sharing'):
                        if not db.execute('SELECT 1 FROM printers WHERE id=?',(b['printer'],)).fetchone():
                            raise ValueError('Impresora inválida.')
                        db.execute('INSERT INTO printer_sharing VALUES(?,?) ON CONFLICT(printer) DO UPDATE SET enabled=excluded.enabled',(b['printer'],1 if b['enabled'] else 0))
                        db.commit()
                        self.respond({'ok':True})
                    elif path.endswith('/grants'):
                        if not isinstance(b['printers'],list) or len(b['printers']) > 200:
                            raise ValueError('Selección inválida.')
                        if not db.execute("SELECT 1 FROM devices WHERE id=? AND role IN ('pc','tablet')",(b['tablet'],)).fetchone():
                            raise ValueError('Equipo inválido.')
                        for pid in b['printers']:
                            if not db.execute('SELECT 1 FROM printers WHERE id=?',(pid,)).fetchone():
                                raise ValueError('Impresora inválida.')
                        db.execute('DELETE FROM grants WHERE tablet=?',(b['tablet'],))
                        db.executemany('INSERT INTO grants VALUES(?,?)',[(b['tablet'],p) for p in set(b['printers'])])
                        db.commit()
                        self.respond({'ok':True})
                    else:
                        self.respond({'error':'Ruta inexistente'},404)
                return
        if path.startswith('/api/pc/'):
            pc = s.device(self.token(),'pc')['id']
            if method == 'GET' and path == '/api/pc/branding':
                logo,icon = s.logo(),s.icon()
                self.respond({'logo':base64.b64encode(logo).decode() if logo else None,
                              'icon':base64.b64encode(icon).decode() if icon else None})
                return
            if method == 'POST' and path.endswith('/heartbeat'):
                s.heartbeat(pc,self.body_json()['printers'])
                self.respond({'ok':True,'inventory_request':s.pending_inventory(pc)})
                return
            if method=='POST' and path=='/api/pc/inventory':
                b=self.body_json(600*1024)
                s.save_inventory(pc,b['inventory'],b.get('request'))
                self.respond({'ok':True})
                return
            if method == 'POST' and path.endswith('/claim'):
                self.read_body(1024)
                self.respond({'job':s.claim(pc)})
                return
            if method == 'POST' and path.endswith('/finish'):
                b = self.body_json()
                s.finish(pc,b['id'],b['status'],b['message'])
                self.respond({'ok':True})
                return
            if method == 'GET' and path.startswith('/api/pc/file/'):
                job_id = path.rsplit('/',1)[-1]
                with s.db() as db:
                    row = db.execute("SELECT 1 FROM jobs WHERE id=? AND pc=? AND status='claimed'",(job_id,pc)).fetchone()
                if not row:
                    raise PermissionError('Archivo no disponible.')
                self.respond((s.files / job_id).read_bytes(),mime='application/octet-stream')
                return
        if path.startswith('/api/tablet/') or path.startswith('/api/client/'):
            tablet = s.device(self.token(),'tablet' if path.startswith('/api/tablet/') else None)['id']
            if method=='POST' and path=='/api/client/heartbeat':
                self.body_json()
                with s.db() as db:db.execute('UPDATE devices SET seen=? WHERE id=?',(time.time(),tablet))
                self.respond({'ok':True,'inventory_request':s.pending_inventory(tablet)})
                return
            if method=='POST' and path=='/api/client/inventory':
                b=self.body_json(600*1024)
                s.save_inventory(tablet,b['inventory'],b.get('request'))
                self.respond({'ok':True})
                return
            if method == 'GET' and path.endswith('/printers'):
                self.respond({'printers':s.printer_list(tablet)})
                return
            if method == 'GET' and path.endswith('/jobs'):
                with s.db() as db:
                    self.respond({'jobs':[dict(r) for r in db.execute('SELECT * FROM jobs WHERE tablet=? ORDER BY created DESC LIMIT 30',(tablet,))]})
                return
            if path.startswith('/api/client/jobs/') and path.endswith('/cancel') and method=='POST':
                self.body_json()
                self.respond(s.cancel_client_job(tablet,path.split('/')[-2]))
                return
            if path.startswith('/api/client/jobs/') and method=='GET':
                self.respond(s.client_job(tablet,path.rsplit('/',1)[-1]))
                return
            if method == 'POST' and (path.startswith('/api/tablet/jobs/') or path.startswith('/api/client/jobs/')):
                job_id = path.rsplit('/',1)[-1]
                try:
                    options = json.loads(base64.b64decode(self.headers['X-Print-Options'],validate=True))
                except Exception:
                    raise ValueError('Opciones inválidas.')
                self.respond(s.enqueue(tablet,job_id,options,self.read_body(MAX_FILE),self.headers.get('Content-Type','')),201)
                return
        self.respond({'error':'Ruta inexistente'},404)

class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, service):
        self.service = service
        self.slots = threading.BoundedSemaphore(16)
        self.auth_lock=threading.Lock()
        self.auth_failures={}
        super().__init__(address,Handler)

    def auth_allowed(self, address):
        with self.auth_lock:
            if len(self.auth_failures)>1024:self.auth_failures.clear()
            recent=[t for t in self.auth_failures.get(address,[]) if t>time.time()-60]
            self.auth_failures[address]=recent
            return len(recent)<20

    def auth_failure(self, address):
        with self.auth_lock:
            if len(self.auth_failures)>1024:self.auth_failures.clear()
            self.auth_failures.setdefault(address,[]).append(time.time())

    def process_request(self, request, address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request,address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request,address)
        finally:
            self.slots.release()

def run(home, port=8765, interactive=True):
    s = Service(home)
    if not s.owner_email():
        if not interactive:
            raise ValueError('Primero crea la cuenta desde el panel PRINTER-TAB.')
        print('\nCrear cuenta local de administrador (el correo no envía mensajes).')
        email = input('Correo: ').strip()
        password = getpass.getpass('Contraseña (mínimo 4 caracteres): ')
        if password != getpass.getpass('Repite la contraseña: '):
            raise ValueError('Las contraseñas no coinciden.')
        s.create_owner(email,password)
    server = Server(('0.0.0.0',port),s)
    print(f'\nConsola administrador: http://localhost:{port}')
    print(f'Cuenta: {s.owner_email()}')
    print(f'PRINTER-TAB · Servidor iniciado. Puerto TCP {port}.')
    print('En otras PCs y tablets usa la IP LAN de ESTA PC, no localhost.')
    try:
        ips = sorted({a[4][0] for a in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET)})
        for ip in ips:
            print(f'  Dirección candidata: http://{ip}:{port}')
    except OSError:
        pass
    if interactive:
        import webbrowser
        webbrowser.open(f'http://localhost:{port}')
    server.serve_forever()

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--home',default=str(Path(os.environ.get('LOCALAPPDATA','.')) / 'JADPrint' / 'hub'))
    parser.add_argument('--port',type=int,default=8765)
    args = parser.parse_args()
    run(args.home,args.port)
