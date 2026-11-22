"""Windows inventory sources. No MSI product enumeration, scans or Office startup."""
import re
from datetime import datetime,timezone

WINDOWS_SCRIPT=r'''
[Console]::OutputEncoding=[System.Text.Encoding]::UTF8
$errorsFound=New-Object System.Collections.Generic.List[string]
function Read-Hardware($class,$fields) {
  try { @(Get-CimInstance -ClassName $class -ErrorAction Stop | Select-Object -Property $fields) }
  catch { $errorsFound.Add($class+': '+$_.Exception.Message); @() }
}
$computer=@(Read-Hardware 'Win32_ComputerSystem' @('Manufacturer','Model','TotalPhysicalMemory','NumberOfLogicalProcessors'))
$os=@(Read-Hardware 'Win32_OperatingSystem' @('Caption','Version','OSArchitecture'))
$bios=@(Read-Hardware 'Win32_BIOS' @('SerialNumber','SMBIOSBIOSVersion','Manufacturer'))
$product=@(Read-Hardware 'Win32_ComputerSystemProduct' @('IdentifyingNumber','Vendor','Name'))
$enclosure=@(Read-Hardware 'Win32_SystemEnclosure' @('SerialNumber','SMBIOSAssetTag','Manufacturer'))
$cpu=@(Read-Hardware 'Win32_Processor' @('Name','NumberOfCores','NumberOfLogicalProcessors','MaxClockSpeed'))
$ram=@(Read-Hardware 'Win32_PhysicalMemory' @('Manufacturer','Capacity','Speed','ConfiguredClockSpeed','PartNumber','SerialNumber','DeviceLocator','MemoryType','SMBIOSMemoryType'))
$disks=@(Read-Hardware 'Win32_DiskDrive' @('Index','Model','Size','InterfaceType','SerialNumber','MediaType'))
$boards=@(Read-Hardware 'Win32_BaseBoard' @('Manufacturer','Product','SerialNumber'))
$graphics=@(Read-Hardware 'Win32_VideoController' @('Name','AdapterRAM','DriverVersion'))
$physical=@()
try { $physical=@(Get-CimInstance -Namespace 'root/Microsoft/Windows/Storage' -ClassName MSFT_PhysicalDisk -ErrorAction Stop | Select-Object DeviceId,FriendlyName,SerialNumber,Size,MediaType,BusType,SpindleSpeed,PhysicalLocation) }
catch { $errorsFound.Add('MSFT_PhysicalDisk: '+$_.Exception.Message) }
$antivirus=@();$avQuery='ok';$defender=@();$defenderQuery='ok'
try { $antivirus=@(Get-CimInstance -Namespace 'root/SecurityCenter2' -ClassName AntiVirusProduct -ErrorAction Stop | Select-Object displayName,productState) }
catch { $avQuery='unavailable';$errorsFound.Add('SecurityCenter2: '+$_.Exception.Message) }
try { $defender=@(Get-MpComputerStatus -ErrorAction Stop | Select-Object AMServiceEnabled,AntivirusEnabled,RealTimeProtectionEnabled,AMRunningMode,AMProductVersion,AntivirusSignatureVersion) }
catch { $defenderQuery='unavailable';$errorsFound.Add('Microsoft Defender: '+$_.Exception.Message) }
$office=New-Object System.Collections.Generic.List[object]
$officeQuery='ok';$registryReadErrors=0
foreach($basePath in @('HKLM:\SOFTWARE\Microsoft\Office','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Office')) {
  $inventoryPath=$basePath+'\ClickToRun\Inventory\Office\16.0'
  $configPath=$basePath+'\ClickToRun\Configuration'
  try {
    if(Test-Path -LiteralPath $inventoryPath -ErrorAction Stop) {
      $installed=Get-ItemProperty -LiteralPath $inventoryPath -ErrorAction Stop
      if($installed.OfficeProductReleaseIds -or $installed.OfficePackageVersion) {
        $office.Add(@{Name='';ProductIds=$installed.OfficeProductReleaseIds;Version=$installed.OfficePackageVersion;Source='Inventario Click-to-Run';Installation='Click-to-Run';Authoritative=$true})
      }
    }
    if(Test-Path -LiteralPath $configPath -ErrorAction Stop) {
      $configuration=Get-ItemProperty -LiteralPath $configPath -ErrorAction Stop
      $binaryVersion='';$binaryName=''
      if($configuration.InstallationPath) {
        foreach($relative in @('root\Office16\WINWORD.EXE','root\Office16\EXCEL.EXE','root\Office16\OUTLOOK.EXE','Office16\WINWORD.EXE','Office16\EXCEL.EXE','WINWORD.EXE','EXCEL.EXE')) {
          $candidate=Join-Path -Path $configuration.InstallationPath -ChildPath $relative
          if(Test-Path -LiteralPath $candidate -PathType Leaf) {
            $binaryVersion=(Get-Item -LiteralPath $candidate -ErrorAction Stop).VersionInfo.ProductVersion
            $binaryName=Split-Path -Path $candidate -Leaf
            break
          }
        }
      }
      if($configuration.ProductReleaseIds) {
        $office.Add(@{Name='';ProductIds=$configuration.ProductReleaseIds;Version=$binaryVersion;Platform=$configuration.Platform;Source=('Configuracion C2R / archivo '+$binaryName);Installation='Click-to-Run';Authoritative=$false})
      }
    }
  } catch { $registryReadErrors++;$errorsFound.Add('Inventario Office: '+$_.Exception.Message) }
}
foreach($uninstallPath in @('HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall','HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall','HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall')) {
  try {
    if(Test-Path -LiteralPath $uninstallPath -ErrorAction Stop) {
      foreach($key in @(Get-ChildItem -LiteralPath $uninstallPath -ErrorAction Stop)) {
        $app=Get-ItemProperty -LiteralPath $key.PSPath -ErrorAction SilentlyContinue
        if($app.DisplayName -match '(?i)^Microsoft\s+(365|Office|Word|Excel|PowerPoint|Outlook|Access|Publisher|Visio|Project)\b') {
          $office.Add(@{Name=$app.DisplayName;ProductIds='';Version=$app.DisplayVersion;Source='Registro de programas instalados';Installation=$(if($app.WindowsInstaller -eq 1){'MSI'}else{'Registro'});Authoritative=$true})
        }
      }
    }
  } catch { $registryReadErrors++;$errorsFound.Add('Registro Office: '+$_.Exception.Message) }
}
if($registryReadErrors -gt 0){$officeQuery='partial'}
@{computer=$computer;os=$os;bios=$bios;product=$product;enclosure=$enclosure;cpu=$cpu;ram=$ram;disks=$disks;physical=$physical;boards=$boards;graphics=$graphics;antivirus=$antivirus;av_query=$avQuery;defender=$defender;defender_query=$defenderQuery;office=@($office.ToArray());office_query=$officeQuery;errors=@($errorsFound.ToArray())} | ConvertTo-Json -Depth 10 -Compress
'''

