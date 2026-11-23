"""Install/uninstall into an isolated build path, without starting a print agent."""
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parents[1]
target=(root / '.build' / 'install-test').resolve()
if not target.is_relative_to((root / '.build').resolve()):
    raise RuntimeError('Ruta de prueba fuera del proyecto.')
installer=root / 'dist' / 'PRINTER-TAB-Instalador-0.5.0.exe'
subprocess.run([str(installer),'/CURRENTUSER','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',
                '/NOICONS','/TASKS=','/DIR='+str(target),'/LOG='+str(root/'.build'/'install.log')],check=True,timeout=90)
try:
    for name in ['PRINTER-TAB.exe','runtime/python.exe','engine/SumatraPDF.exe','pc/main.py','pc/admin.html']:
        if not (target/name).is_file():
            raise RuntimeError('Falta archivo instalado: '+name)
    subprocess.run([str(target/'runtime/python.exe'),str(target/'pc/main.py'),'--help'],check=True,timeout=20)
    subprocess.run([str(target/'runtime/python.exe'),'-c','import sys; import hub, agent; from PIL import Image; print("INSTALACION: runtime, servidor, agente e imagenes OK")'],check=True,timeout=20)
finally:
    subprocess.run([str(target/'unins000.exe'),'/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART'],check=True,timeout=60)
print('INSTALADOR Y DESINSTALADOR: OK')
