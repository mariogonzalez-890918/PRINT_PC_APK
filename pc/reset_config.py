"""Explicit local reset: archive known data directories, never delete or contact a server."""
from contextlib import contextmanager
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import socket
import uuid

@contextmanager
def idle_guard(home):
    # Agent mutex is also used by older installed clients. A listening local server
    # must be stopped before moving its SQLite database (including WAL files).
    handle=None
    if os.name=='nt':
        import ctypes
        kernel=ctypes.WinDLL('kernel32',use_last_error=True)
        kernel.OpenMutexW.restype=ctypes.c_void_p
        kernel.OpenMutexW.argtypes=[ctypes.c_uint,ctypes.c_int,ctypes.c_wchar_p]
        kernel.CloseHandle.argtypes=[ctypes.c_void_p]
        name='Local\\JADPrintAgent-'+hashlib.sha256(str(home/'agent').encode()).hexdigest()[:16]
        handle=kernel.OpenMutexW(0x100000,False,name)
        if handle:
            kernel.CloseHandle(handle)
            raise ValueError('Detén la impresión en todos los paneles de esta PC antes de restablecer.')
    try:
        with socket.create_connection(('127.0.0.1',8765),timeout=.3):
            raise ValueError('Detén el servidor local en todos los paneles antes de restablecer.')
    except OSError:pass
    yield

def reset_local(home,scope,confirmation):
    if scope not in ('client','all') or confirmation!='RESTABLECER':
        raise ValueError('Selecciona el alcance y escribe RESTABLECER para confirmar.')
    home=Path(home).absolute()
    expected=(Path(os.environ['LOCALAPPDATA'])/'JADPrint').absolute()
    if home!=expected or home.is_symlink() or home.is_junction():
        raise ValueError('Ruta de datos no válida para restablecer.')
    backup_root=home.parent/'PRINTER-TAB-Respaldos'
    if backup_root.is_symlink() or backup_root.is_junction():raise ValueError('Ruta de respaldo no válida.')
    names=['agent','sender','branding']+(['hub'] if scope=='all' else [])
    sources=[home/name for name in names if (home/name).exists()]
    # Validate all targets before the first move; junctions/links could escape the profile.
    for source in sources:
        if source.is_symlink() or source.is_junction() or source.resolve().parent!=home.resolve():
            raise ValueError('La configuración contiene una ruta enlazada. No se modificó.')
    with idle_guard(home):
        destination=backup_root/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
        destination.mkdir(parents=True)
        moved=[]
        try:
            for source in sources:
                source.rename(destination/source.name);moved.append(source)
            (destination/'respaldo.json').write_text(json.dumps({'scope':scope,'directories':[s.name for s in moved]},ensure_ascii=False),encoding='utf-8')
        except Exception:
            for source in reversed(moved):(destination/source.name).rename(source)
            raise
    return {'ok':True,'backup':str(destination),'scope':scope}
