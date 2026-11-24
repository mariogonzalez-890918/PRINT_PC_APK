"""Outbound-only Windows agent. Claims are never automatically printed twice."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request
import uuid
import sys
from concurrent.futures import ThreadPoolExecutor
from printer_monitor import PrinterMonitor

class ApiFailure(RuntimeError):
    def __init__(self,status,message):super().__init__(message);self.status=status

def api(config, path, body=None, binary=False, timeout=35):
    data = json.dumps(body).encode() if body is not None else None
    try:
        from transport import request,learn
        retry_safe=body is None or path in ('pc/heartbeat','client/heartbeat','pc/finish','pc/inventory','client/inventory')
        result=request(config,path,data,{'Authorization':'Bearer '+config.get('token',''), 'Content-Type':'application/json'},timeout,retry_safe)
        if binary:return result
        result=json.loads(result);learn(config,result);return result
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read())['error']
        except Exception:
            detail = 'HTTP '+str(e.code)
        raise ApiFailure(e.code,detail) from None

def atomic_json(path, value):
    temp = path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        temp.write_text(json.dumps(value),encoding='utf-8')
        os.replace(temp,path)
    finally:temp.unlink(missing_ok=True)

def printers(include_managed=False):
    try:
        result=subprocess.run([sys.executable,str(Path(__file__).with_name('windows_printers.py'))],
            capture_output=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    except subprocess.TimeoutExpired:
        raise RuntimeError('Windows no respondió al consultar sus impresoras. El agente seguirá conectado. Revisa el servicio Cola de impresión y las conexiones de impresoras en esta PC; luego reintenta Compartir impresoras.') from None
    try:data=json.loads(result.stdout.decode('utf-8-sig'))
    except (ValueError,UnicodeError):raise RuntimeError('Windows no devolvió una lista válida de impresoras. Revisa el servicio Cola de impresión.') from None
    if result.returncode or 'error' in data:
        raise RuntimeError('No se pudieron consultar las impresoras locales. Revisa el servicio Cola de impresión. '+str(data.get('error',''))[:250])
    names=data.get('printers')
    if not isinstance(names,list) or len(names)>2000 or any(not isinstance(n,str) or not n.strip() for n in names):
        raise RuntimeError('Windows devolvió una lista de impresoras inválida.')
    result=names if include_managed else [name for name in names if not name.startswith('PRINTER-TAB - ')]
    if not include_managed and len(result)>200:raise RuntimeError('Windows reportó más de 200 impresoras publicables.')
    return result

def execute_print(config, job, home):
    work = home / 'work'
    work.mkdir(exist_ok=True)
    source = work / (job['id'] + ('.pdf' if job['mime']=='application/pdf' else '.img'))
    pdf = work / (job['id']+'.pdf')
    try:
        payload = api(config,'pc/file/'+job['id'],binary=True)
        source.write_bytes(payload)
        if job['printer_name'] not in printers():
            raise ValueError('La impresora ya no está instalada en esta PC.')
        if job['mime'] != 'application/pdf':
            from PIL import Image, ImageOps
            Image.MAX_IMAGE_PIXELS = 25_000_000
            with Image.open(source) as image:
                if image.width*image.height > 25_000_000:
                    raise ValueError('La imagen excede 25 megapíxeles.')
                ImageOps.exif_transpose(image).convert('RGB').save(pdf,'PDF',resolution=150)
        engine = Path(__file__).resolve().parent.parent / 'engine' / 'SumatraPDF.exe'
        if not engine.is_file():
            raise ValueError('Falta el motor de impresión. Reinstala PRINTER-TAB.')
        settings = [str(job['copies'])+'x',job['scale'],job['color']]
        if job['paper'] != 'driver':
            settings.append('paper='+job['paper'])
        try:
            result = subprocess.run([str(engine),'-print-to',job['printer_name'],'-print-settings',
                ','.join(settings),'-silent',str(pdf)],timeout=180,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        except subprocess.TimeoutExpired:
            return 'unknown','El controlador no respondió a tiempo. Revisa la cola de Windows antes de reenviar.'
        if result.returncode:
            return 'error',f'El motor devolvió error {result.returncode}. Revisa el controlador y la cola de Windows antes de reenviar.'
        return 'submitted','Enviado al controlador de Windows; no confirma salida física del papel.'
    finally:
        source.unlink(missing_ok=True)
        pdf.unlink(missing_ok=True)

def run(home, interactive=True):
    home = Path(home)
    home.mkdir(parents=True,exist_ok=True)
    path = home / 'agent.json'
    if path.exists():
        config = json.loads(path.read_text(encoding='utf-8'))
    else:
        if not interactive:
            raise ValueError('Primero vincula la PC desde el panel PRINTER-TAB.')
        print('\nVincular esta PC. Genera un código de PC en la consola administrador.')
        url = input('Servidor (ejemplo http://192.168.0.10:8765): ').strip().rstrip('/')
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.path or parsed.username:
            raise ValueError('Dirección del servidor inválida.')
        config = {'url':url}
        result = api(config,'enroll',{'email':input('Correo de la cuenta: ').strip(),
            'code':input('Código de PC: ').strip(), 'name':input('Nombre (PC1, Caja, Almacén...): ').strip(),'role':'pc'})
        config.update(result)
        atomic_json(path,config)
    # Per-user single instance avoids two workers on this PC.
    import ctypes
    ctypes.windll.kernel32.CreateMutexW.restype = ctypes.c_void_p
    mutex = ctypes.windll.kernel32.CreateMutexW(None,False,'Local\\JADPrintAgent-'+hashlib.sha256(str(home).encode()).hexdigest()[:16])
    if ctypes.windll.kernel32.GetLastError() == 183:
        raise RuntimeError('El agente ya está abierto para este usuario.')
    print('\nAgente conectado. Mantén esta ventana abierta para recibir trabajos.')
    print('Servidor:',config['url'],'\nCuenta:',config['email'])
    marker = home / 'inflight.json'
    last_heartbeat = 0
    audit_pool=ThreadPoolExecutor(max_workers=1)
    audit_future=None
    audit_request=None
    audit_schema=home/'inventory-schema.json'
    try:auto_audit_needed=json.loads(audit_schema.read_text(encoding='utf-8')).get('schema',0)<2
    except (OSError,ValueError):auto_audit_needed=True
    next_auto_audit=0
    printer_monitor=PrinterMonitor(printers)
    windows_server=None
    try:
        from windows_bridge import start
        windows_server,windows_broker=start(home,config)
        print('Impresoras Windows: puente activo en 127.0.0.1:'+str(windows_server.server_port)+'. Usa Impresoras en Windows para instalarlas.',flush=True)
    except Exception as error:print('No se pudo iniciar el puente Windows:',str(error)[:300],flush=True)
    while True:
        try:
            if marker.exists():
                report = json.loads(marker.read_text(encoding='utf-8'))
                api(config,'pc/finish',report)
                marker.unlink()
            if time.time()-last_heartbeat > 15:
                names,warning=printer_monitor.poll()
                heartbeat={'printer_warning':warning}
                if names is not None:heartbeat['printers']=names
                response=api(config,'pc/heartbeat',heartbeat)
                if warning:print('Aviso de impresoras locales:',warning,flush=True)
                atomic_json(path,config)
                requested=response.get('inventory_request')
                if audit_future is None and (requested or (auto_audit_needed and time.time()>=next_auto_audit)):
                    from inventory import collect_windows
                    audit_request=requested
                    audit_future=audit_pool.submit(collect_windows)
                    next_auto_audit=time.time()+300
                last_heartbeat = time.time()
            if audit_future is not None and audit_future.done():
                try:snapshot=audit_future.result()
                except Exception as e:snapshot={'platform':'Windows','summary':{},'components':[],'errors':[str(e)[:500]]}
                api(config,'pc/inventory',{'request':audit_request,'inventory':snapshot})
                if snapshot.get('schema_version',0)>=2 and snapshot.get('summary',{}).get('os'):
                    atomic_json(audit_schema,{'schema':2});auto_audit_needed=False
                print('Auditoría de componentes enviada al administrador.',flush=True)
                audit_future=None;audit_request=None
            job = api(config,'pc/claim',{})['job']
            if job:
                report = {'id':job['id'],'status':'unknown',
                   'message':'El agente se interrumpió. Revisa la cola de Windows antes de reenviar.'}
                # Persist BEFORE touching the print engine; after a crash only report, never reprint.
                atomic_json(marker,report)
                try:
                    status,message = execute_print(config,job,home)
                except Exception as e:
                    status,message = 'error',str(e)[:400]
                report.update(status=status,message=message)
                atomic_json(marker,report)
                print(time.strftime('%H:%M:%S'),job['name'],message,flush=True)
            else:
                time.sleep(3)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print('Conexión pendiente:',str(e)[:250],flush=True)
            time.sleep(10)
    audit_pool.shutdown(wait=False,cancel_futures=True)
    printer_monitor.close()
    if windows_server is not None:windows_broker.stop.set();windows_server.shutdown();windows_server.server_close()
