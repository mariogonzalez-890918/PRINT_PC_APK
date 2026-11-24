import http.client
import json
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from hub import Service,Server as HubServer
from agent import atomic_json
from windows_bridge import Broker,Server
import ipp_protocol as ipp

PDF=b'%PDF-1.4 synthetic fixture, never physically printed'

class WindowsBridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.s=Service(self.root/'hub');self.s.create_owner('demo@example.test','1234')
        self.source=self.s.register_pc('Source PC',['Bixo']);self.client=self.s.register_pc('Client PC',[])
        with self.s.db() as db:
            self.pid=db.execute('SELECT id FROM printers').fetchone()[0];db.execute('INSERT INTO grants VALUES(?,?)',(self.client['id'],self.pid))
        self.hub=HubServer(('127.0.0.1',0),self.s);self.ht=threading.Thread(target=self.hub.serve_forever,daemon=True);self.ht.start()
        self.home=self.root/'agent';self.home.mkdir();self.config=dict(self.client,url='http://127.0.0.1:'+str(self.hub.server_port),server_id=self.s.server_id())
        self.path=self.home/'agent.json';atomic_json(self.path,self.config)
        self.broker=Broker(self.home/'windows',self.path);self.server=Server(('127.0.0.1',0),self.broker)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/ipp/'+self.pid
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join(2);self.hub.shutdown();self.hub.server_close();self.ht.join(2);self.tmp.cleanup()
    def body(self,operation,attributes=(),document=b'',request=1):
        data=struct.pack('>BBHI',2,0,operation,request)+b'\x01'+ipp.attribute('attributes-charset',0x47,'utf-8')+ipp.attribute('attributes-natural-language',0x48,'en')+ipp.attribute('printer-uri',0x45,self.url.replace('http:','ipp:'))
        for key,tag,value in attributes:data+=ipp.attribute(key,tag,value)
        return data+b'\x03'+document
    def req(self,operation,attributes=(),document=b'',request=1):
        data=self.body(operation,attributes,document,request)
        with urllib.request.urlopen(urllib.request.Request(self.url,data=data,headers={'Content-Type':'application/ipp'}),timeout=5) as response:raw=response.read()
        return ipp.decode(raw)
    def test_native_printer_capabilities_and_unsupported_operation(self):
        status,_,attrs,_=self.req(11)
        self.assertEqual(0,status);self.assertEqual('application/pdf',attrs['document-format-default'][0])
        self.assertEqual('none',attrs['uri-authentication-supported'][0]);self.assertIn('PRINTER-TAB',attrs['printer-name'][0])
        self.assertEqual(0x0501,self.req(0x7fff)[0])
    def test_print_job_retransmission_is_one_local_and_remote_job(self):
        attributes=[('job-name',0x42,'Word document'),('copies',0x21,2),('document-format',0x49,'application/pdf')]
        _,_,first,_=self.req(2,attributes,PDF,42);_,_,again,_=self.req(2,attributes,PDF,42)
        self.assertEqual(first['job-id'],again['job-id']);job_id=first['job-id'][0]
        self.broker.process_once()
        with self.s.db() as db:
            rows=db.execute('SELECT * FROM jobs').fetchall();self.assertEqual(1,len(rows));self.assertEqual(2,rows[0]['copies'])
            remote_id=rows[0]['id']
        self.s.claim(self.source['id']);self.s.finish(self.source['id'],remote_id,'submitted','Simulated Windows receipt')
        self.broker.process_once()
        self.assertEqual(9,self.req(9,[('job-id',0x21,job_id)])[2]['job-state'][0])
        # Retransmitting Send-Document after completion does not resubmit paper.
        self.assertEqual(9,self.req(6,[('job-id',0x21,job_id),('last-document',0x22,True)],PDF)[2]['job-state'][0])
    def test_create_send_and_cancel_before_delivery(self):
        _,_,attrs,_=self.req(5,[('document-format',0x49,'application/pdf')]);job_id=attrs['job-id'][0]
        self.assertEqual(4,attrs['job-state'][0])
        self.assertEqual(0,self.req(6,[('job-id',0x21,job_id),('last-document',0x22,True)],PDF)[0])
        self.req(8,[('job-id',0x21,job_id)]);self.broker.process_once()
        self.assertEqual(7,self.req(9,[('job-id',0x21,job_id)])[2]['job-state'][0])
        self.assertIsNone(self.s.claim(self.source['id']))
    def test_permission_revocation_and_account_change_prevent_upload(self):
        _,_,attrs,_=self.req(2,[],PDF);job_id=attrs['job-id'][0]
        with self.s.db() as db:db.execute('DELETE FROM grants WHERE tablet=?',(self.client['id'],))
        self.broker.process_once();self.assertEqual('failed',self.broker.get(job_id,self.pid)['state'])
        with self.s.db() as db:self.assertEqual(0,db.execute('SELECT count(*) FROM jobs').fetchone()[0])
        with self.s.db() as db:db.execute('INSERT INTO grants VALUES(?,?)',(self.client['id'],self.pid))
        self.broker.cache_time=-100
        _,_,attrs,_=self.req(2,[],PDF,request=2)
        atomic_json(self.path,dict(self.config,token='changed-token'))
        self.broker.process_once();self.assertEqual('failed',self.broker.get(attrs['job-id'][0],self.pid)['state'])
    def test_lost_server_response_keeps_uuid_and_retries_without_duplicate(self):
        _,_,attrs,_=self.req(2,[],PDF);job_id=attrs['job-id'][0]
        actual=urllib.request.urlopen;lost=[False]
        def intercept(request,*args,**kwargs):
            response=actual(request,*args,**kwargs);url=request.full_url if hasattr(request,'full_url') else request
            if '/api/client/jobs/' in url and getattr(request,'data',None) and not lost[0]:lost[0]=True;response.read();response.close();raise TimeoutError('Response lost')
            return response
        with patch('transport.urllib.request.urlopen',side_effect=intercept):self.broker.process_once()
        self.assertEqual('pending',self.broker.get(job_id,self.pid)['state']);self.broker.process_once()
        with self.s.db() as db:self.assertEqual(1,db.execute('SELECT count(*) FROM jobs').fetchone()[0])
    def test_chunked_http_and_reject_unassigned_printer(self):
        body=self.body(11);connection=http.client.HTTPConnection('127.0.0.1',self.server.server_port)
        connection.request('POST','/ipp/'+self.pid,body=iter([body[:17],body[17:]]),headers={'Content-Type':'application/ipp','Transfer-Encoding':'chunked'},encode_chunked=True)
        self.assertEqual(0,ipp.decode(connection.getresponse().read())[0]);connection.close()
        self.url='http://127.0.0.1:'+str(self.server.server_port)+'/ipp/'+'f'*32
        self.assertEqual(0x0403,self.req(11)[0])

if __name__=='__main__':unittest.main()
