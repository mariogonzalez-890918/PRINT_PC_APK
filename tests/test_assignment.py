from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import urllib.error
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
import agent
import main
from hub import Service,Server,digest

class AssignmentTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.s=Service(Path(self.tmp.name)/'hub')
        self.s.create_owner('admin@example.test','1234')
        with self.s.db() as db:
            db.execute('INSERT INTO sessions VALUES(?,?)',(digest('admin-session'),time.time()+60))
            for code in ('tablet1','tablet2'):
                db.execute('INSERT INTO codes VALUES(?,?,?)',(digest(code.upper()),'tablet',time.time()+60))
        self.t1=self.s.enroll('admin@example.test','tablet1','Tablet 1','tablet')
        self.t2=self.s.enroll('admin@example.test','tablet2','Tablet 2','tablet')
        self.server=Server(('127.0.0.1',0),self.s)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.tmp.cleanup()

    def request(self,path,body,token='admin-session'):
        req=urllib.request.Request(self.url+'/api/'+path,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
        try:
            with urllib.request.urlopen(req,timeout=5) as response:return json.load(response)
        except urllib.error.HTTPError as error:
            error.close();raise

    def test_publish_two_pcs_assign_independent_printers_per_tablet(self):
        p1=self.request('admin/register-pc',{'name':'PC1','printers':['Epson','Bixolon']})
        p2=self.request('admin/register-pc',{'name':'PC2','printers':['Etiquetas']})
        with self.s.db() as db:
            printers=[dict(r) for r in db.execute('SELECT * FROM printers ORDER BY name')]
        ids={p['name']:p['id'] for p in printers}
        self.request('admin/grants',{'tablet':self.t1['id'],'printers':[ids['Epson'],ids['Etiquetas']]})
        self.request('admin/grants',{'tablet':self.t2['id'],'printers':[ids['Bixolon']]})
        self.assertEqual({'Epson','Etiquetas'},{p['name'] for p in self.s.printer_list(self.t1['id'])})
        self.assertEqual({'Bixolon'},{p['name'] for p in self.s.printer_list(self.t2['id'])})
        self.request('admin/grants',{'tablet':self.t1['id'],'printers':[]})
        self.assertEqual([],self.s.printer_list(self.t1['id']))
        self.assertEqual({'Bixolon'},{p['name'] for p in self.s.printer_list(self.t2['id'])})

    def test_tablet_cannot_register_pc_or_edit_grants_and_invalid_save_preserves_permissions(self):
        with self.assertRaises(urllib.error.HTTPError) as caught:
            self.request('admin/register-pc',{'name':'Intrusa','printers':['Epson']},self.t1['token'])
        self.assertEqual(403,caught.exception.code)
        pc=self.request('admin/register-pc',{'name':'PC1','printers':['Epson']})
        with self.s.db() as db:pid=db.execute('SELECT id FROM printers WHERE pc=?',(pc['id'],)).fetchone()[0]
        self.request('admin/grants',{'tablet':self.t1['id'],'printers':[pid]})
        with self.assertRaises(urllib.error.HTTPError):self.request('admin/grants',{'tablet':self.t1['id'],'printers':['missing']})
        self.assertEqual([pid],[p['id'] for p in self.s.printer_list(self.t1['id'])])
        with self.assertRaises(urllib.error.HTTPError):self.request('admin/grants',{'tablet':self.t1['id'],'printers':[]},self.t1['token'])

    def test_native_publish_detects_printers_and_reuses_pc_without_pairing_code(self):
        data={'url':self.url,'token':'admin-session','name':'PC local'}
        def invoke():
            output=io.StringIO()
            with patch.dict(os.environ,{'LOCALAPPDATA':str(Path(self.tmp.name)/'profile')}),patch.object(sys,'argv',['main.py','publish-printers','--headless']),patch.object(sys,'stdin',io.StringIO(json.dumps(data))),patch.object(agent,'printers',return_value=['Epson','Bixolon']),redirect_stdout(output):
                main.main()
            return json.loads(output.getvalue())
        first,second=invoke(),invoke()
        self.assertEqual(first['id'],second['id'])
        self.assertEqual(['Epson','Bixolon'],first['printers'])
        with self.s.db() as db:
            self.assertEqual(1,db.execute("SELECT count(*) FROM devices WHERE role='pc'").fetchone()[0])
            self.assertEqual(2,db.execute('SELECT count(*) FROM printers').fetchone()[0])
        config=json.loads((Path(self.tmp.name)/'profile'/'JADPrint'/'agent'/'agent.json').read_text())
        self.assertEqual(first['id'],self.s.device(config['token'],'pc')['id'])
        self.assertEqual([],self.s.printer_list(self.t1['id']))

    def test_deletion_requires_admin_disabled_device_and_confirmation(self):
        data={'id':self.t1['id'],'confirmation':self.t1['id']}
        with self.assertRaises(urllib.error.HTTPError):self.request('admin/device/delete',data,self.t2['token'])
        with self.assertRaises(urllib.error.HTTPError):self.request('admin/device/delete',data)
        self.request('admin/device',{'id':self.t1['id'],'enabled':False})
        with self.assertRaises(urllib.error.HTTPError):self.request('admin/device/delete',dict(data,confirmation='wrong'))
        self.assertTrue(self.request('admin/device/delete',data)['ok'])
        with self.s.db() as db:self.assertIsNone(db.execute('SELECT id FROM devices WHERE id=?',(self.t1['id'],)).fetchone())
        with self.assertRaises(PermissionError):self.s.device(self.t1['token'])

    def test_delete_pc_removes_printers_grants_inventory_and_cancels_queue(self):
        pc=self.s.register_pc('PC to remove',['Printer demo'])
        with self.s.db() as db:
            pid=db.execute('SELECT id FROM printers WHERE pc=?',(pc['id'],)).fetchone()[0]
            db.execute('INSERT INTO grants VALUES(?,?)',(self.t1['id'],pid))
            db.execute('INSERT INTO printer_sharing VALUES(?,1)',(pid,))
        self.s.save_inventory(pc['id'],{'platform':'Windows','summary':{'model':'Synthetic'},'components':[]})
        self.s.request_inventory(pc['id'])
        job=self.s.enqueue(self.t1['id'],'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',{'printer':pid},b'%PDF-1.4 fixture','application/pdf')
        self.request('admin/device',{'id':pc['id'],'enabled':False})
        result=self.request('admin/device/delete',{'id':pc['id'],'confirmation':pc['id']})
        self.assertEqual(1,result['cancelled']);self.assertFalse((self.s.files/job['id']).exists())
        with self.assertRaises(PermissionError):self.s.heartbeat(pc['id'],['Late printer report'])
        with self.assertRaises(PermissionError):self.s.save_inventory(pc['id'],{'platform':'Windows','summary':{},'components':[]})
        with self.s.db() as db:
            for table,column in [('printers','pc'),('inventories','device'),('inventory_requests','device')]:
                self.assertEqual(0,db.execute('SELECT count(*) FROM '+table+' WHERE '+column+'=?',(pc['id'],)).fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM grants WHERE printer=?',(pid,)).fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM printer_sharing WHERE printer=?',(pid,)).fetchone()[0])
            self.assertEqual('error',db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])

    def test_delete_sender_cannot_interrupt_claimed_print_and_preserves_history(self):
        pc=self.s.register_pc('PC retained',['Printer demo'])
        with self.s.db() as db:
            pid=db.execute('SELECT id FROM printers WHERE pc=?',(pc['id'],)).fetchone()[0]
            db.execute('INSERT INTO grants VALUES(?,?)',(self.t1['id'],pid))
        job=self.s.enqueue(self.t1['id'],'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',{'printer':pid},b'%PDF-1.4 fixture','application/pdf')
        self.s.claim(pc['id'])
        self.request('admin/device',{'id':self.t1['id'],'enabled':False})
        data={'id':self.t1['id'],'confirmation':self.t1['id']}
        with self.assertRaises(urllib.error.HTTPError):self.request('admin/device/delete',data)
        self.s.finish(pc['id'],job['id'],'submitted','Sent to Windows')
        self.request('admin/device/delete',data)
        with self.s.db() as db:
            self.assertEqual('submitted',db.execute('SELECT status FROM jobs WHERE id=?',(job['id'],)).fetchone()[0])
            self.assertEqual(1,db.execute('SELECT count(*) FROM printers WHERE pc=?',(pc['id'],)).fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM grants WHERE tablet=?',(self.t1['id'],)).fetchone()[0])
