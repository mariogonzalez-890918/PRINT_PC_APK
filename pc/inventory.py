"""Fixed, read-only hardware audit and administrator-only Excel output."""
import io
import json
import subprocess
import re
from datetime import datetime,timezone

def collect_windows():
    script=r'''
    [Console]::OutputEncoding=[System.Text.Encoding]::UTF8
    $errorsFound=New-Object System.Collections.Generic.List[string]
    function Read-Hardware($class,$fields) {
      try { @(Get-CimInstance -ClassName $class -ErrorAction Stop | Select-Object -Property $fields) }
      catch { $errorsFound.Add($class+': '+$_.Exception.Message); @() }
    }
    $computer=@(Read-Hardware 'Win32_ComputerSystem' @('Manufacturer','Model','TotalPhysicalMemory','NumberOfLogicalProcessors'))
    $os=@(Read-Hardware 'Win32_OperatingSystem' @('Caption','Version','OSArchitecture','LastBootUpTime'))
    $cpu=@(Read-Hardware 'Win32_Processor' @('Name','NumberOfCores','NumberOfLogicalProcessors','MaxClockSpeed'))
    $ram=@(Read-Hardware 'Win32_PhysicalMemory' @('Manufacturer','Capacity','Speed','PartNumber','DeviceLocator'))
    $disks=@(Read-Hardware 'Win32_DiskDrive' @('Model','Size','InterfaceType','SerialNumber'))
    $boards=@(Read-Hardware 'Win32_BaseBoard' @('Manufacturer','Product','SerialNumber'))
    $graphics=@(Read-Hardware 'Win32_VideoController' @('Name','AdapterRAM','DriverVersion'))
    @{computer=$computer;os=$os;cpu=$cpu;ram=$ram;disks=$disks;boards=$boards;graphics=$graphics;errors=@($errorsFound)} | ConvertTo-Json -Depth 8 -Compress
    '''
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],
        capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('No se pudo consultar el inventario de Windows.')
    raw=json.loads(result.stdout.decode('utf-8-sig'))
    computer=(raw.get('computer') or [{}])[0]
    os_info=(raw.get('os') or [{}])[0]
    components=[]
    for category in ('cpu','ram','disks','boards','graphics'):
        for item in raw.get(category,[]):components.append({'category':category,'data':item})
    return {'platform':'Windows','summary':{'manufacturer':computer.get('Manufacturer'),'model':computer.get('Model'),
        'os':os_info.get('Caption'),'os_version':os_info.get('Version'),'architecture':os_info.get('OSArchitecture'),
        'cpu':'; '.join(str(p.get('Name','')) for p in raw.get('cpu',[])),
        'processors':computer.get('NumberOfLogicalProcessors'),'ram_bytes':computer.get('TotalPhysicalMemory'),
        'storage_bytes':sum(int(d.get('Size') or 0) for d in raw.get('disks',[]))},
        'components':components,'errors':raw.get('errors',[]),'collected_at':datetime.now(timezone.utc).isoformat()}

def export_xlsx(devices):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    workbook=Workbook()
    workbook.properties.creator='Área de TI GMP · sistemas@grupomipan.com'
    summary=workbook.active;summary.title='Equipos'
    detail=workbook.create_sheet('Componentes')
    summary.append(['Equipo','Tipo','Sistema','Versión SO','Fabricante','Modelo','CPU','Procesadores','RAM GB','Almacenamiento GB','Recibido UTC','Estado'])
    detail.append(['Equipo','Categoría','Propiedad','Valor'])
    def safe(value):
        if isinstance(value,(dict,list)):value=json.dumps(value,ensure_ascii=False)
        if isinstance(value,str):value=re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]','',value)[:32767]
        return value
    def append(sheet,values):
        sheet.append([safe(v) for v in values])
        for cell in sheet[sheet.max_row]:
            if isinstance(cell.value,str):cell.data_type='s'
    for device in devices:
        inventory=device.get('inventory') or {}
        data=inventory.get('summary') or {}
        def gb(key):
            try:return round(float(data[key])/(1024**3),2) if data.get(key) is not None else None
            except (ValueError,TypeError):return None
        received=datetime.fromtimestamp(device['received'],timezone.utc).strftime('%Y-%m-%d %H:%M:%S') if device.get('received') else ''
        append(summary,[device['name'],inventory.get('platform',device.get('role','')),data.get('os'),data.get('os_version'),data.get('manufacturer'),data.get('model'),data.get('cpu'),data.get('processors'),gb('ram_bytes'),gb('storage_bytes'),received,'Solicitado' if device.get('pending') else 'Recibido' if inventory else 'Sin auditoría'])
        for component in inventory.get('components',[]):
            if not isinstance(component,dict):continue
            values=component.get('data') or {}
            if not isinstance(values,dict):continue
            for key,value in values.items():append(detail,[device['name'],component.get('category',''),key,value])
        for error in inventory.get('errors',[]):append(detail,[device['name'],'Dato no disponible','Detalle',error])
    for sheet in workbook:
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]:cell.fill=PatternFill('solid',fgColor='123458');cell.font=Font(color='FFFFFF',bold=True)
        for i,column in enumerate(sheet.columns,1):
            sheet.column_dimensions[get_column_letter(i)].width=min(65,max(15,max(len(str(c.value or '')) for c in column)+2))
        for row in sheet.iter_rows(min_row=2):
            for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
    output=io.BytesIO();workbook.save(output);return output.getvalue()
