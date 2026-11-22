import io
from pathlib import Path
import sys
import unittest
from openpyxl import load_workbook
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
from inventory_windows import memory_type,disk_details,normalize_windows,normalize_office
from inventory import export_xlsx

class WindowsInventoryTest(unittest.TestCase):
    def test_ram_uses_smbios_and_keeps_unknown_types(self):
        self.assertEqual('DDR4',memory_type({'SMBIOSMemoryType':26,'MemoryType':0}))
        self.assertEqual('DDR5',memory_type({'SMBIOSMemoryType':34}))
        self.assertEqual('DDR2',memory_type({'SMBIOSMemoryType':0,'MemoryType':21}))
        self.assertEqual('No disponible',memory_type({'SMBIOSMemoryType':99,'MemoryType':21}))

    def test_nvme_is_not_proof_of_m2_and_fixed_disk_is_not_proof_of_hdd(self):
        disk=disk_details({'MediaType':4,'BusType':17,'FriendlyName':'Synthetic NVMe'},True)
        self.assertEqual('SSD',disk['TipoDisco']);self.assertEqual('NVMe',disk['Conexion'])
        self.assertEqual('No disponible',disk['Formato'])
        self.assertIn('M.2',disk_details({'FriendlyName':'Synthetic M.2 SSD'})['Formato'])
        self.assertEqual('No disponible',disk_details({'MediaType':'Fixed hard disk media'})['TipoDisco'])

    def test_identification_separates_service_tag_and_asset(self):
        raw={'computer':[{'Manufacturer':'Dell Inc.'}],'bios':[{'SerialNumber':'To be filled by OEM'}],
             'enclosure':[{'SerialNumber':'DEMO123','SMBIOSAssetTag':'ASSET-EXAMPLE'}]}
        summary=normalize_windows(raw)['summary']
        self.assertEqual('DEMO123',summary['service_tag']);self.assertEqual('ASSET-EXAMPLE',summary['asset_tag'])
        raw['computer'][0]['Manufacturer']='Other'
        self.assertEqual('No disponible',normalize_windows(raw)['summary']['service_tag'])

    def test_disk_match_must_be_unique(self):
        physical={'FriendlyName':'Example','Size':1000,'MediaType':4,'BusType':17}
        raw={'disks':[{'Model':'Example','Size':1000}],'physical':[physical,physical]}
        components=normalize_windows(raw)['components']
        disk=next(c['data'] for c in components if c['category']=='disks')
        self.assertEqual('No disponible',disk['TipoDisco'])
        raw['physical']=[physical]
        disk=next(c['data'] for c in normalize_windows(raw)['components'] if c['category']=='disks')
        self.assertEqual('SSD',disk['TipoDisco'])

    def test_office_authoritative_version_wins_and_16_does_not_mean_2016(self):
        raw={'office':[{'Installation':'Click-to-Run','Authoritative':True,'ProductIds':'O365ProPlusRetail','Version':'16.0.99999.10000'},
                       {'Installation':'Click-to-Run','ProductIds':'O365ProPlusRetail','Version':'16.0.11111.10000'},
                       {'Name':'Microsoft Office Shared Components','Version':'16.0'}]}
        office=normalize_office(raw)
        self.assertEqual(1,len(office));self.assertEqual('16.0.99999.10000',office[0]['Version'])
        self.assertIn('365',office[0]['Nombre']);self.assertNotIn('2016',office[0]['Nombre'])
        self.assertEqual('UnrecognizedRetail',normalize_office({'office':[{'Installation':'Click-to-Run','ProductIds':'UnrecognizedRetail','Version':'16.0'}]})[0]['Nombre'])

    def test_antivirus_missing_source_does_not_claim_no_protection(self):
        raw={'av_query':'unavailable','defender_query':'unavailable'}
        self.assertEqual('No disponible',normalize_windows(raw)['summary']['antivirus_presence'])
        raw.update(antivirus=[{'displayName':'Windows Defender'},{'displayName':'Microsoft Defender Antivirus'}],defender=[{'AntivirusEnabled':True}])
        report=normalize_windows(raw)
        self.assertEqual(1,len([c for c in report['components'] if c['category']=='Antivirus']))
        self.assertIn('habilitado',report['summary']['antivirus_status'])

    def test_extended_excel_columns_are_text_and_legacy_android_still_exports(self):
        devices=[{'name':'PC example','inventory':{'summary':{'serial_number':'=BAD()','office_version':'16.0.123'}}},
                 {'name':'Tablet example','inventory':{'platform':'Android','summary':{'model':'Demo'}}}]
        workbook=load_workbook(io.BytesIO(export_xlsx(devices)))
        sheet=workbook['Equipos'];headers=[c.value for c in sheet[1]]
        serial=headers.index('Número de serie')+1
        self.assertEqual('=BAD()',sheet.cell(2,serial).value);self.assertEqual('s',sheet.cell(2,serial).data_type)
        self.assertEqual('No disponible',sheet.cell(3,serial).value)

    def test_missing_values_explain_source_and_report_identifies_collector(self):
        report=normalize_windows({'computer':[{'Manufacturer':'Other'}],'bios':[{'SerialNumber':'DEMO'}]})
        self.assertEqual(2,report['schema_version'])
        self.assertIn('Número de serie',report['field_status']['service_tag'])
        self.assertIn('NVMe',report['field_status']['disk_formats'])

if __name__=='__main__':unittest.main()
