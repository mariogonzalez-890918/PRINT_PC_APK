import argparse
import base64
import json
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))

def main():
    parser = argparse.ArgumentParser(description='PRINTER-TAB · Consola y agente de impresión')
    parser.add_argument('mode',nargs='?',choices=['hub','agent','status','configure-hub','configure-agent'])
    parser.add_argument('--headless',action='store_true')
    args = parser.parse_args()
    mode = args.mode
    home = Path(os.environ.get('LOCALAPPDATA','.')) / 'JADPrint'
    if mode == 'status':
        from hub import Service
        result = {'hub_configured':False,'agent_configured':(home/'agent'/'agent.json').exists(),'url':'http://localhost:8765'}
        if (home/'hub'/'hub.sqlite3').exists():
            service = Service(home/'hub')
            logo = service.logo()
            icon = service.icon()
            result.update(hub_configured=bool(service.owner_email()),email=service.owner_email(),logo=base64.b64encode(logo).decode() if logo else None,icon=base64.b64encode(icon).decode() if icon else None)
        if not result['hub_configured'] and result['agent_configured']:
            from agent import api,atomic_json
            config = json.loads((home/'agent'/'agent.json').read_text(encoding='utf-8'))
            result.update(email=config['email'],url=config['url'])
            cache = home/'agent'/'branding.json'
            if cache.exists():
                result.update(json.loads(cache.read_text(encoding='utf-8')))
            try:
                branding = api(config,'pc/branding',timeout=4)
                atomic_json(cache,branding)
                result.update(branding)
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
        from urllib.parse import urlsplit
        data = json.loads(sys.stdin.readline())
        url = data['url'].strip().rstrip('/')
        parsed = urlsplit(url)
        if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError('Dirección del servidor inválida.')
        path = home/'agent'/'agent.json'
        if path.exists():
            raise ValueError('Esta PC ya está vinculada.')
        config = {'url':url}
        config.update(api(config,'enroll',{'email':data['email'].strip(),'code':data['code'].strip(),'name':data['name'].strip(),'role':'pc'}))
        path.parent.mkdir(parents=True,exist_ok=True)
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
