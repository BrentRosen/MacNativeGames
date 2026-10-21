"""Controller artwork on synthetic BNTX metadata; never uses game content."""
import hashlib
import io
import struct
import tempfile
import sys
import unittest
from unittest.mock import patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'games/totk/scripts'))
import controller_pictures as pictures
from PIL import Image


def archive():
    names = [f'{prefix}{kind}{state}^{suffix}' for prefix,suffix in (('Controller_','w'),('ControllerSh_','s'))
             for kind in ('Console','Grip','Pro') for state in ('','1')] + ['Unrelated']
    data = bytearray(0x2000); data[:8] = b'BNTX\0\0\0\0'; data[12:14] = b'\xff\xfe'
    struct.pack_into('<IQ', data, 0x24, len(names), 0x80)
    name_at = 0xc00; regions = []
    for i,name in enumerate(names):
        at = 0x200+i*0xa0; ptr = 0x1800+i*8
        struct.pack_into('<Q', data, 0x80+i*8, at); data[at:at+4] = b'BRTI'
        data[at+0x16:at+0x18] = b'\x01\0'
        shadow = name.startswith('ControllerSh_')
        fmt,w,h,tile,size = (0x1d01,314,360,4,0x14000) if shadow else (0x2d06,580,340,3,0x4a000)
        struct.pack_into('<I',data,at+0x1c,fmt); struct.pack_into('<5I',data,at+0x24,w,h,1,1,tile)
        struct.pack_into('<I',data,at+0x50,size); struct.pack_into('<Q',data,at+0x60,name_at)
        struct.pack_into('<Q',data,at+0x70,ptr); struct.pack_into('<Q',data,ptr,len(data))
        encoded = name.encode(); struct.pack_into('<H',data,name_at,len(encoded))
        data[name_at+2:name_at+3+len(encoded)] = encoded+b'\0'; name_at += 3+len(encoded)
        lo=len(data);data.extend(b'\xa5'*size);regions.append((at,lo,len(data),name))
    return bytes(data), regions


class ControllerPictures(unittest.TestCase):
    def test_artwork_replaces_every_controller_state_and_preserves_other_assets(self):
        original,regions = archive()
        for style in ('keyboard','xbox','playstation'):
            out = pictures.replace_textures(original,style,Image.new('RGBA',(32,24),(35,80,140,255)))
            restored = bytearray(out)
            for at,lo,hi,name in regions:
                if name == 'Unrelated':
                    self.assertEqual(out[lo:hi],original[lo:hi]);continue
                self.assertNotEqual(out[lo:hi],original[lo:hi])
                if name.startswith('ControllerSh_'):
                    self.assertEqual(out[lo:hi],bytes(hi-lo))
                else:
                    self.assertEqual(struct.unpack_from('<I',out,at+0x1c)[0],0x1c06)
                restored[lo:hi] = original[lo:hi]
                restored[at+0x1c:at+0x20] = original[at+0x1c:at+0x20]
            self.assertEqual(bytes(restored),original)

    def test_unknown_source_geometry_is_rejected(self):
        data,regions = archive();data=bytearray(data)
        struct.pack_into('<I',data,regions[0][0]+0x24,581)
        with self.assertRaises(AssertionError): pictures.replace_textures(data,'xbox')

    def test_switch_connectors_are_hidden_without_removing_labels(self):
        layout = bytearray(20)
        layout[:6] = b'FLYT\xff\xfe'; struct.pack_into('<H',layout,6,20);struct.pack_into('<H',layout,16,2)
        for magic,name in ((b'pan1',b'N_Line_00'),(b'txt1',b'ActionLabel')):
            section = bytearray(84);section[:4] = magic;struct.pack_into('<I',section,4,84)
            section[8] = 3;section[12:12+len(name)] = name;layout.extend(section)
        out = pictures.replace_callouts(bytes(layout))
        self.assertEqual(out[28],2)
        self.assertEqual(out[:28]+out[29:],layout[:28]+layout[29:])

    def test_xbox_rgb_and_transparency_survive_texture_encoding(self):
        image = Image.new('RGBA',(8,4),(15,90,220,255))
        for y in range(4):
            for x in range(4): image.putpixel((x,y),(230,20,30,0 if x==0 else 255))
        decoded = Image.frombytes('RGBA',image.size,pictures.color_bc3(image),'bcn',3)
        red,blue = decoded.getpixel((2,2)),decoded.getpixel((6,2))
        self.assertGreater(red[0],180);self.assertLess(red[2],60)
        self.assertGreater(blue[2],180);self.assertLess(blue[0],60)
        self.assertEqual(decoded.getpixel((0,2))[3],0)
        self.assertEqual(blue[3],255)

    def test_official_image_is_verified_and_reused_without_network(self):
        image = Image.new('RGBA',(1200,1200),(20,30,40,255));out=io.BytesIO();image.save(out,format='PNG')
        data=out.getvalue();digest=hashlib.sha256(data).hexdigest()
        with tempfile.TemporaryDirectory() as cache, patch.dict(pictures.PRODUCT_ARTWORK,
                {'xbox': {'url': 'https://example.invalid/controller.png', 'sha256': digest, 'size': (1200,1200)}}):
            with patch.object(pictures.urllib.request,'urlopen',return_value=io.BytesIO(data)) as fetch:
                self.assertEqual(pictures.load_controller_artwork('xbox',cache).size,(1200,1200))
                fetch.assert_called_once()
            with patch.object(pictures.urllib.request,'urlopen',side_effect=AssertionError('unexpected download')):
                self.assertEqual(pictures.load_controller_artwork('xbox',cache).getpixel((10,10)),(20,30,40,255))
                (Path(cache)/f'xbox-{digest}.png').write_bytes(b'changed')
                with self.assertRaisesRegex(ValueError,'hash differs'): pictures.load_controller_artwork('xbox',cache)

    def test_xbox_has_no_procedural_placeholder_fallback(self):
        for style in ('xbox','playstation'):
            with self.assertRaisesRegex(ValueError,'official .* product image'):
                pictures.drawing(style)

    def test_compressed_coverage_decodes(self):
        alpha = [0,36,73,109,146,182,219,255]*2
        block = pictures.bc3_block([(255,255,255,a) for a in alpha])
        decoded = Image.frombytes('RGBA',(4,4),block,'bcn',3)
        for i,expected in enumerate(alpha):
            pixel = decoded.getpixel((i%4,i//4))
            self.assertEqual(pixel[:3],(255,255,255)); self.assertLessEqual(abs(pixel[3]-expected),1)


if __name__ == '__main__': unittest.main()
