"""Fixed, read-only hardware audit and administrator-only Excel output."""
import io
import json
import subprocess
import re
from datetime import datetime,timezone

def collect_windows():
    from inventory_windows import WINDOWS_SCRIPT,normalize_windows
    result=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',WINDOWS_SCRIPT],
        capture_output=True,timeout=90,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    if result.returncode:raise RuntimeError('No se pudo consultar el inventario de Windows.')
    return normalize_windows(json.loads(result.stdout.decode('utf-8-sig')))

def export_xlsx(devices):
    from openpyxl import Workbook
    from openpyxl.styles import Font,PatternFill,Alignment
    from openpyxl.utils import get_column_letter
    workbook=Workbook()
    workbook.properties.creator='Área de TI GMP · sistemas@grupomipan.com'
    summary=workbook.active;summary.title='Equipos'
    detail=workbook.create_sheet('Componentes')
    summary.append(['Equipo','Tipo','Sistema','Versión SO','Fabricante','Modelo','CPU','Procesadores','RAM GB','Almacenamiento GB','Recibido UTC','Estado','Número de serie','Service Tag','Asset Tag','Tipo RAM','Tipo disco','Conexión disco','Formato disco','Antivirus detectado','Producto antivirus','Estado antivirus reportado','Office detectado','Tipo / edición Office','Versión Office'])
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
        append(summary,[device['name'],inventory.get('platform',device.get('role','')),data.get('os'),data.get('os_version'),data.get('manufacturer'),data.get('model'),data.get('cpu'),data.get('processors'),gb('ram_bytes'),gb('storage_bytes'),received,'Solicitado' if device.get('pending') else 'Recibido' if inventory else 'Sin auditoría']+[data.get(k,'No disponible') for k in ('serial_number','service_tag','asset_tag','ram_types','disk_types','disk_connections','disk_formats','antivirus_presence','antivirus','antivirus_status','office_presence','office_type','office_version')])
        for component in inventory.get('components',[]):
            if not isinstance(component,dict):continue
            values=component.get('data') or {}
            if not isinstance(values,dict):continue
            for key,value in values.items():append(detail,[device['name'],component.get('category',''),key,value])
        for error in inventory.get('errors',[]):append(detail,[device['name'],'Dato no disponible','Detalle',error])
        if inventory.get('platform')=='Windows' and inventory.get('schema_version',0)<2:
            append(detail,[device['name'],'Diagnóstico','Reporte anterior','Actualizar el EXE e iniciar impresión para recibir automáticamente la auditoría ampliada.'])
        for key,value in inventory.get('field_status',{}).items():append(detail,[device['name'],'Diagnóstico',key,value])
        if inventory.get('collector_version'):append(detail,[device['name'],'Diagnóstico','Versión del agente',inventory['collector_version']])
    for sheet in workbook:
        sheet.freeze_panes='A2';sheet.auto_filter.ref=sheet.dimensions
        for cell in sheet[1]:cell.fill=PatternFill('solid',fgColor='123458');cell.font=Font(color='FFFFFF',bold=True)
        for i,column in enumerate(sheet.columns,1):
            sheet.column_dimensions[get_column_letter(i)].width=min(65,max(15,max(len(str(c.value or '')) for c in column)+2))
        for row in sheet.iter_rows(min_row=2):
            for cell in row:cell.alignment=Alignment(vertical='top',wrap_text=True)
    output=io.BytesIO();workbook.save(output);return output.getvalue()
