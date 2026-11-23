import argparse
import base64
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))

def main():
    parser = argparse.ArgumentParser(description='PRINTER-TAB · Consola y agente de impresión')
    parser.add_argument('mode',nargs='?',choices=['hub','agent','status','configure-hub','configure-agent','admin-login','admin-state','admin-grants','admin-code','publish-printers','client-state','client-send','publish-client','reset-local','export-backup','restore-backup','clear-origin'])
    parser.add_argument('--headless',action='store_true')
    args = parser.parse_args()
    mode = args.mode
    home = Path(os.environ.get('LOCALAPPDATA','.')) / 'JADPrint'
    if mode in ('export-backup','restore-backup','clear-origin'):
        from backup_config import export_file,restore_file,clear_origin
        data=json.loads(sys.stdin.readline())
        if mode=='export-backup':result=export_file(home,data['path'])
        elif mode=='restore-backup':result=restore_file(home,data['path'],data.get('confirmation'))
        else:result=clear_origin(home,data['path'],data.get('confirmation'))
        print(json.dumps(result));return
    if mode=='reset-local':
        from reset_config import reset_local
        data=json.loads(sys.stdin.readline())
        print(json.dumps(reset_local(home,data.get('scope'),data.get('confirmation'))))
        return
    if mode in ('client-state','client-send','publish-client'):
        from agent import api,printers,atomic_json
        path=home/'agent'/'agent.json'
        if not path.exists():raise ValueError('Primero une esta PC con correo y código de registro.')
        config=json.loads(path.read_text(encoding='utf-8'))
        if mode=='client-state':
            result=api(config,'client/printers');result.update(api(config,'client/jobs'))
            result['pending']=(home/'sender'/'pending.json').exists()
            if result['pending']:result['pending_job']=json.loads((home/'sender'/'pending.json').read_text(encoding='utf-8'))
            print(json.dumps(result))
        elif mode=='publish-client':
            names=printers();api(config,'pc/heartbeat',{'printers':names});print(json.dumps({'printers':names}))
        else:
            from client import send_file
            data=json.loads(sys.stdin.readline())
            print(json.dumps(send_file(config,home,data.get('options'),data.get('path'),data.get('id'))))
        atomic_json(path,config)
        return
    if mode in ('admin-login','admin-state','admin-grants','admin-code','publish-printers'):
        from agent import api,atomic_json,printers
        from urllib.parse import urlsplit
        data=json.loads(sys.stdin.readline())
        from network_config import normalize_url
        url=normalize_url(data['url'])
        config={'url':url,'token':data.get('token','')}
        if mode=='admin-login':
            session=api(config,'login',{'email':data['email'],'password':data['password']})
            config['token']=session['token']
            print(json.dumps({'token':session['token'],'state':api(config,'admin/state')}))
        elif mode=='admin-state':
            print(json.dumps(api(config,'admin/state')))
        elif mode=='admin-grants':
            print(json.dumps(api(config,'admin/grants',{'tablet':data['tablet'],'printers':data['printers']})))
        elif mode=='admin-code':
            print(json.dumps(api(config,'admin/code',{'role':data.get('role','tablet')})))
        else:
            # Verify the administrator session before reading/publishing any device data.
            api(config,'admin/state')
            names=printers()
            if not names:
                raise ValueError('Windows no reportó impresoras instaladas. Instala el controlador y vuelve a intentarlo.')
            path=home/'agent'/'agent.json'
            if path.exists():
                device=json.loads(path.read_text(encoding='utf-8'))
                if device['url'].rstrip('/')!=url:
                    raise ValueError('Esta PC ya está vinculada a otro servidor. Usa la cuenta y dirección de ese servidor.')
            else:
                device={'url':url}
                device.update(api(config,'admin/register-pc',{'name':data['name'],'printers':names}))
                path.parent.mkdir(parents=True,exist_ok=True)
                atomic_json(path,device)
            api(device,'pc/heartbeat',{'printers':names})
            print(json.dumps({'printers':names,'id':device['id']}))
        return
    if mode == 'status':
        from hub import Service
        result = {'hub_configured':False,'agent_configured':(home/'agent'/'agent.json').exists(),'url':'http://localhost:8765'}
        if (home/'hub'/'hub.sqlite3').exists():
            service = Service(home/'hub')
            logo = service.logo()
            icon = service.icon()
            result.update(hub_configured=bool(service.owner_email()),email=service.owner_email(),logo=base64.b64encode(logo).decode() if logo else None,icon=base64.b64encode(icon).decode() if icon else None)
        if result['agent_configured']:
            from agent import api,atomic_json
            config = json.loads((home/'agent'/'agent.json').read_text(encoding='utf-8'))
            result.update(email=config['email'],url=config['url'])
            cache = home/'agent'/'branding.json'
            if cache.exists():
                result.update(json.loads(cache.read_text(encoding='utf-8')))
            try:
                branding = api(config,'pc/branding',timeout=4)
                atomic_json(home/'agent'/'agent.json',config)
                atomic_json(cache,branding)
                result.update(branding)
                result['url']=config['url']
            except Exception:
                pass
        print(json.dumps(result))
        return
    if mode == 'configure-hub':
        from hub import Service
        data = json.loads(sys.stdin.readline())
        Service(home/'hub').create_owner(data['email'].strip(),data['password'])
        print('Cuenta creada correctamente.')
        return
    if mode == 'configure-agent':
        from agent import api,atomic_json
        data = json.loads(sys.stdin.readline())
        path = home/'agent'/'agent.json'
        if path.exists():
            if not data.get('replace'):raise ValueError('Esta PC ya está vinculada.')
            if (home/'agent'/'inflight.json').exists() or (home/'sender'/'pending.json').exists():
                raise ValueError('Hay un trabajo sin confirmar. Revisa el servidor actual antes de cambiar la vinculación.')
        if data['code'].strip().startswith('PT3.'):
            from registration import join
            config=join(data['email'].strip(),data['code'].strip(),data['name'].strip(),'pc')
        else:
            from network_config import normalize_url
            config={'url':normalize_url(data['url'])}
            config.update(api(config,'enroll',{'email':data['email'].strip(),'code':data['code'].strip(),'name':data['name'].strip(),'role':'pc'}))
        path.parent.mkdir(parents=True,exist_ok=True)
        if path.exists():
            (path.parent/'agent.previous.json').write_bytes(path.read_bytes())
        atomic_json(path,config)
        print('PC vinculada correctamente.')
        return
    if not mode:
        print('PRINTER-TAB\n1. Servidor y consola administrador\n2. Agente de impresión de esta PC\n')
        mode = 'hub' if input('Elige 1 o 2: ').strip() == '1' else 'agent'
    if mode == 'hub':
        from hub import run
        run(home / 'hub',interactive=not args.headless)
    else:
        from agent import run
        run(home / 'agent',interactive=not args.headless)

if __name__ == '__main__':
    for stream in (sys.stdin,sys.stdout,sys.stderr):
        if stream and hasattr(stream,'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print('\nNo se pudo continuar:',e)
        sys.exit(1)