UNAVAILABLE='No disponible'
SMBIOS_RAM={18:'DDR',19:'DDR2',20:'DDR2 FB-DIMM',24:'DDR3',25:'FBD2',26:'DDR4',27:'LPDDR',28:'LPDDR2',29:'LPDDR3',30:'LPDDR4',34:'DDR5',35:'LPDDR5',32:'HBM',33:'HBM2',36:'HBM3'}
LEGACY_RAM={20:'DDR',21:'DDR2',22:'DDR2 FB-DIMM',24:'DDR3',25:'FBD2',26:'DDR4'}
BUS_TYPES={1:'SCSI',2:'ATAPI',3:'ATA',4:'IEEE 1394',6:'Fibre Channel',7:'USB',8:'RAID',9:'iSCSI',10:'SAS',11:'SATA',12:'SD',13:'MMC',15:'Virtual',16:'Storage Spaces',17:'NVMe',18:'SCM',19:'UFS'}
OFFICE_NAMES={
 'O365ProPlusRetail':'Microsoft 365 Apps para empresas','O365BusinessRetail':'Microsoft 365 Apps para negocios',
 'O365HomePremRetail':'Microsoft 365 Familia','O365PersonalRetail':'Microsoft 365 Personal',
 'ProPlus2024Volume':'Office LTSC Professional Plus 2024','Standard2024Volume':'Office LTSC Standard 2024',
 'ProPlus2021Volume':'Office LTSC Professional Plus 2021','Standard2021Volume':'Office LTSC Standard 2021',
 'ProPlus2019Volume':'Office Professional Plus 2019','Standard2019Volume':'Office Standard 2019',
 'Professional2024Retail':'Office Professional 2024','HomeBusiness2024Retail':'Office Hogar y Empresas 2024',
 'Home2024Retail':'Office Hogar 2024','Professional2021Retail':'Office Professional 2021',
 'HomeBusiness2021Retail':'Office Hogar y Empresas 2021','HomeStudent2021Retail':'Office Hogar y Estudiantes 2021',
 'Professional2019Retail':'Office Professional 2019','HomeBusiness2019Retail':'Office Hogar y Empresas 2019',
 'HomeStudent2019Retail':'Office Hogar y Estudiantes 2019',
}

