"""Registration envelopes carry connection addresses, never account passwords."""
import base64
import json
import os
import socket
import ipaddress
import binascii
from network_config import normalize_url

def server_urls(port=8765):
    public=os.environ.get('PRINTER_TAB_PUBLIC_URL') or os.environ.get('RENDER_EXTERNAL_URL')
    if public:return [normalize_url(public)]
    addresses=set()
    try:
        for address in socket.getaddrinfo(socket.gethostname(),None,socket.AF_INET):
            value=ipaddress.ip_address(address[4][0])
            if not value.is_loopback and not value.is_link_local and not value.is_unspecified:addresses.add(str(value))
    except OSError:pass
    return ['http://'+ip+':'+str(port) for ip in sorted(addresses)][:12]

def make_registration(email,code,role,urls):
    if not urls:raise ValueError('Configura la dirección pública o conecta el servidor a una red para generar el registro.')
    payload={'version':3,'service':'PRINTER-TAB','email':email,'code':code,'role':role,'urls':urls}
    return 'PT3.'+base64.urlsafe_b64encode(json.dumps(payload,separators=(',',':')).encode()).decode().rstrip('=')

def parse_registration(value,email,role):
    if not isinstance(value,str) or not value.startswith('PT3.') or len(value)>8192:
        raise ValueError('Pega el código completo de registro que genera el servidor (PT3...).')
    try:
        encoded=value.strip()[4:]
        payload=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
        if payload['service']!='PRINTER-TAB' or payload['version']!=3 or payload['role']!=role:
            raise ValueError('Usa un código de registro PRINTER-TAB correspondiente al tipo de equipo.')
        if payload['email'].strip().lower()!=email.strip().lower():
            raise ValueError('El correo no corresponde al código de registro.')
        urls=payload['urls']
        if not isinstance(urls,list) or not 1<=len(urls)<=12:raise ValueError()
        urls=[normalize_url(url) for url in urls]
        if not isinstance(payload['code'],str) or not 1<=len(payload['code'])<=100:raise ValueError()
        return urls,payload['code']
    except (KeyError,TypeError,json.JSONDecodeError,UnicodeError,binascii.Error) as e:
        raise ValueError('Código de registro inválido.') from e

def join(email,registration,name,role):
    from agent import api
    urls,code=parse_registration(registration,email,role)
    last_error=None
    for url in urls:
        try:
            data=api({'url':url},'enroll',{'email':email,'code':code,'name':name,'role':role},timeout=8)
            return dict(data,url=url)
        except RuntimeError:
            # An HTTP response means we reached the server: do not reuse a consumed/invalid code elsewhere.
            raise
        except (OSError,ValueError) as e:last_error=e
    raise ValueError('No se pudo llegar al servidor del código. Revisa que esté activo y accesible por Internet, red local o VPN. Detalle: '+str(last_error))
