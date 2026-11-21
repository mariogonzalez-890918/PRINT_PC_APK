import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from hub import Service,Server,digest,password_hash

class BrandingTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.s=Service(self.tmp.name)
        self.s.create_owner('admin@example.test','abcd')

    def tearDown(self):
        self.tmp.cleanup()

    def image(self):
        out=io.BytesIO()
        Image.new('RGBA',(40,30),(20,100,192,128)).save(out,format='PNG')
        return out.getvalue()

    def test_password_boundary_and_rotation_preserve_devices(self):
        with tempfile.TemporaryDirectory() as other:
            empty=Service(other)
            for value in ['','a','abc','x'*201]:
                with self.assertRaises(ValueError):empty.create_owner('a@example.test',value)
            empty.create_owner('a@example.test','1234')
        with self.s.db() as db:
            db.execute('INSERT INTO sessions VALUES(?,?)',(digest('keep'),time.time()+60))
            db.execute('INSERT INTO sessions VALUES(?,?)',(digest('old'),time.time()+60))
        with self.assertRaises(PermissionError):self.s.change_password('wrong','1234','keep')
        with self.assertRaises(ValueError):self.s.change_password('abcd','123','keep')
        self.s.change_password('abcd','1234','keep')
        self.assertTrue(self.s.admin('keep'))
        self.assertFalse(self.s.admin('old'))
        with self.s.db() as db:
            row=db.execute('SELECT * FROM owner').fetchone()
        self.assertEqual(row['password'],password_hash('1234',row['salt']))

    def test_logo_validation_persistence_and_reset(self):
        self.assertIsNone(self.s.logo())
        self.s.set_logo(self.image())
        stored=Service(self.tmp.name).logo()
        self.assertTrue(stored.startswith(b'\x89PNG'))
        with Image.open(io.BytesIO(stored)) as logo:
            self.assertEqual((40,30),logo.size)
            self.assertEqual('RGBA',logo.mode)
        for value in [b'<svg onload="alert(1)"></svg>',b'not an image',b'x'*(2*1024*1024+1)]:
            with self.assertRaises(ValueError):self.s.set_logo(value)
        self.assertEqual(stored,self.s.logo())
        self.s.reset_logo()
        self.assertIsNone(self.s.logo())

    def test_icon_accepts_image_and_ico_and_can_restore(self):
        self.s.set_icon(self.image())
        stored=self.s.icon()
        self.assertTrue(stored.startswith(b'\x00\x00\x01\x00'))
        with Image.open(io.BytesIO(stored)) as icon:
            self.assertEqual('ICO',icon.format)
            self.assertEqual((256,256),icon.size)
        self.s.set_icon(stored)
        with self.assertRaises(ValueError):self.s.set_icon(b'<svg></svg>')
        self.assertIsNotNone(Service(self.tmp.name).icon())
        self.s.reset_icon()
        self.assertIsNone(self.s.icon())

    def test_http_logo_requires_admin_and_login_accepts_four_characters(self):
        server=Server(('127.0.0.1',0),self.s)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        base='http://127.0.0.1:'+str(server.server_port)
        def request(path,body=None,token=''):
            req=urllib.request.Request(base+path,data=body,headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=5) as r:return r.read()
            except urllib.error.HTTPError as e:
                e.close();raise
        try:
            login=json.loads(request('/api/login',json.dumps({'email':'admin@example.test','password':'abcd'}).encode()))
            token=login['token']
            with self.assertRaises(urllib.error.HTTPError):request('/api/admin/logo',self.image())
            request('/api/admin/logo',self.image(),token)
            self.assertTrue(request('/branding/logo').startswith(b'\x89PNG'))
            request('/api/admin/logo/reset',b'{}',token)
            self.assertTrue(request('/branding/logo').startswith(b'<svg'))
            with self.assertRaises(urllib.error.HTTPError):request('/api/admin/icon',self.image())
            request('/api/admin/icon',self.image(),token)
            self.assertIsNotNone(self.s.icon())
            request('/api/admin/icon/reset',b'{}',token)
            self.assertIsNone(self.s.icon())
            request('/api/admin/password',json.dumps({'current':'abcd','password':'1234'}).encode(),token)
            self.assertIn('token',json.loads(request('/api/login',json.dumps({'email':'admin@example.test','password':'1234'}).encode())))
        finally:
            server.shutdown();server.server_close();thread.join(2)

    def test_gui_bridge_configures_account_without_terminal_prompts(self):
        main=Path(__file__).resolve().parents[1]/'pc'/'main.py'
        with tempfile.TemporaryDirectory() as folder:
            env=dict(os.environ,LOCALAPPDATA=folder)
            args=[sys.executable,str(main)]
            configured=subprocess.run(args+['configure-hub','--headless'],input=json.dumps({'email':'gui@example.test','password':'1234'}),text=True,encoding='utf-8',capture_output=True,env=env,timeout=15)
            self.assertEqual(0,configured.returncode,configured.stdout+configured.stderr)
            info=subprocess.run(args+['status','--headless'],text=True,encoding='utf-8',capture_output=True,env=env,timeout=15)
            status=json.loads(info.stdout)
            self.assertTrue(status['hub_configured'])
            self.assertFalse(status['agent_configured'])
            self.assertEqual('gui@example.test',status['email'])
            self.assertNotIn('password',status)
