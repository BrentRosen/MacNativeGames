"""Controller artwork on synthetic BNTX metadata; never uses game content."""
import struct
import sys
import unittest
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
            out = pictures.replace_textures(original,style)
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

    def test_compressed_coverage_decodes(self):
        alpha = [0,36,73,109,146,182,219,255]*2
        block = pictures.bc3_block([(255,255,255,a) for a in alpha])
        decoded = Image.frombytes('RGBA',(4,4),block,'bcn',3)
        for i,expected in enumerate(alpha):
            pixel = decoded.getpixel((i%4,i//4))
            self.assertEqual(pixel[:3],(255,255,255)); self.assertLessEqual(abs(pixel[3]-expected),1)


if __name__ == '__main__': unittest.main()
