"""Bounded PWG 5102.4 raster -> PDF conversion in an isolated worker process."""
import io
from pathlib import Path
import struct
import sys
import zlib

def exact(stream,count):
    data=stream.read(count)
    if len(data)!=count:raise ValueError('Documento PWG truncado.')
    return data

def pages(stream):
    from PIL import Image,ImageOps
    if exact(stream,4)!=b'RaS2':raise ValueError('Formato PWG no admitido.')
    pixels=0;count=0
    while True:
        header=stream.read(1796)
        if not header:break
        if len(header)!=1796:raise ValueError('Cabecera PWG truncada.')
        def number(offset):return struct.unpack_from('>I',header,offset)[0]
        width,height=number(372),number(376);bpc,bpp=number(384),number(388)
        row_size,order,space=number(392),number(396),number(400)
        dpi=(number(276),number(280));pixels+=width*height;count+=1
        if not width or not height or width>20000 or height>30000 or width*height>25_000_000 or count>100:
            raise ValueError('El documento raster excede los límites de tamaño/páginas.')
        if dpi!=(300,300) or order!=0 or row_size!=(width*bpp+7)//8:
            raise ValueError('Resolución o distribución raster no admitida; usa 300 dpi.')
        if not ((bpc,bpp,space) in ((1,1,3),(1,1,18),(8,8,3),(8,8,18),(8,24,1),(8,24,19))):
            raise ValueError('Tipo de color raster no admitido.')
        unit=max(1,bpp//8);decoded=bytearray();rows=0
        while rows<height:
            repeat=exact(stream,1)[0]+1;line=bytearray()
            if rows+repeat>height:raise ValueError('Repetición de línea PWG inválida.')
            while len(line)<row_size:
                control=exact(stream,1)[0]
                if control<=127:chunk=exact(stream,unit)*(control+1)
                elif control>=129:chunk=exact(stream,unit*(257-control))
                else:raise ValueError('Código PWG reservado.')
                if len(line)+len(chunk)>row_size:raise ValueError('Línea PWG fuera de límites.')
                line.extend(chunk)
            decoded.extend(line*repeat);rows+=repeat
        mode='1' if bpp==1 else 'L' if bpp==8 else 'RGB'
        image=Image.frombytes(mode,(width,height),bytes(decoded))
        del decoded
        if space==3:image=ImageOps.invert(image.convert('L'))
        if image.mode!='RGB':
            converted=image.convert('RGB');image.close();image=converted
        yield image
    if not count:raise ValueError('Documento PWG sin páginas.')

def convert(source,target):
    # Emit one lossless image-backed PDF page at a time so long documents do not retain
    # every uncompressed raster page in memory.
    with open(source,'rb') as stream,open(target,'wb') as output:
        output.write(b'%PDF-1.4\n%\xe2\xe3\xcf\xd3\n');offsets={};children=[]
        def obj(number,content):
            offsets[number]=output.tell();output.write(str(number).encode()+b' 0 obj\n'+content+b'\nendobj\n')
        for index,image in enumerate(pages(stream)):
            page,image_id,content_id=3+index*3,4+index*3,5+index*3
            try:
                bitmap=zlib.compress(image.tobytes(),6)
                width,height=image.size;w,h=width*72/300,height*72/300
                draw=('q %.4f 0 0 %.4f 0 0 cm /Im0 Do Q'%(w,h)).encode()
                obj(image_id,('<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length %d >>\nstream\n'%(width,height,len(bitmap))).encode()+bitmap+b'\nendstream')
                obj(content_id,('<< /Length %d >>\nstream\n'%len(draw)).encode()+draw+b'\nendstream')
                obj(page,('<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %.4f %.4f] /Resources << /XObject << /Im0 %d 0 R >> >> /Contents %d 0 R >>'%(w,h,image_id,content_id)).encode());children.append(page)
            finally:image.close()
            if output.tell()>25*1024*1024:raise ValueError('Documento convertido mayor de 25 MB.')
        obj(1,b'<< /Type /Catalog /Pages 2 0 R >>')
        obj(2,('<< /Type /Pages /Count %d /Kids [%s] >>'%(len(children),' '.join(str(p)+' 0 R' for p in children))).encode())
        start=output.tell();total=max(offsets)+1;output.write(('xref\n0 %d\n0000000000 65535 f \n'%total).encode())
        for number in range(1,total):output.write(('%010d 00000 n \n'%offsets[number]).encode())
        output.write(('trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n'%(total,start)).encode())

if __name__=='__main__':
    try:convert(sys.argv[1],sys.argv[2])
    except Exception as error:print(str(error));sys.exit(1)
