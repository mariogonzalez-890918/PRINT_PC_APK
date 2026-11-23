"""One address format for local/VPN IPs and public HTTPS servers."""
import ipaddress
import urllib.parse
import re

def normalize_url(value):
    value=str(value).strip().rstrip('/')
    if '://' not in value:value='http://'+value
    parsed=urllib.parse.urlsplit(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('Usa una IP del servidor o una dirección HTTPS completa.')
    try:port=parsed.port
    except ValueError:raise ValueError('Puerto del servidor inválido.') from None
    host=parsed.hostname
    if parsed.scheme=='http' and port is None:
        try:ipaddress.ip_address(host);port=8765
        except ValueError:
            if host.lower()=='localhost':port=8765
    authority=('['+host+']' if ':' in host else host)+((':'+str(port)) if port is not None else '')
    return urllib.parse.urlunsplit((parsed.scheme,authority,'','',''))

def normalize_urls(value):
    values=value if isinstance(value,list) else re.split(r'[\s,;]+',str(value).strip()) if str(value).strip() else []
    result=list(dict.fromkeys(normalize_url(v) for v in values))
    if len(result)>12:raise ValueError('Configura como máximo 12 direcciones del mismo servidor.')
    return result
