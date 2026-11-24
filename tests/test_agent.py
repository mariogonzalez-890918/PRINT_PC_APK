import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
import agent

class AgentTest(unittest.TestCase):
    def test_upgraded_agent_uploads_extended_inventory_without_manual_request(self):
        class EndLoop(BaseException):pass
        snapshot={'platform':'Windows','schema_version':2,'summary':{'os':'Windows'},'components':[]}
        submitted=[]
        def fake_api(config,path,body=None,**kwargs):
            if path=='pc/heartbeat':return {}
            if path=='pc/inventory':submitted.append(body);return {'ok':True}
            if path=='pc/claim':raise EndLoop()
            raise AssertionError(path)
        pool=MagicMock();pool.submit.return_value.done.return_value=True;pool.submit.return_value.result.return_value=snapshot
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);(home/'agent.json').write_text(json.dumps({'url':'http://127.0.0.1:9999','email':'test@example.test'}))
            kernel=MagicMock();kernel.GetLastError.return_value=0
            monitor=MagicMock();monitor.poll.return_value=(None,'Consulta local pendiente')
            with patch.object(agent,'api',side_effect=fake_api),patch.object(agent,'printers',return_value=[]),patch.object(agent,'PrinterMonitor',return_value=monitor),patch.object(agent,'ThreadPoolExecutor',return_value=pool),patch('windows_bridge.start',side_effect=RuntimeError('Bridge disabled in test')),patch('ctypes.windll.kernel32',kernel):
                with self.assertRaises(EndLoop):agent.run(home,interactive=False)
            self.assertEqual(snapshot,submitted[0]['inventory']);self.assertIsNone(submitted[0]['request'])
            self.assertEqual(2,json.loads((home/'inventory-schema.json').read_text())['schema'])

    def test_discovery_uses_isolated_native_enumeration_and_friendly_timeout(self):
        with patch.object(agent.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=json.dumps({'printers':['bixo','Impresora áé']}).encode())) as run:
            self.assertEqual(['bixo','Impresora áé'],agent.printers())
            self.assertTrue(run.call_args.args[0][1].endswith('windows_printers.py'));self.assertEqual(8,run.call_args.kwargs['timeout'])
            self.assertNotIn('powershell.exe',run.call_args.args[0])
        with patch.object(agent.subprocess,'run',side_effect=subprocess.TimeoutExpired('native-enumeration',8)):
            with self.assertRaisesRegex(RuntimeError,'Cola de impresión'):agent.printers()

    def test_discovery_empty_is_valid_but_invalid_response_is_not(self):
        for payload,code in [(b'{"printers":[]}',0),(b'{"error":"spooler unavailable"}',1),(b'not json',0)]:
            with patch.object(agent.subprocess,'run',return_value=types.SimpleNamespace(returncode=code,stdout=payload)):
                if payload==b'{"printers":[]}':self.assertEqual([],agent.printers())
                else:
                    with self.assertRaises(RuntimeError):agent.printers()
        names=['Physical Bixo']+['PRINTER-TAB - proxy '+str(i) for i in range(201)]
        with patch.object(agent.subprocess,'run',return_value=types.SimpleNamespace(returncode=0,stdout=json.dumps({'printers':names}).encode())):
            self.assertEqual(['Physical Bixo'],agent.printers())
            self.assertEqual(names,agent.printers(include_managed=True))

    def test_print_command_passes_printer_name_as_one_argument_and_cleans_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            job={'id':'test-id','mime':'application/pdf','printer_name':'EPSON & Caja "1"',
                 'copies':2,'scale':'noscale','color':'monochrome','paper':'driver'}
            with patch.object(agent,'api',return_value=b'%PDF-1.4'),patch.object(agent,'printers',return_value=[job['printer_name']]),patch.object(agent.Path,'is_file',return_value=True),patch.object(agent.subprocess,'run',return_value=types.SimpleNamespace(returncode=0)) as run:
                status,message=agent.execute_print({},job,home)
                self.assertEqual('submitted',status)
                args=run.call_args.args[0]
                self.assertEqual(job['printer_name'],args[2])
                self.assertIn('2x,noscale,monochrome',args)
                self.assertNotIn('shell',run.call_args.kwargs)
            self.assertEqual([],list((home/'work').iterdir()))

    def test_timeout_is_uncertain_and_never_claims_physical_success(self):
        job={'id':'test-id','mime':'application/pdf','printer_name':'BIXOLON',
             'copies':1,'scale':'fit','color':'color','paper':'A4'}
        with tempfile.TemporaryDirectory() as tmp,patch.object(agent,'api',return_value=b'%PDF-1.4'),patch.object(agent,'printers',return_value=['BIXOLON']),patch.object(agent.Path,'is_file',return_value=True),patch.object(agent.subprocess,'run',side_effect=subprocess.TimeoutExpired('engine',180)):
            status,message=agent.execute_print({},job,Path(tmp))
            self.assertEqual('unknown',status)
            self.assertIn('cola de Windows',message)
