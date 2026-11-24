"""Small bounded IPP/1.1-2.0 codec, used only by the loopback Windows bridge."""
import struct
import uuid

def decode(data):
    if len(data)<9 or data[0] not in (1,2):raise ValueError('IPP inválido.')
    operation,request=struct.unpack_from('>HI',data,2);offset=8;attributes={};last='';group=0;count=0
    while offset<len(data):
        tag=data[offset];offset+=1
        if tag==3:return operation,request,attributes,data[offset:]
        if tag<0x10:group=tag;last='';continue
        if offset+2>len(data):raise ValueError('IPP truncado.')
        length=struct.unpack_from('>H',data,offset)[0];offset+=2
        if offset+length+2>len(data):raise ValueError('IPP truncado.')
        name=data[offset:offset+length].decode('utf-8');offset+=length
        length=struct.unpack_from('>H',data,offset)[0];offset+=2
        if offset+length>len(data):raise ValueError('IPP truncado.')
        value=data[offset:offset+length];offset+=length;count+=1
        if count>4096 or offset>65536:raise ValueError('Atributos IPP demasiado grandes.')
        if name:last=name
        if tag in (0x21,0x23) and len(value)==4:value=struct.unpack('>i',value)[0]
        elif tag==0x22 and len(value)==1:value=bool(value[0])
        elif tag in (0x41,0x42,0x44,0x45,0x47,0x48,0x49):value=value.decode('utf-8')
        # Store simple top-level attributes; collections are retained as opaque records.
        if name:attributes.setdefault(last,[]).append(value)
    raise ValueError('Falta fin de atributos IPP.')

def value(tag,item):
    if tag in (0x21,0x23):return struct.pack('>i',int(item))
    if tag==0x22:return bytes([bool(item)])
    if tag==0x33:return struct.pack('>ii',*item)
    if tag==0x32:return struct.pack('>iiB',*item)
    return item if isinstance(item,bytes) else str(item).encode('utf-8')

def attribute(name,tag,items):
    if not isinstance(items,list):items=[items]
    out=bytearray()
    for index,item in enumerate(items):
        key=name.encode('utf-8') if index==0 else b'';data=value(tag,item)
        out.extend(bytes([tag])+struct.pack('>H',len(key))+key+struct.pack('>H',len(data))+data)
    return bytes(out)

def response(request,status=0,groups=(),message=None):
    data=bytearray(struct.pack('>BBHI',2,0,status,request));data.append(1)
    data.extend(attribute('attributes-charset',0x47,'utf-8'));data.extend(attribute('attributes-natural-language',0x48,'en'))
    if message:data.extend(attribute('status-message',0x41,str(message)[:500]))
    for delimiter,attrs in groups:
        data.append(delimiter)
        for name,tag,items in attrs:data.extend(attribute(name,tag,items))
    data.append(3);return bytes(data)

def collection(members):
    data=bytearray()
    for name,tag,item in members:
        data.extend(attribute('',0x4a,name));data.extend(attribute('',tag,item))
    data.extend(attribute('',0x37,b''));return bytes(data)

def printer_attributes(printer,url,display=None):
    media=['iso_a4_210x297mm','na_letter_8.5x11in','oe_ticket80_80x200mm','oe_ticket58_58x200mm']
    media_collections=[]
    for name,width,height in [(media[0],21000,29700),(media[1],21590,27940),(media[2],8000,20000),(media[3],5800,20000)]:
        size=collection([('x-dimension',0x21,width),('y-dimension',0x21,height)])
        # collection() includes its end tag; the begin tag is emitted explicitly below.
        members=attribute('',0x4a,'media-size')+attribute('',0x34,b'')+size
        members+=attribute('',0x4a,'media-size-name')+attribute('',0x44,name)
        for margin in ('top','bottom','left','right'):members+=attribute('',0x4a,'media-'+margin+'-margin')+attribute('',0x21,0)
        members+=attribute('',0x37,b'');media_collections.append(members)
    name=(display or 'PRINTER-TAB - '+printer['pc']+' - '+printer['name']).encode('utf-8')[:250].decode('utf-8',errors='ignore')
    result=[('printer-uri-supported',0x45,url),('uri-authentication-supported',0x44,'none'),('uri-security-supported',0x44,'none'),
        ('printer-name',0x42,name),('printer-info',0x41,name),('printer-location',0x41,'PRINTER-TAB'),('printer-make-and-model',0x41,'GMP PRINTER-TAB'),
        ('printer-uuid',0x45,'urn:uuid:'+str(uuid.uuid5(uuid.NAMESPACE_URL,url))),('ipp-versions-supported',0x44,['1.1','2.0']),
        ('operations-supported',0x23,[2,4,5,6,8,9,10,11]),('charset-configured',0x47,'utf-8'),('charset-supported',0x47,'utf-8'),
        ('natural-language-configured',0x48,'en'),('generated-natural-language-supported',0x48,['en','es']),
        ('document-format-default',0x49,'application/pdf'),('document-format-supported',0x49,['application/pdf','image/pwg-raster','image/jpeg']),
        ('compression-supported',0x44,'none'),('printer-is-accepting-jobs',0x22,True),('printer-state',0x23,3),('printer-state-reasons',0x44,'none'),
        ('queued-job-count',0x21,0),('color-supported',0x22,True),('copies-default',0x21,1),('copies-supported',0x33,(1,20)),
        ('media-supported',0x44,media),('media-ready',0x44,media),('media-default',0x44,media[0]),
        ('printer-resolution-default',0x32,(300,300,3)),('printer-resolution-supported',0x32,(300,300,3)),
        ('pwg-raster-document-resolution-supported',0x32,(300,300,3)),('pwg-raster-document-type-supported',0x44,['black_1','sgray_8','srgb_8']),
        ('pwg-raster-document-sheet-back',0x44,'normal'),('sides-default',0x44,'one-sided'),('sides-supported',0x44,'one-sided'),
        ('print-color-mode-default',0x44,'color'),('print-color-mode-supported',0x44,['auto','color','monochrome']),
        ('print-quality-default',0x23,4),('print-quality-supported',0x23,4),('page-ranges-supported',0x22,False),
        ('orientation-requested-default',0x23,3),('orientation-requested-supported',0x23,[3,4,5,6]),
        ('multiple-document-jobs-supported',0x22,False),('job-creation-attributes-supported',0x44,['copies','media','print-color-mode','sides','printer-resolution']),
        ('job-k-octets-supported',0x33,(0,64*1024)),('printer-up-time',0x21,1)]
    result.extend([('media-source-default',0x44,'auto'),('media-source-supported',0x44,'auto'),('media-type-default',0x44,'stationery'),('media-type-supported',0x44,'stationery'),
        ('media-col-supported',0x44,['media-size','media-size-name','media-top-margin','media-bottom-margin','media-left-margin','media-right-margin']),
        ('finishings-default',0x23,3),('finishings-supported',0x23,3),('number-up-default',0x21,1),('number-up-supported',0x21,1),
        ('job-hold-until-default',0x44,'no-hold'),('job-hold-until-supported',0x44,'no-hold'),('job-sheets-default',0x44,'none'),('job-sheets-supported',0x44,'none')])
    # IPP collections need a zero-length beginCollection followed by member records.
    extra=bytearray()
    for key,collections in [('media-col-database',media_collections),('media-col-default',media_collections[:1]),('media-col-ready',media_collections)]:
        for index,item in enumerate(collections):extra.extend(attribute(key if index==0 else '',0x34,b'')+item)
    return result,bytes(extra)
