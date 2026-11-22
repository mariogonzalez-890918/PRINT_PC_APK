from contextlib import nullcontext
import io
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
import backup_config as backup
import reset_config as reset
from hub import Service

class BackupResetTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.env=patch.dict(os.environ,{'LOCALAPPDATA':str(self.root)});self.env.start()
        self.home=self.root/'JADPrint';self.s=Service(self.home/'hub');self.s.create_owner('demo@example.test','1234')
        self.pc=self.s.register_pc('PC demo',['Printer demo'])
        for name in ('agent','sender','branding','signing'):
            (self.home/name).mkdir();(self.home/name/'fixture').write_text('synthetic')
        self.guards=[patch.object(reset,'idle_guard',return_value=nullcontext()),patch.object(backup,'idle_guard',return_value=nullcontext())]
        for guard in self.guards:guard.start()
    def tearDown(self):
        for guard in reversed(self.guards):guard.stop()
        self.env.stop();self.tmp.cleanup()
    def export(self):
        path=self.root/'portable.zip';backup.export_file(self.home,path);return path
    def test_reset_client_is_reversible_and_preserves_server_and_signing(self):
        result=reset.reset_local(self.home,'client','RESTABLECER')
        self.assertTrue((self.home/'hub'/'hub.sqlite3').is_file());self.assertTrue((self.home/'signing'/'fixture').exists())
        self.assertFalse((self.home/'agent').exists());self.assertTrue((Path(result['backup'])/'agent'/'fixture').is_file())
    def test_reset_requires_explicit_confirmation_and_expected_root(self):
        with self.assertRaises(ValueError):reset.reset_local(self.home,'all','')
        with self.assertRaises(ValueError):reset.reset_local(self.root,'all','RESTABLECER')
        self.assertTrue((self.home/'agent').exists())
    def test_export_restore_preserves_account_and_inventory_disables_old_clients(self):
        self.s.save_inventory(self.pc['id'],{'platform':'Windows','summary':{'model':'Synthetic'},'components':[]})
        with self.s.db() as db:
            db.execute("INSERT INTO sessions VALUES('test-session',9999999999)")
            db.execute("INSERT INTO codes VALUES('test-code','pc',9999999999)")
            printer=db.execute('SELECT id FROM printers').fetchone()[0]
            db.execute('INSERT INTO grants VALUES(?,?)',(self.pc['id'],printer))
        self.s.enqueue(self.pc['id'],'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa',{'printer':printer},b'%PDF-1.4 test','application/pdf')
        portable=self.export()
        reset.reset_local(self.home,'all','RESTABLECER')
        backup.restore_file(self.home,portable,'RESTAURAR')
        restored=Service(self.home/'hub');self.assertEqual('demo@example.test',restored.owner_email())
        with restored.db() as db:
            self.assertEqual(0,db.execute('SELECT enabled FROM devices').fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM grants').fetchone()[0])
            self.assertEqual(0,db.execute('SELECT count(*) FROM sessions').fetchone()[0])
            self.assertEqual('unknown',db.execute('SELECT status FROM jobs').fetchone()[0])
            self.assertEqual(1,db.execute('SELECT count(*) FROM inventories').fetchone()[0])
    def test_restore_refuses_to_overwrite_existing_configuration(self):
        path=self.export()
        with self.assertRaises(ValueError):backup.restore_file(self.home,path,'RESTAURAR')
        self.assertEqual('demo@example.test',Service(self.home/'hub').owner_email())
    def test_zip_paths_and_tampering_are_rejected(self):
        content=io.BytesIO()
        with zipfile.ZipFile(content,'w') as z:z.writestr('../outside.txt','bad')
        with self.assertRaises(ValueError):backup.read_backup(content.getvalue())
        original=backup.server_backup(self.home/'hub');changed=io.BytesIO()
        with zipfile.ZipFile(io.BytesIO(original)) as src,zipfile.ZipFile(changed,'w') as dest:
            dest.writestr('manifest.json',src.read('manifest.json'));dest.writestr('hub.sqlite3',src.read('hub.sqlite3')+b'changed')
        with self.assertRaises(ValueError):backup.read_backup(changed.getvalue())
    def test_clear_requires_current_external_backup_and_exact_confirmation(self):
        path=self.export()
        with self.assertRaises(ValueError):backup.clear_origin(self.home,path,'')
        with self.s.db() as db:db.execute("UPDATE devices SET name='Changed'")
        with self.assertRaises(ValueError):backup.clear_origin(self.home,path,'BORRAR ORIGEN')
        self.assertTrue((self.home/'hub').exists())
    def test_clear_removes_active_configuration_only_after_backup_verification(self):
        path=self.export();backup.clear_origin(self.home,path,'BORRAR ORIGEN')
        for name in ('hub','agent','sender','branding'):self.assertFalse((self.home/name).exists())
        self.assertTrue(path.is_file());self.assertTrue((self.home/'signing'/'fixture').is_file())
        backup.restore_file(self.home,path,'RESTAURAR')
        self.assertEqual('demo@example.test',Service(self.home/'hub').owner_email())

if __name__=='__main__':unittest.main()
