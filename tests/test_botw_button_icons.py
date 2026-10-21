"""Synthetic BotW bitmap fonts: keep texture storage, unrelated glyphs and resource budgets intact."""
import io
import importlib.util
from pathlib import Path
import struct
import unittest
try:
    from PIL import Image
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen
except ImportError:
    raise unittest.SkipTest('optional BotW icon tooling needs Pillow and fonttools')

SCRIPT=Path(__file__).resolve().parents[1]/'games/botw/scripts/make_button_icons.py'
spec=importlib.util.spec_from_file_location('botw_button_icons',SCRIPT)
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)


def font_fixture():
    start=4096;texture=bytearray(start+131072)
    texture[:8]=b'BNTX\0\0\0\0';struct.pack_into('<IQ',texture,0x24,1,128)
    struct.pack_into('<Q',texture,128,256);texture[256:260]=b'BRTI'
    struct.pack_into('<I',texture,256+28,0x1d01)
    struct.pack_into('<5I',texture,256+36,256,1024,1,1,4)
    struct.pack_into('<I',texture,256+80,131072);struct.pack_into('<Q',texture,256+112,512)
    struct.pack_into('<Q',texture,512,start)
    texture[start:]=bytes((255,255,0,0,0,0,0,0))*(131072//8)
    data=bytearray(4096);data[:6]=b'FFNT\xff\xfe';struct.pack_into('<H',data,6,20)
    data[20:24]=b'TGLP';struct.pack_into('<I',data,24,4096+len(texture)-20)
    struct.pack_into('<BBB',data,28,50,50,1)
    struct.pack_into('<4H',data,40,5,20,256,1024);struct.pack_into('<I',data,48,4096)
    data+=texture
    data+=b'CMAP'+struct.pack('<IIIHHI',26,0xe040,0xe040,1,0,0)+struct.pack('<H',0)
    return bytes(data)


def shared_font_fixture():
    order=['.notdef']+[f'u{cp}' for cp in range(32,127)]
    fb=FontBuilder(1000,isTTF=True);fb.setupGlyphOrder(order)
    fb.setupCharacterMap({cp:f'u{cp}' for cp in range(32,127)})
    glyphs={}
    for name in order:
        pen=TTGlyphPen(None);pen.moveTo((0,0));pen.lineTo((0,700));pen.lineTo((500,700));pen.lineTo((500,0));pen.closePath()
        glyphs[name]=pen.glyph()
    fb.setupGlyf(glyphs);fb.setupHorizontalMetrics({name:(600,0) for name in order})
    fb.setupHorizontalHeader(ascent=800,descent=-200)
    fb.setupNameTable({'familyName':'Synthetic','styleName':'Regular'})
    fb.setupOS2(sTypoAscender=800,sTypoDescender=-200,usWinAscent=800,usWinDescent=200);fb.setupPost()
    stream=io.BytesIO();fb.save(stream)
    return mod.icons.bfotf_encode(stream.getvalue(),123)


class BotwButtonIcons(unittest.TestCase):
    def test_all_styles_render_with_truetype_letters_cut_out_of_buttons(self):
        font=shared_font_fixture()
        for style in ('xbox','playstation','keyboard'):
            images=mod.icon_bitmaps(font,style)
            face=images[0xe040]
            self.assertEqual(face.getextrema(),(0,255))
            if style in ('xbox','keyboard'):
                self.assertEqual(face.getpixel((face.width//2,face.height//2)),0)
            if style=='keyboard':
                self.assertNotIn(0xe05c,images);self.assertNotIn(0xe068,images)

    def test_yaz0_roundtrip_and_alignment_metadata(self):
        for size in (1,7,8,9,1025):
            data=bytes(i%256 for i in range(size));header=b'Yaz0'+bytes(4)+b'align123'
            packed=mod.literal_yaz0(data,header)
            self.assertEqual(mod.yaz0(packed),data);self.assertEqual(packed[8:16],header[8:16])

    def test_bc4_coverage(self):
        pixels=[0,255,36,73,109,146,182,219]*2
        decoded=Image.frombytes('L',(4,4),mod.bc4(pixels),'bcn',4)
        self.assertTrue(all(abs(a-b)<=1 for a,b in zip(pixels,decoded.tobytes())))

    def test_patch_preserves_font_size_metadata_and_other_glyph_pixels(self):
        source=font_fixture();bitmap=Image.new('L',(32,32),0)
        for y in range(8,24):
            for x in range(8,24):bitmap.putpixel((x,y),255)
        out,count,preview=mod.patch_font(source,{0xe040:bitmap})
        self.assertEqual(count,1);self.assertEqual(len(out),len(source))
        # Only the existing texture payload can change, not font metrics/cmap/BNTX metadata.
        self.assertEqual(out[:8192],source[:8192]);self.assertEqual(out[8192+131072:],source[8192+131072:])
        linear=b''.join(out[8192+mod.block_offset(x*8,y,512,4):8192+mod.block_offset(x*8,y,512,4)+8]
                        for y in range(256) for x in range(64))
        image=Image.frombytes('L',(256,1024),linear,'bcn',4)
        self.assertEqual(image.getpixel((25,998)),255);self.assertEqual(image.getpixel((2,975)),0)
        self.assertEqual(image.crop((51,0,256,1024)).tobytes(),bytes([255])*(205*1024))
        self.assertEqual(image.crop((0,0,51,973)).tobytes(),bytes([255])*(51*973))
        self.assertEqual(preview.getpixel((2,975)),0)

    def test_cells_store_glyphs_bottom_to_top(self):
        bitmap=Image.new('L',(32,32),0)
        bitmap.paste(255,(0,0,32,8))
        _,_,image=mod.patch_font(font_fixture(),{0xe040:bitmap})
        self.assertEqual(image.getpixel((25,980)),0)
        self.assertEqual(image.getpixel((25,1020)),255)

    def test_unrecognized_font_geometry_is_rejected(self):
        data=bytearray(font_fixture());data[28]=49
        with self.assertRaises(AssertionError):mod.patch_font(bytes(data),{0xe040:Image.new('L',(32,32),255)})
