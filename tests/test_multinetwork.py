import base64
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.request
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from hub import Service,Server,digest
from registration import make_registration,parse_registration,join
from agent import api
from client import send_file
from network_config import normalize_urls

class MultiNetworkTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=Service(Path(self.tmp.name)/'hub');self.s.create_owner('demo@example.test','1234')
        self.servers=[Server(('127.0.0.1',0),self.s) for _ in range(2)]
        self.threads=[threading.Thread(target=s.serve_forever,daemon=True) for s in self.servers]
        for t in self.threads:t.start()
        self.urls=['http://127.0.0.1:'+str(s.server_port) for s in self.servers]
        self.s.set_public_url('\n'.join(self.urls))
        self.pc=self.s.register_pc('PC target',['Printer'])
        code='MOBILE'
        with self.s.db() as db:db.execute('INSERT INTO codes VALUES(?,?,?)',(digest(code),'tablet',time.time()+60))
        self.mobile=self.s.enroll('demo@example.test',code,'Mobile','tablet')
        with self.s.db() as db:
            self.pid=db.execute('SELECT id FROM printers').fetchone()[0]
            db.execute('INSERT INTO grants VALUES(?,?)',(self.mobile['id'],self.pid))
        self.config=dict(self.mobile,url=self.urls[0],urls=self.urls,server_id=self.s.server_id())
    def tearDown(self):
        for s in self.servers:s.shutdown();s.server_close()
        for t in self.threads:t.join(2)
        self.tmp.cleanup()
    def test_list_and_registration_preserve_all_addresses_and_server_identity(self):
        values=normalize_urls('192.168.0.10\n10.20.30.40;26.10.20.30,192.168.0.10')
        self.assertEqual(3,len(values));self.assertEqual(self.urls,self.s.registration_urls(8765))
        self.assertEqual(self.s.server_id(),Service(self.s.home).server_id())
        code='JOINPC'
        with self.s.db() as db:db.execute('INSERT INTO codes VALUES(?,?,?)',(digest(code),'pc',time.time()+60))
        addresses=['http://127.0.0.1:1']+self.urls
        envelope=make_registration('demo@example.test',code,'pc',addresses,self.s.server_id())
        self.assertEqual(addresses,parse_registration(envelope,'demo@example.test','pc')[0])
        config=join('demo@example.test',envelope,'PC joined','pc')
        self.assertEqual(self.urls[0],config['url']);self.assertEqual(addresses,config['urls']);self.assertEqual(self.s.server_id(),config['server_id'])
    def test_existing_client_learns_routes_and_changes_to_reachable_route(self):
        config=dict(self.mobile,url=self.urls[0])
        api(config,'client/printers')
        self.assertEqual(self.s.server_id(),config['server_id']);self.assertEqual(self.urls,config['urls'])
        config['url']='http://127.0.0.1:1'
        self.assertEqual(self.pid,api(config,'client/printers')['printers'][0]['id'])
        self.assertEqual(self.urls[0],config['url'])
    def test_wrong_server_does_not_receive_credentials(self):
        seen=[]
        class WrongServer(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                seen.append((self.path,self.headers.get('Authorization')))
                data=json.dumps({'service':'PRINTER-TAB','server_id':'another-server'}).encode()
                self.send_response(200);self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)
        other=http.server.ThreadingHTTPServer(('127.0.0.1',0),WrongServer);thread=threading.Thread(target=other.serve_forever,daemon=True);thread.start()
        try:
            self.config.update(url='http://127.0.0.1:1',urls=['http://127.0.0.1:'+str(other.server_port),self.urls[1]])
            self.assertEqual(1,len(api(self.config,'client/printers')['printers']))
            self.assertEqual([('/api/health',None)],seen)
        finally:other.shutdown();other.server_close();thread.join(2)
    def test_lost_upload_response_retries_same_job_on_other_route_once(self):
        source=Path(self.tmp.name)/'web.pdf';source.write_bytes(b'%PDF-1.4 synthetic')
        actual=urllib.request.urlopen;lost=[False]
        def intercept(request,*args,**kwargs):
            response=actual(request,*args,**kwargs)
            url=request.full_url if hasattr(request,'full_url') else request
            if url.startswith(self.urls[0]+'/api/client/jobs/') and not lost[0]:
                lost[0]=True;response.read();response.close();raise TimeoutError('Response lost')
            return response
        with patch('transport.urllib.request.urlopen',side_effect=intercept):
            result=send_file(self.config,Path(self.tmp.name)/'sender',{'printer':self.pid},source,str(uuid.uuid4()))
        self.assertEqual(self.urls[1],self.config['url'])
        with self.s.db() as db:self.assertEqual(1,db.execute('SELECT count(*) FROM jobs').fetchone()[0])
        self.assertEqual('queued',result['status'])
    def test_lost_claim_response_is_never_replayed_on_another_route(self):
        for _ in range(2):self.s.enqueue(self.mobile['id'],str(uuid.uuid4()),{'printer':self.pid},b'%PDF-1.4 fixture','application/pdf')
        config=dict(self.pc,url=self.urls[0],urls=self.urls,server_id=self.s.server_id())
        actual=urllib.request.urlopen;claims=[]
        def intercept(request,*args,**kwargs):
            response=actual(request,*args,**kwargs)
            url=request.full_url if hasattr(request,'full_url') else request
            if url.endswith('/api/pc/claim'):
                claims.append(url);response.read();response.close();raise TimeoutError('Claim response lost')
            return response
        with patch('transport.urllib.request.urlopen',side_effect=intercept),self.assertRaises(TimeoutError):api(config,'pc/claim',{})
        self.assertEqual(1,len(claims))
        with self.s.db() as db:self.assertEqual({'claimed':1,'queued':1},{r[0]:r[1] for r in db.execute('SELECT status,count(*) FROM jobs GROUP BY status')})
    def test_disabled_client_is_not_retried_to_evade_revocation(self):
        with self.s.db() as db:db.execute('UPDATE devices SET enabled=0 WHERE id=?',(self.mobile['id'],))
        actual=urllib.request.urlopen;calls=[]
        def intercept(request,*args,**kwargs):
            calls.append(request.full_url if hasattr(request,'full_url') else request)
            return actual(request,*args,**kwargs)
        with patch('transport.urllib.request.urlopen',side_effect=intercept),self.assertRaises(RuntimeError):api(self.config,'client/printers')
        self.assertEqual(1,len(calls))

if __name__=='__main__':unittest.main()
