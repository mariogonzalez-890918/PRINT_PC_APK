"""Optional Python host entry point; the Windows EXE remains self contained."""
import os
from pathlib import Path
from hub import Service,run

def start():
    home=Path(os.environ.get('PRINTER_TAB_DATA','data'))
    service=Service(home)
    if not service.owner_email():
        email=os.environ.get('PRINTER_TAB_ADMIN_EMAIL','').strip()
        password_file=os.environ.get('PRINTER_TAB_ADMIN_PASSWORD_FILE')
        password=Path(password_file).read_text(encoding='utf-8').rstrip('\r\n') if password_file else os.environ.get('PRINTER_TAB_ADMIN_PASSWORD','')
        if not email or not password:
            raise RuntimeError('Primera instalación: configura PRINTER_TAB_ADMIN_EMAIL y PRINTER_TAB_ADMIN_PASSWORD (o PASSWORD_FILE) en el alojamiento. No hay contraseña predeterminada.')
        service.create_owner(email,password)
        os.environ.pop('PRINTER_TAB_ADMIN_PASSWORD',None)
    run(home,int(os.environ.get('PORT','8765')),interactive=False)

if __name__=='__main__':start()
