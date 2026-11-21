import io
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
import agent

class AgentTest(unittest.TestCase):
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