def rows(raw,key):
    value=raw.get(key) or []
    return [value] if isinstance(value,dict) else [r for r in value if isinstance(r,dict)]

def integer(value):
    try:return int(value)
    except (ValueError,TypeError):return None

def identifier(value):
    value=str(value or '').strip().strip('\x00')
    canonical=re.sub(r'[^a-z0-9]','',value.lower())
    if canonical in ('','none','unknown','notavailable','notapplicable','na','defaultstring','systemserialnumber','tobefilledbyoem','notspecified') or set(canonical)<=set('0'):
        return None
    return value

def memory_type(item):
    smbios=integer(item.get('SMBIOSMemoryType'))
    if smbios not in (None,0,1,2):return SMBIOS_RAM.get(smbios,UNAVAILABLE)
    return LEGACY_RAM.get(integer(item.get('MemoryType')),UNAVAILABLE)

def disk_details(item,physical=False):
    result=dict(item)
    media=integer(item.get('MediaType')) if physical else None
    result['TipoDisco']={3:'Mecánico (HDD)',4:'SSD',5:'SCM'}.get(media,UNAVAILABLE)
    result['Conexion']=BUS_TYPES.get(integer(item.get('BusType')),UNAVAILABLE) if physical else item.get('InterfaceType') or UNAVAILABLE
    model=str(item.get('FriendlyName') or item.get('Model') or '')
    # NVMe is a bus/protocol, not proof of an M.2 physical form factor.
    result['Formato']='M.2 (indicado en el modelo)' if re.search(r'\bM\.2\b',model,re.I) else UNAVAILABLE
    result['FuenteTipo']='MSFT_PhysicalDisk.MediaType' if physical else 'Win32_DiskDrive (tipo no confirmado)'
    return result

def normalize_office(raw):
    entries=rows(raw,'office')
    preferred=[r for r in entries if r.get('Installation')=='Click-to-Run' and r.get('Authoritative')]
    configs=[r for r in entries if r.get('Installation')=='Click-to-Run' and not r.get('Authoritative')]
    chosen=preferred or configs
    result=[];seen=set()
    for item in chosen:
        fallback=next((c for c in configs if not item.get('ProductIds') or c.get('ProductIds')==item.get('ProductIds')), {})
        product_ids=item.get('ProductIds') or fallback.get('ProductIds') or ''
        if isinstance(product_ids,list):product_ids=','.join(str(x) for x in product_ids)
        ids=[x.strip() for x in re.split(r'[,;]',str(product_ids)) if x.strip()] or ['Office (edición no disponible)']
        for product in ids:
            name=OFFICE_NAMES.get(product,product)
            version=item.get('Version') or fallback.get('Version') or UNAVAILABLE
            key=(product,str(version))
            if key in seen:continue
            seen.add(key)
            source=item.get('Source') or UNAVAILABLE
            if not item.get('Version') and fallback.get('Version'):source+='; versión '+str(fallback.get('Source') or 'archivo Office')
            result.append({'Nombre':name,'ProductoID':product,'Version':version,'Instalacion':'Click-to-Run','Fuente':source})
    for item in entries:
        if item.get('Installation')=='Click-to-Run':continue
        name=str(item.get('Name') or '')
        if not name or re.search(r'(?i)(proof|language|idioma|\bmui\b|shared|extensibility|update|hotfix|redistributable|interop|runtime|file validation|compatibility|officehub|office hub)',name):continue
        if chosen and item.get('Installation')!='MSI':continue
        key=(name,str(item.get('Version') or ''))
        if key in seen:continue
        seen.add(key)
        result.append({'Nombre':name,'ProductoID':item.get('ProductIds') or '', 'Version':item.get('Version') or UNAVAILABLE,'Instalacion':item.get('Installation') or UNAVAILABLE,'Fuente':item.get('Source') or UNAVAILABLE})
    return result

