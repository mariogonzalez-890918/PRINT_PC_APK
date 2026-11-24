import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pc'))
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'.build'/'test-libs'))
from pypdf import PdfReader
from pwg_raster import pages,convert

def header(width=3,height=2,bits=8,pixel_bits=24,space=19):
    data=bytearray(1796);data[:9]=b'PwgRaster'
    for offset,value in [(276,300),(280,300),(372,width),(376,height),(384,bits),(388,pixel_bits),(392,(width*pixel_bits+7)//8),(396,0),(400,space),(420,3 if pixel_bits==24 else 1)]:struct.pack_into('>I',data,offset,value)
    return bytes(data)

class PwgTest(unittest.TestCase):
    def test_rgb_repetition_and_gray_black_polarity(self):
        image=list(pages(io.BytesIO(b'RaS2'+header()+b'\x01\x02\xff\xff\xff')))[0]
        self.assertEqual((3,2),image.size);self.assertEqual((255,255,255),image.getpixel((2,1)));image.close()
        for space,expected in [(18,255),(3,0)]:
            image=list(pages(io.BytesIO(b'RaS2'+header(8,2,1,1,space)+b'\x01\x00\xaa')))[0]
            self.assertEqual((expected,)*3,image.getpixel((0,0)));image.close()
    def test_literal_color_runs_and_bad_rle_are_bounded(self):
        data=b'RaS2'+header(2,1)+b'\x00\xff\xff\x00\x00\x00\xff\x00'
        image=list(pages(io.BytesIO(data)))[0]
        self.assertEqual((255,0,0),image.getpixel((0,0)));self.assertEqual((0,255,0),image.getpixel((1,0)));image.close()
        for payload in [b'RaS2'+header()+b'\x02\x02\xff\xff\xff',b'RaS2'+header()+b'\x00\x80',b'RaS2'+header(20000,20000),b'RaS2'+b'truncated',b'RaS2']:
            with self.assertRaises(ValueError):list(pages(io.BytesIO(payload)))
    def test_multi_page_pdf_is_readable_and_preserves_page_sizes(self):
        data=b'RaS2'+header()+b'\x01\x02\xff\xff\xff'+header(6,1)+b'\x00\x05\x00\x00\x00'
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/'source.pwg';target=Path(folder)/'out.pdf';source.write_bytes(data);convert(source,target)
            pdf=PdfReader(target);self.assertEqual(2,len(pdf.pages))
            self.assertAlmostEqual(.72,float(pdf.pages[0].mediabox.width),places=3)
            self.assertAlmostEqual(1.44,float(pdf.pages[1].mediabox.width),places=3)
            self.assertTrue(pdf.pages[0].images[0].data)

if __name__=='__main__':unittest.main()
