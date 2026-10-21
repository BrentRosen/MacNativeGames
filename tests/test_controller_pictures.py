"""Controller artwork on synthetic BNTX metadata; never uses game content."""
import io
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


def callout_layout():
    """Synthetic native pane geometry and its parent graph; no copyrighted layout data."""
    nodes=[];parents={}
    def add(name,parent=None,x=0,y=0,sx=1,w=30,h=40,magic=b'pan1'):
        part=bytearray(84);part[:4]=magic;struct.pack_into('<I',part,4,84);part[8]=3
        part[12:12+len(name)]=name.encode();struct.pack_into('<10f',part,44,x,y,0,0,0,0,sx,1,w,h)
        nodes.append(part);parents[name]=parent
    add('N_CapGuide_00');add('N_Line_00','N_CapGuide_00',y=68)
    add('Pa_Controller_00',y=-7);add('ActionLabel',magic=b'txt1')
    for key,y in (('ZL',139),('L',67),('Minus',-5),('LStick',-77),('CrossKey',-193),
                  ('ZR',105),('R',55),('Plus',5),('ABXY',-108),('RStick',-243)):
        left=key in ('ZL','L','Minus','LStick','CrossKey');sign=1 if left else -1
        add('N_'+key+'_00',y=y)
        parent='N_Line_00';x=-295 if left else 295
        if key in ('LStick','CrossKey'):
            add('N_IsHorse_'+key+'_00',parent,x,y);parent='N_IsHorse_'+key+'_00';x=y=0
        line='P_Line'+key+'_00';add(line,parent,x,y,sign,magic=b'pic1');parent=line
        if key in ('LStick','CrossKey'):
            add('N_IsHorse_'+key+'_01',parent);parent='N_IsHorse_'+key+'_01'
        horizon='P_Horizon'+key+'_00';add(horizon,parent,w=60,h=3,magic=b'pic1')
        vertical=('P_VertiL' if key in ('CrossKey','ABXY') else 'P_Verti')+key+'_00'
        add(vertical,horizon,x=60,w=3,h=30,magic=b'pic1')
        grouped=key in ('CrossKey','ABXY');endpoint=('W_Circle' if grouped else 'P_Circle')+key+'_00'
        add(endpoint,horizon if key in ('Minus','Plus') else vertical,magic=b'wnd1' if grouped else b'pic1')
    def document(parts):
        head=bytearray(20);head[:6]=b'FLYT\xff\xfe';struct.pack_into('<H',head,6,20)
        struct.pack_into('<H',head,16,len(parts));return bytes(head)+b''.join(parts)
    source=document(nodes)
    part=bytearray(84);part[:4]=b'pic1';struct.pack_into('<I',part,4,84);part[12:27]=b'P_Controller_00'
    struct.pack_into('<10f',part,44,0,-20,0,0,0,0,1,1,580,340)
    return source,document([part]),parents