def normalize_windows(raw):
    computer=(rows(raw,'computer') or [{}])[0];os_info=(rows(raw,'os') or [{}])[0]
    bios=(rows(raw,'bios') or [{}])[0];enclosure=(rows(raw,'enclosure') or [{}])[0];product=(rows(raw,'product') or [{}])[0]
    serial=next((s for s in (identifier(bios.get('SerialNumber')),identifier(enclosure.get('SerialNumber')),identifier(product.get('IdentifyingNumber'))) if s),None)
    maker=str(computer.get('Manufacturer') or '')
    service_tag=serial if re.search(r'(?i)dell|alienware',maker) else None
    memory=[dict(item,TipoRAM=memory_type(item)) for item in rows(raw,'ram')]
    physical=[disk_details(item,True) for item in rows(raw,'physical')]
    disks=[]
    for item in rows(raw,'disks'):
        data=disk_details(item)
        serial_key=re.sub(r'\s','',str(identifier(item.get('SerialNumber')) or '')).upper()
        matches=[p for p in physical if serial_key and re.sub(r'\s','',str(identifier(p.get('SerialNumber')) or '')).upper()==serial_key]
        if len(matches)!=1:
            model=re.sub(r'\s','',str(item.get('Model') or '')).casefold()
            matches=[p for p in physical if model and re.sub(r'\s','',str(p.get('FriendlyName') or '')).casefold()==model and integer(p.get('Size'))==integer(item.get('Size'))]
        if len(matches)==1:
            for key in ('TipoDisco','Conexion','Formato','FuenteTipo'):data[key]=matches[0][key]
        disks.append(data)
    office=normalize_office(raw)
    av=[]
    for item in rows(raw,'antivirus'):
        name=item.get('displayName') or UNAVAILABLE
        if re.search(r'(?i)(windows|microsoft)\s+defender',name):name='Microsoft Defender Antivirus'
        if not any(a['Nombre']==name for a in av):av.append(dict(Nombre=name,Estado='Registrado en Seguridad de Windows; actividad no confirmada',EstadoProveedor=item.get('productState')))
    defender=(rows(raw,'defender') or [None])[0]
    if defender:
        enabled=defender.get('AntivirusEnabled')
        detail={'Nombre':'Microsoft Defender Antivirus','Estado':'Antivirus habilitado' if enabled is True else 'Antivirus deshabilitado' if enabled is False else UNAVAILABLE,**defender}
        current=next((a for a in av if a['Nombre']=='Microsoft Defender Antivirus'),None)
        if current is not None:current.update(detail)
        else:av.append(detail)
    av_names=list(dict.fromkeys(a['Nombre'] for a in av))
    av_status='Detectado' if av else 'No detectado en las fuentes consultadas' if raw.get('av_query')=='ok' else UNAVAILABLE
    office_status='Detectado' if office else 'No detectado en las fuentes consultadas' if raw.get('office_query')=='ok' else UNAVAILABLE
    storage=physical or disks
    summary={'manufacturer':computer.get('Manufacturer'),'model':computer.get('Model'),'serial_number':serial or UNAVAILABLE,
        'service_tag':service_tag or UNAVAILABLE,'asset_tag':identifier(enclosure.get('SMBIOSAssetTag')) or UNAVAILABLE,
        'os':os_info.get('Caption'),'os_version':os_info.get('Version'),'architecture':os_info.get('OSArchitecture'),
        'cpu':'; '.join(str(p.get('Name','')) for p in rows(raw,'cpu')),'processors':computer.get('NumberOfLogicalProcessors'),
        'ram_bytes':computer.get('TotalPhysicalMemory'),'ram_types':', '.join(sorted({p['TipoRAM'] for p in memory})) or UNAVAILABLE,
        'storage_bytes':sum(integer(d.get('Size')) or 0 for d in rows(raw,'disks')),
        'disk_types':', '.join(sorted({p['TipoDisco'] for p in storage})) or UNAVAILABLE,
        'disk_connections':', '.join(sorted({p['Conexion'] for p in storage})) or UNAVAILABLE,
        'disk_formats':', '.join(sorted({p['Formato'] for p in storage})) or UNAVAILABLE,
        'antivirus_presence':av_status,'antivirus':'; '.join(av_names) or UNAVAILABLE,
        'antivirus_status':'; '.join(a['Nombre']+': '+a['Estado'] for a in av) or UNAVAILABLE,
        'office_presence':office_status,'office_type':'; '.join(o['Nombre'] for o in office) or UNAVAILABLE,
        'office_version':'; '.join(o['Nombre']+': '+str(o['Version']) for o in office) or UNAVAILABLE}
    components=[]
    identity={'NumeroSerie':summary['serial_number'],'ServiceTag':summary['service_tag'],'AssetTag':summary['asset_tag'],'FuenteSerie':'BIOS/chasis/identificación del fabricante'}
    components.append({'category':'Identificación','data':identity})
    for category,items in [('cpu',rows(raw,'cpu')),('ram',memory),('disks',disks),('physical_disks',physical),('boards',rows(raw,'boards')),('graphics',rows(raw,'graphics')),('Antivirus',av),('Office',office)]:
        for item in items:components.append({'category':category,'data':item})
    return {'platform':'Windows','summary':summary,'components':components,'errors':raw.get('errors',[]),'collected_at':datetime.now(timezone.utc).isoformat()}
