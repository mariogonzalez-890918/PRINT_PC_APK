import base64
from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import secrets
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request
import uuid
from openpyxl import load_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from hub import Service,Server,digest
from registration import make_registration,parse_registration,join
from network_config import normalize_url
from client import send_file
from inventory import export_xlsx

class CentralTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.s=Service(self.tmp.name)
        self.s.create_owner('admin@example.test','1234')
        with self.s.db() as db:db.execute('INSERT INTO sessions VALUES(?,?)',(digest('admin'),time.time()+120))
        self.pc1=self.s.register_pc('PC1',['Epson'])
        self.pc2=self.s.register_pc('PC2',['Bixolon'])
        code='TABLETCODE'
        with self.s.db() as db:db.execute('INSERT INTO codes VALUES(?,?,?)',(digest(code),'tablet',time.time()+60))
        self.mobile=self.s.enroll('admin@example.test',code,'Celular','tablet')
        self.server=Server(('127.0.0.1',0),self.s)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)
        with self.s.db() as db:self.printer=db.execute('SELECT id FROM printers WHERE pc=?',(self.pc2['id'],)).fetchone()[0]

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.tmp.cleanup()

    def req(self,path,body=None,token='admin',binary=False):
        req=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(body).encode() if body is not None else None,
            headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=5) as response:return response.read() if binary else json.load(response)
        except urllib.error.HTTPError as error:error.close();raise

    def test_registration_email_code_without_ip_entry_and_single_use(self):
        with patch.dict(os.environ,{'PRINTER_TAB_PUBLIC_URL':self.url}):
            registration=self.req('admin/code',{'role':'pc'})
        urls,code=parse_registration(registration['registration'],'admin@example.test','pc')
        self.assertEqual([self.url],urls)
        enrolled=join('admin@example.test',registration['registration'],'Nueva PC','pc')
        self.assertEqual(self.url,enrolled['url'])
        with self.assertRaises(RuntimeError):join('admin@example.test',registration['registration'],'Otra PC','pc')
        with self.assertRaises(ValueError):parse_registration(registration['registration'],'other@example.test','pc')
        with self.assertRaises(ValueError):parse_registration(registration['registration'],'admin@example.test','tablet')

    def test_service_address_is_configured_once_by_admin_not_by_clients(self):
        self.req('admin/service-url',{'url':'https://example.onrender.com'})
        code=self.req('admin/code',{'role':'tablet'})['registration']
        urls,_=parse_registration(code,'admin@example.test','tablet')
        self.assertEqual(['https://example.onrender.com'],urls)
        with self.assertRaises(urllib.error.HTTPError):self.req('admin/service-url',{'url':'https://evil.invalid'},self.mobile['token'])
        self.assertEqual('https://example.onrender.com',self.s.public_url())
        self.req('admin/service-url',{'url':''});self.assertEqual('',self.s.public_url())

    def test_authentication_attempts_are_rate_limited(self):
        for _ in range(20):self.server.auth_failure('127.0.0.1')
        with self.assertRaises(urllib.error.HTTPError) as result:self.req('enroll',{'email':'admin@example.test','code':'bad','name':'bad','role':'tablet'},token='')
        self.assertEqual(429,result.exception.code)

    def test_pc_can_send_to_other_pc_and_retry_does_not_duplicate(self):
        self.req('admin/grants',{'tablet':self.pc1['id'],'printers':[self.printer]})
        visible=self.req('client/printers',token=self.pc1['token'])['printers']
        self.assertEqual(['Bixolon'],[p['name'] for p in visible])
        self.assertEqual([],self.req('client/printers',token=self.mobile['token'])['printers'])
        path=Path(self.tmp.name)/'fixture.pdf';path.write_bytes(b'%PDF-1.4\nfixture\n%%EOF')
        config=dict(self.pc1,url=self.url);job_id=str(uuid.uuid4())
        actual=urllib.request.urlopen
        def lost_response(*args,**kwargs):
            with actual(*args,**kwargs) as response:response.read()
            raise TimeoutError('Simulación de confirmación perdida')
        with patch('client.urllib.request.urlopen',side_effect=lost_response),self.assertRaises(TimeoutError):
            send_file(config,Path(self.tmp.name)/'sender-profile',{'printer':self.printer},path,job_id)
        result=send_file(config,Path(self.tmp.name)/'sender-profile')
        self.assertEqual(job_id,result['id'])
        with self.s.db() as db:self.assertEqual(1,db.execute('SELECT count(*) FROM jobs').fetchone()[0])
        claimed=self.s.claim(self.pc2['id']);self.assertEqual(job_id,claimed['id'])
        self.assertIsNone(self.s.claim(self.pc1['id']))

    def test_global_sharing_blocks_granted_devices_and_queued_jobs(self):
        self.req('admin/grants',{'tablet':self.pc1['id'],'printers':[self.printer]})
        job=self.s.enqueue(self.pc1['id'],str(uuid.uuid4()),{'printer':self.printer},b'%PDF-1.4 fixture','application/pdf')
        self.req('admin/printer-sharing',{'printer':self.printer,'enabled':False})
        self.assertEqual([],self.s.printer_list(self.pc1['id']))
        with self.assertRaises(PermissionError):self.s.enqueue(self.pc1['id'],str(uuid.uuid4()),{'printer':self.printer},b'%PDF-1.4 fixture','application/pdf')
        self.assertIsNone(self.s.claim(self.pc2['id']))
        with self.s.db() as db:self.assertEqual('error',db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])

    def test_android_spooler_upload_retry_status_and_cancel_are_private(self):
        self.req('admin/grants',{'tablet':self.mobile['id'],'printers':[self.printer]})
        job_id=str(uuid.uuid4());options={'printer':self.printer,'name':'Página web','copies':2,'paper':'letter','color':'monochrome'}
        def upload():
            request=urllib.request.Request(self.url+'/api/client/jobs/'+job_id,data=b'%PDF-1.4 synthetic web print',headers={
                'Authorization':'Bearer '+self.mobile['token'],'Content-Type':'application/pdf',
                'X-Print-Options':base64.b64encode(json.dumps(options).encode()).decode()})
            with urllib.request.urlopen(request) as response:return json.load(response)
        self.assertEqual('queued',upload()['status']);self.assertEqual('queued',upload()['status'])
        self.assertEqual(2,self.req('client/jobs/'+job_id,token=self.mobile['token'])['copies'])
        with self.assertRaises(urllib.error.HTTPError):self.req('client/jobs/'+job_id,token=self.pc1['token'])
        with self.assertRaises(urllib.error.HTTPError):self.req('client/jobs/'+job_id+'/cancel',{},self.pc1['token'])
        self.assertTrue(self.req('client/jobs/'+job_id+'/cancel',{},self.mobile['token'])['cancelled'])
        self.assertEqual('cancelled',upload()['status']);self.assertIsNone(self.s.claim(self.pc2['id']))
        self.assertFalse((self.s.files/job_id).exists())

    def test_cancel_before_upload_survives_restart_and_cancel_after_claim_is_honest(self):
        self.req('admin/grants',{'tablet':self.mobile['id'],'printers':[self.printer]})
        job_id=str(uuid.uuid4())
        self.assertTrue(self.req('client/jobs/'+job_id+'/cancel',{},self.mobile['token'])['cancelled'])
        restarted=Service(self.tmp.name)
        result=restarted.enqueue(self.mobile['id'],job_id,{'printer':self.printer},b'%PDF-1.4 fixture','application/pdf')
        self.assertEqual('cancelled',result['status']);self.assertIsNone(restarted.claim(self.pc2['id']))
        accepted=self.s.enqueue(self.mobile['id'],str(uuid.uuid4()),{'printer':self.printer},b'%PDF-1.4 fixture','application/pdf')
        self.s.claim(self.pc2['id'])
        self.assertFalse(self.req('client/jobs/'+accepted['id']+'/cancel',{},self.mobile['token'])['cancelled'])
        self.s.finish(self.pc2['id'],accepted['id'],'submitted','Sent to Windows')
        self.assertEqual('submitted',self.req('client/jobs/'+accepted['id'],token=self.mobile['token'])['status'])

    def test_permission_changes_are_committed_before_success_response(self):
        for _ in range(6):
            self.req('admin/grants',{'tablet':self.mobile['id'],'printers':[self.printer]})
            self.assertEqual(1,len(self.s.printer_list(self.mobile['id'])))
            self.req('admin/grants',{'tablet':self.mobile['id'],'printers':[]})
            self.assertEqual([],self.s.printer_list(self.mobile['id']))

    def test_inventory_pc_and_android_is_private_and_exports_excel(self):
        pending=self.req('admin/inventory/request',{'device':self.pc1['id']})['id']
        self.assertEqual(pending,self.req('pc/heartbeat',{'printers':['Epson']},self.pc1['token'])['inventory_request'])
        windows={'platform':'Windows','summary':{'model':'Equipo prueba','os':'Windows','ram_bytes':8*1024**3,'cpu':'CPU de prueba'},'components':[{'category':'RAM','data':{'Modelo':'=HYPERLINK("bad")'}}]}
        with self.assertRaises(urllib.error.HTTPError):self.req('client/inventory',{'request':pending,'inventory':windows},self.mobile['token'])
        self.req('pc/inventory',{'request':pending,'inventory':windows},self.pc1['token'])
        android={'platform':'Android','summary':{'model':'Tablet prueba','os':'Android','ram_bytes':4*1024**3},'components':[]}
        request=self.req('admin/inventory/request',{'device':self.mobile['id']})['id']
        self.assertEqual(request,self.req('client/heartbeat',{},self.mobile['token'])['inventory_request'])
        self.req('client/inventory',{'request':request,'inventory':android},self.mobile['token'])
        with self.assertRaises(urllib.error.HTTPError):self.req('admin/inventory',token=self.mobile['token'])
        devices=self.req('admin/inventory')['devices'];self.assertEqual(2,len([d for d in devices if d['inventory']]))
        report=self.req('admin/inventory.xlsx',binary=True)
        workbook=load_workbook(io.BytesIO(report))
        self.assertEqual(['Equipos','Componentes'],workbook.sheetnames)
        formulas=[c for row in workbook['Componentes'] for c in row if c.data_type=='f'];self.assertEqual([],formulas)
        self.assertEqual('=HYPERLINK("bad")',workbook['Componentes']['D2'].value)
        self.assertEqual(2,len([d for d in Service(self.tmp.name).inventory_list() if d['inventory']]))

    def test_network_normalization_public_https_and_vpn_ip(self):
        self.assertEqual('http://10.20.30.40:8765',normalize_url('10.20.30.40'))
        self.assertEqual('https://example.onrender.com',normalize_url('https://example.onrender.com/'))
        for address in ['http://user:secret@host','https://host/path','https://host?token=bad']:
            with self.assertRaises(ValueError):normalize_url(address)

    def test_backup_download_is_admin_only_and_snapshot_is_valid(self):
        from backup_config import read_backup
        data=self.req('admin/backup.zip',binary=True)
        self.assertTrue(read_backup(data).startswith(b'SQLite format 3'))
        with self.assertRaises(urllib.error.HTTPError):self.req('admin/backup.zip',token=self.mobile['token'],binary=True)

    def test_cloud_start_requires_explicit_account_and_does_not_replace_existing(self):
        import central_server
        with tempfile.TemporaryDirectory() as folder:
            env={'PRINTER_TAB_DATA':folder,'PRINTER_TAB_ADMIN_EMAIL':'setup@example.test','PRINTER_TAB_ADMIN_PASSWORD':'1234','PORT':'9000'}
            with patch.dict(os.environ,env),patch.object(central_server,'run') as run:
                central_server.start();run.assert_called_once_with(Path(folder),9000,interactive=False)
            self.assertEqual('setup@example.test',Service(folder).owner_email())
