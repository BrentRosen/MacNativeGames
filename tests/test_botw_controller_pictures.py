"""Synthetic BotW BNTX storage and pack-budget guards; no player assets."""
import importlib.util
from pathlib import Path
import struct
import unittest
import zlib
try:
    from PIL import Image
except ImportError:
    raise unittest.SkipTest('controller artwork needs Pillow')
SCRIPT=Path(__file__).resolve().parents[1]/'games/botw/scripts/controller_pictures.py'
spec=importlib.util.spec_from_file_location('botw_controller_art',SCRIPT)
art=importlib.util.module_from_spec(spec);spec.loader.exec_module(art)


def textures():
    b=bytearray(4096);b[:8]=b'BNTX\0\0\0\0';struct.pack_into('<IQ',b,36,3,128);regions=[]
    for i,(name,w,h,size) in enumerate((('Nt_NNillust_00^f',576,288,442368),('Nt_NNillust_01^f',576,100,147456),('Unrelated',16,16,4096))):
        p=512+i*160;struct.pack_into('<Q',b,128+8*i,p);b[p:p+4]=b'BRTI'
        struct.pack_into('<I',b,p+28,0x901);struct.pack_into('<5I',b,p+36,w,h,1,1,4)
        struct.pack_into('<I',b,p+80,size);n=1100+i*64;struct.pack_into('<Q',b,p+96,n)
        struct.pack_into('<H',b,n,len(name));b[n+2:n+3+len(name)]=name.encode()+b'\0'
        ptr=1400+i*8;struct.pack_into('<Q',b,p+112,ptr);struct.pack_into('<Q',b,ptr,len(b))
        lo=len(b);b.extend(b'\xa5'*size);regions.append((p,lo,len(b),name))
    return bytes(b),regions


def layout_fixture():
    parts=[];names=set()
    def add(name,magic=b'pan1',x=0,y=0,sx=1):
        names.add(name);p=bytearray(140 if magic==b'pic1' else 84);p[:4]=magic
        struct.pack_into('<I',p,4,len(p));p[8]=3;p[12:12+len(name)]=name.encode()
        struct.pack_into('<10f',p,44,x,y,0,0,0,0,sx,1,10,10);parts.append(bytes(p))
    def section(magic):return magic+struct.pack('<I',8)
    add('RootPane');parts.append(section(b'pas1'))
    add('P_NNillust_00',b'pic1',y=-10)
    for n in ('N_CrossKey_00','N_CrossKey_01','N_CrossKey_02','W_Base_02','T_Icon_16','T_Lstick_00','T_Lstick_01',
              'T_Lstick_02','T_Lstick_03','T_Lstick_06','T_Icon_04','T_Icon_05','T_Icon_06',
              'T_Lstick_04','T_Lstick_05','T_Icon_07','T_Icon_08'):
        add(n)
    for num,key in art.LINE_KEYS.items():
        group=f'N_Line_{num:02d}';add(group,x=19,y=-7,sx=-1 if num%2 else 1)
        parts.append(section(b'pas1'))
        for k in range(4):add(f'Line{num}_{k}',b'pic1')
        parts.append(section(b'pae1'))
    parts.append(section(b'pae1'))
    header=bytearray(20);header[:6]=b'FLYT\xff\xfe';struct.pack_into('<H',header,6,20)
    return bytes(header)+b''.join(parts)


