import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

sys.path.insert(0,str(Path(__file__).resolve().parents[1] / 'pc'))
from hub import Service,Server,digest,MAX_FILE

PDF = b'%PDF-1.4\nprotocol fixture, never printed\n%%EOF'

class ProtocolTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Service(self.tmp.name)
        self.s.create_owner('admin@example.test',secrets.token_urlsafe(16))
        self.pc1 = self.enroll('pc','PC1')
        self.pc2 = self.enroll('pc','PC2')
        self.tablet = self.enroll('tablet','Tablet 1')
        self.other = self.enroll('tablet','Tablet 2')
        self.s.heartbeat(self.pc1['id'],['Epson'])
        self.s.heartbeat(self.pc2['id'],['Bixolon'])
        with self.s.db() as db:
            self.p1 = db.execute('SELECT id FROM printers WHERE pc=?',(self.pc1['id'],)).fetchone()[0]
            self.p2 = db.execute('SELECT id FROM printers WHERE pc=?',(self.pc2['id'],)).fetchone()[0]
            db.executemany('INSERT INTO grants VALUES(?,?)',[(self.tablet['id'],self.p1),(self.tablet['id'],self.p2)])

    def tearDown(self):
        self.tmp.cleanup()

    def code(self,role):
        code = secrets.token_hex(5).upper()
        with self.s.db() as db:
            db.execute('INSERT INTO codes VALUES(?,?,?)',(digest(code),role,time.time()+60))
        return code

    def enroll(self,role,name):
        return self.s.enroll('admin@example.test',self.code(role),name,role)

    def enqueue(self,printer=None,job_id=None,tablet=None,content=PDF,**options):
        return self.s.enqueue(tablet or self.tablet['id'],job_id or str(uuid.uuid4()),
          dict(printer=printer or self.p1,name='Prueba.pdf',**options),content,'application/pdf')

    def test_one_tablet_can_choose_printers_on_two_pcs(self):
        self.assertEqual({'PC1','PC2'},{p['pc'] for p in self.s.printer_list(self.tablet['id'])})
        self.assertEqual([],self.s.printer_list(self.other['id']))
        j1,j2 = self.enqueue(self.p1),self.enqueue(self.p2)
        self.assertEqual(j1['id'],self.s.claim(self.pc1['id'])['id'])
        self.assertEqual(j2['id'],self.s.claim(self.pc2['id'])['id'])
        self.assertIsNone(self.s.claim(self.pc1['id']))

    def test_unassigned_tablet_cannot_print(self):
        with self.assertRaises(PermissionError):
            self.enqueue(tablet=self.other['id'])

    def test_parallel_retries_create_only_one_job(self):
        job_id=str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.enqueue(job_id=job_id),range(16)))
        self.assertEqual({job_id},{j['id'] for j in results})
        with self.s.db() as db:
            self.assertEqual(1,db.execute('SELECT count(*) FROM jobs').fetchone()[0])
        with self.assertRaises(ValueError):
            self.enqueue(job_id=job_id,copies=2)
        with self.assertRaises(ValueError):
            self.enqueue(job_id=job_id,content=PDF+b'changed')

    def test_claim_is_durable_and_never_automatically_reprinted(self):
        job=self.enqueue()
        self.assertIsNotNone(self.s.claim(self.pc1['id']))
        restarted=Service(self.tmp.name)
        self.assertIsNone(restarted.claim(self.pc1['id']))
        self.assertEqual('claimed',self.enqueue(job_id=job['id'])['status'])
        self.s.finish(self.pc1['id'],job['id'],'unknown','Revisar cola')
        self.assertFalse((self.s.files / job['id']).exists())

    def test_finish_retries_are_idempotent_and_isolated_by_pc(self):
        job=self.enqueue();self.s.claim(self.pc1['id'])
        with self.assertRaises(ValueError):
            self.s.finish(self.pc2['id'],job['id'],'submitted','Falso')
        self.s.finish(self.pc1['id'],job['id'],'submitted','Enviado a Windows')
        self.s.finish(self.pc1['id'],job['id'],'submitted','Enviado a Windows')
        self.assertEqual('submitted',self.enqueue(job_id=job['id'])['status'])
        self.assertFalse((self.s.files / job['id']).exists())

    def test_revoking_permission_blocks_waiting_job(self):
        job=self.enqueue()
        with self.s.db() as db:
            db.execute('DELETE FROM grants WHERE tablet=?',(self.tablet['id'],))
        self.assertIsNone(self.s.claim(self.pc1['id']))
        with self.s.db() as db:
            self.assertEqual('error',db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])
        self.assertFalse((self.s.files / job['id']).exists())

    def test_pairing_role_expiry_and_single_use(self):
        code=self.code('tablet')
        with self.assertRaises(PermissionError):
            self.s.enroll('admin@example.test',code,'Intruso','pc')
        self.s.enroll('admin@example.test',code,'Tablet','tablet')
        with self.assertRaises(PermissionError):
            self.s.enroll('admin@example.test',code,'Tablet','tablet')
        code=self.code('pc')
        with self.s.db() as db:
            db.execute('UPDATE codes SET expires=0 WHERE code=?',(digest(code),))
        with self.assertRaises(PermissionError):
            self.s.enroll('admin@example.test',code,'PC','pc')

    def test_disable_device_and_missing_printer(self):
        self.s.heartbeat(self.pc1['id'],[])
        p=next(p for p in self.s.printer_list(self.tablet['id']) if p['id']==self.p1)
        self.assertEqual(0,p['online'])
        with self.s.db() as db:
            db.execute('UPDATE devices SET enabled=0 WHERE id=?',(self.tablet['id'],))
        with self.assertRaises(PermissionError):
            self.s.device(self.tablet['token'])
        with self.assertRaises(PermissionError):
            self.s.device(self.pc1['token'],'tablet')

    def test_invalid_payload_and_settings(self):
        for options in [{'copies':0},{'copies':21},{'scale':'shell'},{'paper':'80mm & cmd'},{'color':'unknown'}]:
            with self.subTest(options=options),self.assertRaises(ValueError):
                self.enqueue(**options)
        with self.assertRaises(ValueError):self.enqueue(content=b'not a pdf')
        with self.assertRaises(ValueError):self.enqueue(job_id='../../outside')

    def test_http_end_to_end_and_auth_boundaries(self):
        server=Server(('127.0.0.1',0),self.s)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def req(path,token='',body=None,headers=None):
            h={'Authorization':'Bearer '+token,'Content-Type':'application/json'}
            h.update(headers or {})
            request=urllib.request.Request(base+path,data=body,headers=h)
            with urllib.request.urlopen(request,timeout=5) as response:return response.read()
        try:
            with self.assertRaises(urllib.error.HTTPError) as err:req('/api/admin/state',self.tablet['token'])
            self.assertEqual(403,err.exception.code)
            self.assertEqual(2,len(json.loads(req('/api/tablet/printers',self.tablet['token']))['printers']))
            job_id=str(uuid.uuid4())
            headers={'Content-Type':'application/pdf','X-Print-Options':base64.b64encode(json.dumps({'printer':self.p1,'name':'PDF'}).encode()).decode()}
            first=json.loads(req('/api/tablet/jobs/'+job_id,self.tablet['token'],PDF,headers))
            second=json.loads(req('/api/tablet/jobs/'+job_id,self.tablet['token'],PDF,headers))
            self.assertEqual(first['id'],second['id'])
            req('/api/pc/claim',self.pc1['token'],b'{}')
            with self.assertRaises(urllib.error.HTTPError):req('/api/pc/file/'+job_id,self.pc2['token'])
            self.assertEqual(PDF,req('/api/pc/file/'+job_id,self.pc1['token']))
            req('/api/pc/finish',self.pc1['token'],json.dumps({'id':job_id,'status':'submitted','message':'Prueba simulada'}).encode())
            with self.assertRaises(urllib.error.HTTPError):req('/api/pc/file/'+job_id,self.pc1['token'])
            with self.assertRaises(urllib.error.HTTPError):req('/api/pc/heartbeat',self.tablet['token'],b'{"printers":[]}')
            with self.assertRaises(urllib.error.HTTPError):req('/api/admin/grants',self.pc1['token'],b'{}')
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)

if __name__=='__main__':unittest.main()
