"""Outbound-only Windows agent. Claims are never automatically printed twice."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.error
import urllib.request

def api(config, path, body=None, binary=False, timeout=35):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(config['url'] + '/api/' + path, data=data,
          headers={'Authorization':'Bearer '+config.get('token',''), 'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            result = response.read(26*1024*1024)
            return result if binary else json.loads(result)
    except urllib.error.HTTPError as e:
        try:
            detail = json.loads(e.read())['error']
        except Exception:
            detail = 'HTTP '+str(e.code)
        raise RuntimeError(detail) from None

def atomic_json(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value),encoding='utf-8')
    os.replace(temp,path)

def printers():
    # Constant script; no names or user input are interpolated into a shell.
    script = "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; @(Get-Printer -ErrorAction Stop | Select-Object -ExpandProperty Name) | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
       capture_output=True,timeout=30,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:
        raise RuntimeError('No se pudieron consultar las impresoras de Windows.')
    value = result.stdout.decode('utf-8-sig').strip()
    data = json.loads(value) if value else []
    return [data] if isinstance(data,str) else data or []

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
    while True:
        try:
            if marker.exists():
                report = json.loads(marker.read_text(encoding='utf-8'))
                api(config,'pc/finish',report)
                marker.unlink()
            if time.time()-last_heartbeat > 15:
                names = printers()
                api(config,'pc/heartbeat',{'printers':names})
                last_heartbeat = time.time()
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
