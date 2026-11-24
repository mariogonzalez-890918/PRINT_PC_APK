import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from windows_queues import prepare,profile_tag,queue_name

class QueuePlanTest(unittest.TestCase):
    def test_install_plan_contains_only_loopback_urls_and_granted_printers(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);(home/'agent.json').write_text(json.dumps({'url':'http://10.20.30.40:8765','token':'synthetic','windows_bridge_port':23456}))
            printer={'id':'a'*32,'name':'Bixo','pc':'Source PC'}
            health=io.BytesIO(json.dumps({'service':'PRINTER-TAB-Windows','profile':profile_tag(home)}).encode())
            with patch('windows_queues.printers',return_value=['Physical printer']),patch('windows_queues.api',return_value={'printers':[printer]}),patch('windows_queues.urllib.request.urlopen',return_value=health):
                plan=prepare(home,'install')
            self.assertEqual('http://127.0.0.1:23456/ipp/'+'a'*32,plan['add'][0]['url'])
            self.assertEqual([],plan['remove']);self.assertNotIn('token',Path(plan['path']).read_text())
    def test_remove_plan_never_touches_physical_or_other_profile_queues(self):
        with tempfile.TemporaryDirectory() as temp:
            home=Path(temp);printer={'id':'a'*32,'name':'Bixo','pc':'Source'};managed=queue_name(printer,home)
            with patch('windows_queues.printers',return_value=[managed,'Physical Bixo','PRINTER-TAB - someone [ffffffff-aaaaaaaa]']):plan=prepare(home,'remove')
            self.assertEqual([managed],plan['remove']);self.assertEqual([],plan['add'])
    def test_unicode_queue_name_preserves_managed_suffix_and_limits(self):
        printer={'id':'b'*32,'name':'á漢'*150,'pc':'PC\nSource'}
        name=queue_name(printer,Path('profile'))
        self.assertLess(len(name.encode('utf-8')),250);self.assertTrue(name.endswith('-bbbbbbbb]'));self.assertNotIn('\n',name)

if __name__=='__main__':unittest.main()