def animation(entries):
    """A minimal BFLAN with Hermite transform tracks, independently assembled."""
    pai=bytearray(20+4*len(entries));pai[:4]=b'pai1';struct.pack_into('<H',pai,14,len(entries));struct.pack_into('<I',pai,16,20)
    for index,(name,prop,values) in enumerate(entries):
        struct.pack_into('<I',pai,20+index*4,len(pai))
        content=bytearray(36);content[:len(name)]=name.encode();content[28]=1;struct.pack_into('<I',content,32,36)
        tag=bytearray(12);tag[:4]=b'FLPA';tag[4]=1;struct.pack_into('<I',tag,8,12)
        group=bytearray(12);group[1]=prop;group[2]=2;struct.pack_into('<H',group,4,len(values));struct.pack_into('<I',group,8,12)
        pai+=content+tag+group+b''.join(struct.pack('<fff',float(i),value,3) for i,value in enumerate(values))
    struct.pack_into('<I',pai,4,len(pai))
    head=bytearray(20);head[:6]=b'FLAN\xff\xfe';struct.pack_into('<H',head,6,20);struct.pack_into('<H',head,16,1)
    return bytes(head+pai)


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
        out,_ = pictures.replace_callouts(bytes(layout),'keyboard')
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

    def test_flat_diagrams_have_correct_canvas_and_stick_locations(self):
        for style in ('xbox','playstation'):
            image=pictures.drawing(style)
            self.assertEqual(image.size,(580,340));self.assertEqual(image.getpixel((0,0))[3],0)
            self.assertEqual(image.tobytes(),pictures.drawing(style).tobytes())
            for key in ('LStick','RStick'):
                x,y=pictures.DIAGRAM_ANCHORS[style][key]
                r,g,b,a=image.getpixel((round(x),round(y)))
                self.assertEqual(a,255);self.assertEqual(r,g);self.assertEqual(g,b)
                self.assertTrue(80<=r<=100)

    def test_native_endpoint_geometry_and_playstation_label_order(self):
        source,child,parents=callout_layout()
        for style in ('xbox','playstation'):
            out,edits=pictures.replace_callouts(source,style,child);panes=pictures.layout_panes(out)
            def properties(name):return struct.unpack_from('<10f',out,panes[name]+44)
            def world(name):
                x,y,_,_,_,_,sx,sy,*_=properties(name)
                if parents[name]:
                    px,py,psx,psy=world(parents[name]);return px+x*psx,py+y*psy,sx*psx,sy*psy
                return x,y,sx,sy
            for key,(x,y) in pictures.DIAGRAM_ANCHORS[style].items():
                grouped=key in ('CrossKey','ABXY')
                endpoint=('W_Circle' if grouped else 'P_Circle')+key+'_00'
                ex,ey,_,_=world(endpoint)
                self.assertAlmostEqual(ex,x-290,places=4)
                self.assertAlmostEqual(ey,143-y,places=4)
                self.assertEqual(out[panes[endpoint]+9],0)
            ls=properties('N_LStick_00')[1];cross=properties('N_CrossKey_00')[1]
            self.assertEqual(ls<cross,style=='playstation')
            self.assertTrue(out[panes['N_Line_00']+8]&1)
            self.assertEqual(out[panes['ActionLabel']:panes['ActionLabel']+84],source[panes['ActionLabel']:panes['ActionLabel']+84])

    def test_animation_modes_cannot_restore_switch_endpoints(self):
        data=animation([('P_HorizonZL_00',8,[77,200,200]),('Unrelated',0,[1,2,3])])
        out=pictures.replace_callout_animation(data,{('P_HorizonZL_00',8):121},'xbox')
        for name,magic,prop,curve,keys in pictures.animation_tracks(out):
            self.assertEqual([struct.unpack_from('<f',out,k)[0] for k in keys],[0,1,2])
            values=[struct.unpack_from('<f',out,k+4)[0] for k in keys]
            self.assertEqual(values,[121]*3 if name=='P_HorizonZL_00' else [1,2,3])
            if name=='P_HorizonZL_00':self.assertEqual([struct.unpack_from('<f',out,k+8)[0] for k in keys],[0]*3)

    def test_playstation_horse_rows_swap_curves_with_compensating_offsets(self):
        data=animation([('N_LStick_00',1,[-77,-77,-99]),('N_CrossKey_00',1,[-193,-193,-237]),
                        ('N_IsHorse_LStick_01',1,[0,0,22]),('N_IsHorse_CrossKey_01',1,[0,0,44])])
        out=pictures.replace_callout_animation(data,{('Pa_Controller_00',1):-7},'playstation')
        values={name:[struct.unpack_from('<f',out,k+4)[0] for k in keys]
                for name,_,_,_,keys in pictures.animation_tracks(out)}
        self.assertEqual(values['N_LStick_00'],[-193,-193,-237])
        self.assertEqual(values['N_CrossKey_00'],[-77,-77,-99])
        self.assertEqual(values['N_IsHorse_LStick_01'],[0,0,44])
        self.assertEqual(values['N_IsHorse_CrossKey_01'],[0,0,22])
        self.assertEqual(pictures.replace_callout_animation(data,{('Pa_Controller_00',1):-7},'xbox'),data)

    def test_compressed_coverage_decodes(self):
        alpha = [0,36,73,109,146,182,219,255]*2
        block = pictures.bc3_block([(255,255,255,a) for a in alpha])
        decoded = Image.frombytes('RGBA',(4,4),block,'bcn',3)
        for i,expected in enumerate(alpha):
            pixel = decoded.getpixel((i%4,i//4))
            self.assertEqual(pixel[:3],(255,255,255)); self.assertLessEqual(abs(pixel[3]-expected),1)


if __name__ == '__main__': unittest.main()
