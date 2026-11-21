import argparse
import os
from pathlib import Path
import sys

def main():
    parser = argparse.ArgumentParser(description='JAD Print · Consola y agente de impresión')
    parser.add_argument('mode',nargs='?',choices=['hub','agent'])
    args = parser.parse_args()
    mode = args.mode
    if not mode:
        print('JAD PRINT\n1. Servidor y consola administrador\n2. Agente de impresión de esta PC\n')
        mode = 'hub' if input('Elige 1 o 2: ').strip() == '1' else 'agent'
    home = Path(os.environ.get('LOCALAPPDATA','.')) / 'JADPrint'
    if mode == 'hub':
        from hub import run
        run(home / 'hub')
    else:
        from agent import run
        run(home / 'agent')

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print('\nNo se pudo continuar:',e)
        input('Presiona Enter para cerrar...')
        sys.exit(1)