class BotwControllerPictures(unittest.TestCase):
    def test_yaz0_matches_roundtrip_and_compresses_repeated_content(self):
        header=b'Yaz0'+bytes(4)+b'align123'
        for b in (b'a',b'abcd'*1500,bytes(range(256))*32,b'abcabcXabcabcY'*350):
            out=art.compress_yaz0(b,header)
            self.assertEqual(art.yaz0(out),b);self.assertEqual(out[8:16],header[8:16])
            if len(b)>10:self.assertLess(len(out),len(b))

    def test_textures_keep_storage_and_unrelated_assets(self):
        source,regions=textures()
        for style in ('xbox','playstation','keyboard'):
            out=art.replace_textures(source,style);restored=bytearray(out)
            for p,lo,hi,name in regions:
                if name=='Unrelated':self.assertEqual(out[lo:hi],source[lo:hi]);continue
                self.assertEqual(struct.unpack_from('<I',out,p+28)[0],0x1c01)
                restored[lo:hi]=source[lo:hi];restored[p+28:p+32]=source[p+28:p+32]
                restored[p+52:p+56]=source[p+52:p+56]
                self.assertEqual(struct.unpack_from('<I',out,p+88)[0],0x05040302)
                restored[p+88:p+92]=source[p+88:p+92]
                w,h,_,_,tile=struct.unpack_from('<5I',out,p+36);row=w//4*16
                raw=b''.join(out[lo+art.block_offset(x*16,y,row,tile&7):lo+art.block_offset(x*16,y,row,tile&7)+16]
                             for y in range((h+3)//4) for x in range(w//4))
                image=Image.frombytes('RGBA',(w,h),raw,'bcn',3)
                self.assertEqual(image.getpixel((0,0))[3],0)
                if h==100 and style=='keyboard':self.assertIsNone(image.getbbox())
                else:self.assertIsNotNone(image.getbbox())
            self.assertEqual(bytes(restored),source)

    def test_unknown_texture_geometry_refused(self):
        source,regions=textures();source=bytearray(source);struct.pack_into('<I',source,regions[0][0]+36,575)
        with self.assertRaises(AssertionError):art.replace_textures(bytes(source),'xbox')

    def test_callout_dots_follow_drawn_controls_in_both_layouts(self):
        source=layout_fixture()
        for style in ('xbox','playstation'):
            out,edits=art.replace_layout(source,style);nodes,parents=art.panes(out)
            def world(name):
                x,y,_,_,_,_,sx,sy,*_=struct.unpack_from('<10f',out,nodes[name]+44)
                if parents[name]:
                    px,py,psx,psy=world(parents[name]);return px+x*psx,py+y*psy,sx*psx,sy*psy
                return x,y,sx,sy
            for num,key in art.LINE_KEYS.items():
                if key in ('ZL','ZR','L','R'):
                    px,py={'ZL':(174,22),'ZR':(406,22),'L':(142,66),'R':(438,66)}[key]
                    expected=((px-288)*.67,-194+(50-py)*.67)
                else:
                    px,py=art.DIAGRAM_ANCHORS[style][key];expected=((px-290)*.67,-10+(170-py)*.67)
                x,y,_,_=world(f'Line{num}_2')
                self.assertAlmostEqual(x,expected[0],places=4);self.assertAlmostEqual(y,expected[1],places=4)
                self.assertEqual(struct.unpack_from('<f',out,nodes[f'Line{num}_3']+76)[0],0)
            self.assertIn(('P_NNillust_00',9),edits)
        out,_=art.replace_layout(source,'keyboard');nodes,_=art.panes(out)
        for name,at in nodes.items():
            if name.startswith('Line'):self.assertFalse(out[at+8]&1)

    def test_pack_growth_is_only_allowed_without_fixed_resource_budget(self):
        art.verify_pack_budget(b'RSTB'+struct.pack('<II',1,0)+struct.pack('<II',123,1000))
        with self.assertRaisesRegex(AssertionError,'fixed resource budget'):
            art.verify_pack_budget(b'RSTB'+struct.pack('<II',1,0)+struct.pack('<II',zlib.crc32(b'Pack/Bootup.pack'),1000))
        with self.assertRaisesRegex(AssertionError,'fixed named'):
            art.verify_pack_budget(b'RSTB'+struct.pack('<II',0,1)+b'Pack/Bootup.pack'.ljust(128,b'\0')+struct.pack('<I',1000))
