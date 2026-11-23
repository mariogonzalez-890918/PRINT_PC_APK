"""Verify install-over-install and preserved account data without printing."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

root=Path(__file__).resolve().parents[1]
target=(root/'.build'/'upgrade-test').resolve()
if not target.is_relative_to((root/'.build').resolve()):
    raise RuntimeError('Ruta de prueba fuera del proyecto.')
flags=['/CURRENTUSER','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/NOICONS','/TASKS=','/DIR='+str(target)]
with tempfile.TemporaryDirectory(prefix='printer-tab-upgrade-') as profile:
    env=dict(os.environ,LOCALAPPDATA=profile)
    installed=False
    try:
        subprocess.run([str(root/'dist'/'JADPrint-Instalador-0.1.0.exe')]+flags,check=True,timeout=120)
        installed=True
        runtime=str(target/'runtime'/'python.exe')
        setup="from hub import Service; from pathlib import Path; import os; s=Service(Path(os.environ['LOCALAPPDATA'])/'JADPrint'/'hub'); s.create_owner('upgrade@example.test','Fixture-12345'); print('Cuenta de prueba creada')"
        subprocess.run([runtime,'-c',setup],check=True,env=env,timeout=30)
        database=Path(profile)/'JADPrint'/'hub'/'hub.sqlite3'
        original=hashlib.sha256(database.read_bytes()).hexdigest()
        subprocess.run([str(root/'dist'/'PRINTER-TAB-Instalador-0.4.2.exe')]+flags,check=True,timeout=120)
        if hashlib.sha256(database.read_bytes()).hexdigest()!=original:
            raise RuntimeError('El instalador modificó los datos de la cuenta.')
        if not (target/'PRINTER-TAB.exe').is_file() or (target/'JADPrint.exe').exists():
            raise RuntimeError('El ejecutable no se actualizó correctamente.')
        result=subprocess.run([runtime,str(target/'pc'/'main.py'),'status','--headless'],check=True,env=env,
                              capture_output=True,text=True,encoding='utf-8',timeout=30)
        data=json.loads(result.stdout)
        if not data['hub_configured'] or data['email']!='upgrade@example.test':
            raise RuntimeError('No se conservó la cuenta tras actualizar.')
        print('ACTUALIZACION 0.1.0 -> 0.2.1 Y CUENTA CONSERVADA: OK',flush=True)
    finally:
        if installed:
            subprocess.run([str(target/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],check=True,timeout=90)
print('DESINSTALACION DE LA PRUEBA: OK',flush=True)
