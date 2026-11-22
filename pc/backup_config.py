"""Portable server backup. Only fixed members are read; ZIP paths are never extracted."""
import hashlib
from contextlib import closing
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import zipfile
from reset_config import idle_guard

MAX_DATABASE=128*1024*1024

def server_backup(home):
    home=Path(home)
    source=home/'hub.sqlite3'
    if not source.is_file():raise ValueError('No hay un servidor configurado para respaldar.')
    with tempfile.TemporaryDirectory(prefix='printer-tab-backup-') as folder:
        target=Path(folder)/'snapshot.sqlite3'
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as original,closing(sqlite3.connect(target)) as snapshot:
            original.backup(snapshot)
        database=target.read_bytes()
    if len(database)>MAX_DATABASE:raise ValueError('El respaldo excede el límite de 128 MB.')
    manifest={'service':'PRINTER-TAB','format':1,'sha256':hashlib.sha256(database).hexdigest(),'scope':'server'}
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('manifest.json',json.dumps(manifest))
        archive.writestr('hub.sqlite3',database)
    return output.getvalue()

def read_backup(content):
    if len(content)>MAX_DATABASE:raise ValueError('Archivo de respaldo demasiado grande.')
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        if sorted(archive.namelist())!=['hub.sqlite3','manifest.json']:
            raise ValueError('El respaldo contiene archivos inesperados.')
        if archive.getinfo('hub.sqlite3').file_size>MAX_DATABASE or archive.getinfo('manifest.json').file_size>4096:
            raise ValueError('Contenido del respaldo demasiado grande.')
        manifest=json.loads(archive.read('manifest.json'));database=archive.read('hub.sqlite3')
    if manifest.get('service')!='PRINTER-TAB' or manifest.get('format')!=1 or manifest.get('sha256')!=hashlib.sha256(database).hexdigest():
        raise ValueError('El respaldo no es válido o está dañado.')
    if not database.startswith(b'SQLite format 3\x00'):raise ValueError('Base de datos inválida.')
    return database

def export_file(home,path):
    home=Path(home).absolute();target=Path(path).absolute()
    if target==home or home in target.parents:raise ValueError('Guarda el respaldo fuera de la carpeta de datos PRINTER-TAB.')
    data=server_backup(home/'hub');read_backup(data)
    # Exclusive create: never overwrite an existing backup silently.
    with target.open('xb') as out:out.write(data);out.flush();os.fsync(out.fileno())
    if target.read_bytes()!=data:raise ValueError('No se pudo verificar el respaldo guardado.')
    return {'path':str(target),'sha256':hashlib.sha256(data).hexdigest()}

def restore_file(home,path,confirmation):
    if confirmation!='RESTAURAR':raise ValueError('Escribe RESTAURAR para confirmar.')
    home=Path(home).absolute()
    if home!=(Path(os.environ['LOCALAPPDATA'])/'JADPrint').absolute() or home.is_symlink() or home.is_junction():raise ValueError('Ruta de datos inválida.')
    if (home/'hub').exists() or (home/'agent').exists() or (home/'sender').exists():
        raise ValueError('Restablece primero la configuración local. La restauración requiere un equipo limpio.')
    source=Path(path)
    if source.stat().st_size>MAX_DATABASE:raise ValueError('Respaldo demasiado grande.')
    data=read_backup(source.read_bytes())
    with idle_guard(home),tempfile.TemporaryDirectory(prefix='printer-tab-restore-',dir=home.parent) as folder:
        staging=Path(folder)/'hub';staging.mkdir();database=staging/'hub.sqlite3';database.write_bytes(data)
        with closing(sqlite3.connect(database)) as db,db:
            # Reject views/triggers and unrecognized database structures before modifying.
            if db.execute("SELECT count(*) FROM sqlite_master WHERE type IN ('view','trigger')").fetchone()[0]:raise ValueError('Estructura de respaldo no admitida.')
            if db.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Base de datos dañada.')
            required={'owner','sessions','codes','devices','grants','jobs','inventories','branding'}
            if not required<={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                raise ValueError('El respaldo no contiene una cuenta PRINTER-TAB válida.')
            db.execute('DELETE FROM sessions');db.execute('DELETE FROM codes');db.execute('DELETE FROM grants')
            db.execute('UPDATE devices SET enabled=0')
            db.execute("DELETE FROM branding WHERE key='public_url'")
            db.execute("UPDATE jobs SET status='unknown',message='Migración: trabajo detenido. Revisar cola de origen antes de reenviar.' WHERE status IN ('queued','claimed')")
            if 'inventory_requests' in {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}:
                db.execute("UPDATE inventory_requests SET status='complete' WHERE status='pending'")
        (staging/'queue').mkdir();home.mkdir(exist_ok=True)
        staging.rename(home/'hub')
    return {'ok':True,'message':'Cuenta e inventarios restaurados. Configura la dirección VPN, genera códigos nuevos y vuelve a asignar impresoras.'}

def clear_origin(home,path,confirmation):
    if confirmation!='BORRAR ORIGEN':raise ValueError('Escribe BORRAR ORIGEN para confirmar.')
    home=Path(home).absolute()
    if home!=(Path(os.environ['LOCALAPPDATA'])/'JADPrint').absolute() or home.is_symlink() or home.is_junction():raise ValueError('Ruta de datos inválida.')
    target=Path(path).absolute().resolve()
    if home.resolve() in target.parents or target==home.resolve():raise ValueError('El respaldo debe quedar fuera de los datos de origen.')
    # Verify the supplied backup matches the current account data before any removal.
    source=home/'hub'/'hub.sqlite3'
    if target.stat().st_size>MAX_DATABASE:raise ValueError('Respaldo demasiado grande.')
    data=read_backup(target.read_bytes())
    with idle_guard(home),tempfile.TemporaryDirectory(prefix='printer-tab-verify-') as folder:
        check=Path(folder)/'check.sqlite3';check.write_bytes(data)
        with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as a,closing(sqlite3.connect(check)) as b:
            if a.execute('SELECT * FROM owner').fetchall()!=b.execute('SELECT * FROM owner').fetchall():raise ValueError('El respaldo no corresponde a la cuenta de origen.')
            # Backup must be current: every table must have the same content.
            tables=[r[0] for r in a.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
            for table in tables:
                name='"'+table.replace('"','""')+'"'
                if sorted(map(repr,a.execute('SELECT * FROM '+name)))!=sorted(map(repr,b.execute('SELECT * FROM '+name))):raise ValueError('Hay cambios posteriores al respaldo. Exporta uno nuevo con los servicios detenidos.')
        paths=[home/n for n in ('hub','agent','sender','branding') if (home/n).exists()]
        for item in paths:
            if item.is_symlink() or item.is_junction() or item.resolve().parent!=home.resolve():raise ValueError('Ruta enlazada no admitida; no se limpió el origen.')
        for item in paths:shutil.rmtree(item)
    return {'ok':True,'message':'Configuración local eliminada. El respaldo externo permanece disponible; los documentos enviados a Windows deben revisarse en su cola.'}
