"""Fail over only to verified addresses of the same server; preserve POST semantics."""
import json
import urllib.error
import urllib.request
from network_config import normalize_url,normalize_urls

def addresses(config):
    return normalize_urls([config['url']]+config.get('urls',[]))

def learn(config,result):
    connection=result.get('_connection') if isinstance(result,dict) else None
    if not connection:return
    identity=connection.get('server_id')
    if config.get('server_id') and identity!=config['server_id']:raise ValueError('La respuesta pertenece a otro servidor.')
    if identity:
        config['server_id']=identity
        config['urls']=normalize_urls([config['url']]+connection.get('urls',[]))

def verify(url,identity,timeout):
    with urllib.request.urlopen(url+'/api/health',timeout=min(timeout,3)) as response:health=json.load(response)
    if health.get('service')!='PRINTER-TAB' or (identity and health.get('server_id')!=identity):
        raise ValueError('La dirección pertenece a otro servidor; no se enviaron credenciales.')
    return health.get('server_id')

def request(config,path,data=None,headers=None,timeout=35,retry_safe=True):
    candidates=addresses(config);errors=[]
    # A claim or enrollment cannot be repeated after an ambiguous POST result.
    # Select a reachable address with GET first, then perform exactly one mutation.
    if not retry_safe:
        selected=None
        for url in candidates:
            if url!=config['url'] and not config.get('server_id'):continue
            try:verify(url,config.get('server_id'),timeout);selected=url;break
            except (OSError,ValueError) as error:errors.append(url+': '+str(error))
        if selected is None:raise OSError('No se pudo llegar al servidor. '+ ' | '.join(errors))
        candidates=[selected]
    for url in candidates:
        try:
            if retry_safe and data is not None and len(candidates)>1 and url==config['url']:
                verify(url,config.get('server_id'),timeout)
            if retry_safe and url!=config['url']:
                if not config.get('server_id'):continue
                verify(url,config['server_id'],timeout)
            req=urllib.request.Request(url+'/api/'+path,data=data,headers=headers or {})
            with urllib.request.urlopen(req,timeout=min(timeout,6) if len(candidates)>1 and data is None else timeout) as response:
                result=response.read(26*1024*1024)
            config['url']=url
            return result
        except urllib.error.HTTPError:raise
        except (OSError,ValueError) as error:
            if not retry_safe:raise
            if len(candidates)==1:raise
            errors.append(url+': '+str(error))
    raise OSError('Ninguna dirección del servidor respondió. '+ ' | '.join(errors))
