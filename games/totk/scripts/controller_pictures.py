"""Original flat controller diagrams and native callouts for the Controls screen.

No product photos, third-party mod artwork, or network downloads. The six Console/Grip/Pro textures share a canvas.
BC3 keeps the original BC7 storage size; all other textures and the game's localized action labels stay intact.
"""
import io
import math
import struct
from PIL import Image, ImageDraw, ImageFont


# Coordinates are shared by the vector drawings and native callout placement (580 x 340 canvas).
# They describe a front-facing Xbox pad and a DualShock 4, matching the game's flat, outlined illustration style.
DIAGRAM_ANCHORS = {
    'xbox': {'ZL': (174,12), 'ZR': (406,12), 'L': (142,33), 'R': (438,33),
             'Minus': (230,69), 'Plus': (358,69), 'LStick': (170,112),
             'CrossKey': (226,184), 'ABXY': (414,112), 'RStick': (362,184)},
    'playstation': {'ZL': (150,12), 'ZR': (430,12), 'L': (122,30), 'R': (458,30),
                    'Minus': (207.6,60), 'Plus': (372.4,60), 'LStick': (222,188),
                    'CrossKey': (154,106.4), 'ABXY': (426,106.4), 'RStick': (358,188)},
}
GROUP_RADIUS = {'xbox': {'CrossKey': 39, 'ABXY': 54}, 'playstation': {'CrossKey': 43, 'ABXY': 54}}


def controller_diagram(style, width=580, height=340):
    """Original flat vector illustration: smooth shell contours, dark outlines and neutral grey input details."""
    assert style in DIAGRAM_ANCHORS
    scale = 4; image = Image.new('RGBA', (580*scale,340*scale)); draw = ImageDraw.Draw(image)
    def point(x,y): return ((50+.8*x)*scale,.8*y*scale)
    def line(points, color='#151515', stroke=2):
        draw.line([point(*p) for p in points],fill=color,width=max(1,round(stroke*.8*scale)),joint='curve')
    def path(commands, fill='#393939', stroke=2.5):
        points=[]; current=None
        for command in commands:
            if command[0] in ('M','L'):
                current=command[1:]; points.append(current)
            elif command[0]=='C':
                start=current; a,b,end=command[1:3],command[3:5],command[5:7]
                for i in range(1,33):
                    t=i/32;u=1-t
                    points.append(tuple(u**3*start[j]+3*u*u*t*a[j]+3*u*t*t*b[j]+t**3*end[j] for j in (0,1)))
                current=end
            elif command[0]=='Z': points.append(points[0])
        if fill is not None: draw.polygon([point(*p) for p in points],fill=fill)
        if stroke: line(points,stroke=stroke)
    def oval(x,y,rx,ry=None,fill='#585858',stroke=2):
        ry=rx if ry is None else ry
        draw.ellipse((*point(x-rx,y-ry),*point(x+rx,y+ry)),fill=fill,outline='#151515',width=max(1,round(stroke*.8*scale)))
    def rounded(bounds,radius=8,fill='#242424',stroke=2):
        x0,y0,x1,y1=bounds
        draw.rounded_rectangle((*point(x0,y0),*point(x1,y1)),radius=radius*.8*scale,fill=fill,
                               outline='#151515',width=max(1,round(stroke*.8*scale)))
    def label(x,y,value,size=20,color='#b7b7b7'):
        draw.text(point(x,y),value,font=ImageFont.load_default(size=round(size*.8*scale)),fill=color,anchor='mm')
    def stick(x,y):
        oval(x,y,45,fill='#303030',stroke=3);oval(x,y,36,fill='#595959',stroke=2)
        oval(x,y,31,fill=None,stroke=1)
    def plus(x,y):
        pts=[(-11,-33),(11,-33),(11,-11),(33,-11),(33,11),(11,11),(11,33),(-11,33),(-11,11),(-33,11),(-33,-11),(-11,-11)]
        path([('M',x+pts[0][0],y+pts[0][1]),*[('L',x+a,y+b) for a,b in pts[1:]],('Z',)],fill='#5c5c5c',stroke=2)
        for dx,dy in ((0,-1),(0,1),(-1,0),(1,0)):
            cx,cy=x+dx*23,y+dy*23
            triangle=[(cx+dx*4,cy+dy*4),(cx-dx*3+dy*4,cy-dy*3-dx*4),(cx-dx*3-dy*4,cy-dy*3+dx*4)]
            draw.polygon([point(*p) for p in triangle],fill='#aeaeae')
    # Separate trigger/bumper pods and a curved shoulder rim, rather than the old angular generic silhouette.
    for x in (155,445):
        path([('M',x-48,28),('C',x-42,6,x+35,5,x+45,27),('L',x+44,48),('L',x-47,48),('Z',)],fill='#343434')
    if style=='xbox':
        path([('M',130,30),('C',100,29,76,39,65,66),('C',46,112,33,186,20,265),
              ('C',8,328,18,368,48,387),('C',75,405,111,390,139,351),('L',193,278),
              ('C',210,253,253,252,300,253),('C',347,252,390,253,407,278),('L',461,351),
              ('C',489,390,525,405,552,387),('C',582,368,592,328,580,265),
              ('C',567,186,554,112,535,66),('C',524,39,500,29,470,30),
              ('C',410,23,365,24,300,25),('C',235,24,190,23,130,30),('Z',)],fill='#303030')
        path([('M',72,77),('C',142,44,224,44,300,45),('C',376,44,458,44,528,77),
              ('L',548,162),('C',514,190,474,230,432,286),('C',393,256,366,251,300,253),
              ('C',234,251,207,256,168,286),('C',126,230,86,190,52,162),('Z',)],fill='#3a3a3a',stroke=1.5)
        path([('M',70,69),('C',152,33,229,36,300,36),('C',371,36,448,33,530,69)],fill=None,stroke=2)
        oval(300,65,20,fill='#202020')
        # Xbox sphere/X mark, drawn as four curved lobes rather than a literal letter X in a circle.
        for sign in (-1,1):
            path([('M',300,49),('C',300+sign*4,50,300+sign*10,55,300+sign*15,65),
                  ('C',300+sign*10,61,300+sign*4,58,300,58),('C',300-sign*3,60,300-sign*9,67,300-sign*15,79),
                  ('C',300-sign*12,64,300-sign*5,54,300,49),('Z',)],fill='#3a3a3a',stroke=0)
        label(300,103,'XBOX',24,'#202020')
        for x in (225,385): oval(x,86,13,fill='#555555')
        # Native View and Menu marks.
        for x,y in ((222,83),(228,89)):
            line([(x-4,y-4),(x+4,y-4),(x+4,y+4),(x-4,y+4),(x-4,y-4)],'#b7b7b7',1.3)
        for y in (81,86,91): line([(379,y),(391,y)],'#b7b7b7',1.4)
        rounded((282,122,318,141),8,fill='#555555');line([(292,133),(308,133)],'#aaa',1.5)
        line([(300,133),(300,125),(296,128),(300,125),(304,128)],'#aaa',1.5)
        stick(150,140);stick(390,230);plus(220,230)
        for x,y,letter in ((455,100,'Y'),(415,140,'X'),(495,140,'B'),(455,180,'A')):
            oval(x,y,21,fill='#575757');label(x,y,letter,25)
    else:
        path([('M',110,28),('C',76,23,57,34,46,64),('C',31,116,25,200,18,299),
              ('C',13,350,23,385,55,395),('C',90,408,117,374,139,334),('L',185,262),
              ('C',204,247,239,249,260,256),('L',340,256),('C',361,249,396,247,415,262),
              ('L',461,334),('C',483,374,510,408,545,395),('C',577,385,587,350,582,299),
              ('C',575,200,569,116,554,64),('C',543,34,524,23,490,28),
              ('C',431,19,377,23,300,24),('C',223,23,169,19,110,28),('Z',)],fill='#303030')
        # DualShock 4 face shell: wide recessed touchpad, symmetric sticks, split d-pad and no DualSense light strips.
        path([('M',90,40),('L',510,40),('C',530,76,542,130,549,181),('C',516,206,469,247,427,288),
              ('C',399,261,362,250,340,256),('L',260,256),('C',238,250,201,261,173,288),
              ('C',131,247,84,206,51,181),('C',58,130,70,76,90,40),('Z',)],fill='#393939',stroke=1.5)
        rounded((214,31,386,161),17,fill='#202020',stroke=3)
        rounded((191,60,203,89),6,fill='#5b5b5b');rounded((397,60,409,89),6,fill='#5b5b5b')
        for row in range(3):
            for column in range(5-row): oval(284+column*8+row*4,182+row*8,1.7,fill='#151515',stroke=1)
        oval(300,233,17,fill='#606060')
        stick(215,235);stick(385,235)
        # Four independently outlined direction buttons, matching the DualShock reference.
        for turn in range(4):
            points=[(-12,-36),(12,-36),(14,-20),(0,-5),(-14,-20)];rotated=[]
            for x,y in points:
                for _ in range(turn):x,y=-y,x
                rotated.append((130+x,133+y))
            path([('M',*rotated[0]),*[('L',*p) for p in rotated[1:]],('Z',)],fill='#5a5a5a',stroke=2.5)
        for x,y,symbol in ((470,93,'triangle'),(430,133,'square'),(510,133,'circle'),(470,173,'cross')):
            oval(x,y,23,fill='#575757')
            if symbol=='circle':
                draw.ellipse((*point(x-14,y-14),*point(x+14,y+14)),outline='#b7b7b7',width=round(2*.8*scale))
            elif symbol=='triangle':line([(x,y-15),(x-15,y+12),(x+15,y+12),(x,y-15)],'#b7b7b7',2)
            elif symbol=='square':line([(x-12,y-12),(x+12,y-12),(x+12,y+12),(x-12,y+12),(x-12,y-12)],'#b7b7b7',2)
            else:
                line([(x-12,y-12),(x+12,y+12)],'#b7b7b7',2);line([(x-12,y+12),(x+12,y-12)],'#b7b7b7',2)
    image=image.resize((580,340),Image.Resampling.LANCZOS)
    return image if (width,height)==(580,340) else image.resize((width,height),Image.Resampling.LANCZOS)


def color_bc3(image):
    """Encode actual RGB and alpha, preserving the flat diagram’s fills, fine outlines and transparency."""
    out = io.BytesIO()
    image.save(out, format='DDS', pixel_format='DXT5')
    data = out.getvalue()
    assert data[:4] == b'DDS ' and data[84:88] == b'DXT5'
    blocks = data[128:]
    assert len(blocks) == ((image.width+3)//4)*((image.height+3)//4)*16
    return blocks


def drawing(style, width=580, height=340):
    if style in DIAGRAM_ANCHORS:
        return controller_diagram(style,width,height)
    assert style == 'keyboard', style
    scale = 3
    im = Image.new('RGBA', (width * scale, height * scale))
    d = ImageDraw.Draw(im)
    def box(bounds, radius=10, fill=None, outline='white', line=2):
        d.rounded_rectangle(tuple(round(v * scale) for v in bounds), radius * scale, fill=fill,
                            outline=outline, width=line * scale)
    def text(x, y, label, size=16):
        # Pillow's bundled font keeps generation independent of installed system fonts.
        font = ImageFont.load_default(size=size*scale)
        d.text((x*scale, y*scale), label, font=font, fill='white', anchor='mm')
    def key(x, y, label, w=36):
        box((x-w/2, y-16, x+w/2, y+16), 5, fill='#242424'); text(x, y, label, 13)
    if style == 'keyboard':
        box((24, 45, 556, 295), 18, fill='#181818', line=3)
        for x, label in ((66,'Tab'), (154,'Q'), (204,'W'), (254,'E'), (310,'I'), (360,'U'), (422,'Opt'), (502,'Shift')):
            key(x, 85, label, 60 if len(label)>1 else 36)
        for x, label in ((154,'A'), (204,'S'), (254,'D'), (310,'J'), (360,'K'), (422,'Enter')):
            key(x, 135, label, 66 if len(label)>1 else 36)
        for x, label in ((154,'Z'), (204,'C'), (284,'T'), (334,'F'), (384,'G'), (434,'H')): key(x,185,label)
        key(260, 245, 'Space', 200)
        # Arrow keys are drawn as lines, so no Unicode font coverage is needed.
        for x,y,dx,dy in ((490,185,0,-1),(450,235,-1,0),(490,235,0,1),(530,235,1,0)):
            key(x,y,'')
            points=[(x-dx*7,y-dy*7),(x+dx*7,y+dy*7)]
            d.line([(a*scale,b*scale) for a,b in points],fill='white',width=2*scale)
            tip=(x+dx*7,y+dy*7)
            d.line([((tip[0]-dx*5+dy*5)*scale,(tip[1]-dy*5-dx*5)*scale), (tip[0]*scale,tip[1]*scale),
                    ((tip[0]-dx*5-dy*5)*scale,(tip[1]-dy*5+dx*5)*scale)], fill='white',width=2*scale)
    return im.resize((width,height), Image.Resampling.LANCZOS)


def block_offset(x, y, row_bytes, tile_height):
    """Byte address in Tegra block-linear storage (same mapping as gfx/tex/nvn_deswizzle.c)."""
    bh = 1 << tile_height
    return ((y//(8*bh))*((row_bytes+63)//64)+(x//64))*512*bh + (y%(8*bh)//8)*512 + \
        (x%64//32)*256 + (y%8//2)*64 + (x%32//16)*32 + (y%2)*16 + x%16


def bc3_block(pixels):
    # White artwork with luminance encoded in alpha: reproduces fine outlines and labels in eight coverage levels.
    alpha = [round(p[3] * p[0] / 255) for p in pixels]
    palette = [255, 0] + [round((7-i)*255/7) for i in range(1,7)]
    bits = sum(min(range(8), key=lambda i: abs(palette[i]-v)) << (3*j) for j,v in enumerate(alpha))
    return bytes((255,0)) + bits.to_bytes(6,'little') + b'\xff\xff\x00\x00' + b'\0'*4


def replace_textures(data, style):
    """BNTX with all controller states replaced, and original Switch-shaped shadows cleared. Fail on unknown geometry."""
    assert data[:8] == b'BNTX\0\0\0\0' and data[12:14] == b'\xff\xfe', 'unsupported BNTX'
    out = bytearray(data); count = struct.unpack_from('<I',data,0x24)[0]; table = struct.unpack_from('<Q',data,0x28)[0]
    found = set(); cache = {}
    for i in range(count):
        at = struct.unpack_from('<Q',data,table+8*i)[0]
        assert data[at:at+4] == b'BRTI'
        name_at = struct.unpack_from('<Q',data,at+0x60)[0]
        name = data[name_at+2:data.index(b'\0',name_at+2)].decode()
        if not name.startswith(('Controller_', 'ControllerSh_')): continue
        assert name in {f'{prefix}{kind}{state}^{suffix}' for prefix,suffix in (('Controller_','w'),('ControllerSh_','s'))
                        for kind in ('Console','Grip','Pro') for state in ('','1')}, name
        fmt = struct.unpack_from('<I',data,at+0x1c)[0]
        w,h,depth,layers,tile = struct.unpack_from('<5I',data,at+0x24)
        size = struct.unpack_from('<I',data,at+0x50)[0]
        pointers = struct.unpack_from('<Q',data,at+0x70)[0]; start = struct.unpack_from('<Q',data,pointers)[0]
        assert data[at+0x12:at+0x18] == b'\0\0\0\0\x01\0' and depth == layers == 1
        assert start+size <= len(data)
        if name.startswith('ControllerSh_'):
            assert fmt == 0x1d01, (name,hex(fmt))   # BC4 UNORM: all-zero blocks = transparent shadow
            out[start:start+size] = bytes(size)
        else:
            assert (fmt,w,h) == (0x2d06,580,340), (name,hex(fmt),w,h)  # BC7 sRGB -> BC3 sRGB
            if (w,h,tile,size) not in cache:
                im = drawing(style,w,h); px = im.load(); blocks = bytearray(size)
                color = color_bc3(im) if style in DIAGRAM_ANCHORS else None
                for y in range(0,h,4):
                    for x in range(0,w,4):
                        off = block_offset(x//4*16,y//4,((w+3)//4)*16,tile & 7)
                        assert off+16 <= size
                        linear = ((y//4)*((w+3)//4)+x//4)*16
                        blocks[off:off+16] = color[linear:linear+16] if color is not None else bc3_block(
                            [px[min(x+i,w-1),min(y+j,h-1)] for j in range(4) for i in range(4)])
                cache[w,h,tile,size] = blocks
            out[start:start+size] = cache[w,h,tile,size]
            struct.pack_into('<I',out,at+0x1c,0x1c06)
        found.add(name)
    assert len(found) == 12, f'expected twelve controller textures, got {found}'
    return bytes(out)


PANE_MAGICS = (b'pan1', b'pic1', b'txt1', b'wnd1', b'bnd1', b'prt1', b'ali1', b'scr1')


def layout_panes(layout):
    assert layout[:6] == b'FLYT\xff\xfe', 'unsupported Controls layout'
    at = struct.unpack_from('<H',layout,6)[0]; found = {}
    for _ in range(struct.unpack_from('<H',layout,16)[0]):
        size = struct.unpack_from('<I',layout,at+4)[0]
        assert size >= 8 and at+size <= len(layout)
        if layout[at:at+4] in PANE_MAGICS:
            name=layout[at+12:at+36].split(b'\0')[0].decode()
            assert name not in found, f'duplicate Controls pane {name}'
            found[name]=at
        at += size
    return found


def replace_callouts(layout, style, controller_layout=None):
    """Preserve the native label panels, cream connectors, dots, diamonds and visibility animations.

    Endpoints use the same coordinates as the drawings. Return the layout and FLPA property overrides to apply
    to the controller-mode animations; otherwise those animations would restore the original Switch endpoints.
    """
    found=layout_panes(layout);out=bytearray(layout);edits={}
    if style=='keyboard':
        out[found['N_Line_00']+8] &= ~1
        return bytes(out),edits
    assert style in DIAGRAM_ANCHORS
    assert layout[found['N_Line_00']+8] & 1, 'original connector parent is hidden'
    child=layout_panes(controller_layout)
    pic=child['P_Controller_00']
    assert struct.unpack_from('<2f',controller_layout,pic+76)==(580,340), 'unexpected controller canvas'
    assert struct.unpack_from('<2f',controller_layout,pic+68)==(1,1), 'unexpected controller scale'
    def original(name,prop):return struct.unpack_from('<f',layout,found[name]+44+4*prop)[0]
    def set_field(name,prop,value):
        struct.pack_into('<f',out,found[name]+44+4*prop,value);edits[name,prop]=value
    def origin(name,value):out[found[name]+9]=value
    # Child layout has its own root; its image offset and the enclosing part define texture-to-layout coordinates.
    picture_x=original('Pa_Controller_00',0)+struct.unpack_from('<f',controller_layout,pic+44)[0]
    picture_y=original('Pa_Controller_00',1)+struct.unpack_from('<f',controller_layout,pic+48)[0]
    set_field('Pa_Controller_00',1,original('Pa_Controller_00',1))
    line_x=original('N_CapGuide_00',0)+original('N_Line_00',0)
    line_y=original('N_CapGuide_00',1)+original('N_Line_00',1)
    if style=='playstation':
        # DualShock has its d-pad above the left stick. Move each complete native action group so the
        # connector routes do not cross; IsHorse's position curves are swapped in the same way below.
        for prefix in ('N_','N_IsHorse_'):
            left=f'{prefix}LStick_00';cross=f'{prefix}CrossKey_00'
            set_field(left,1,original(cross,1));set_field(cross,1,original(left,1))
    for key,(px,py) in DIAGRAM_ANCHORS[style].items():
        line_name=f'P_Line{key}_00';horizon=f'P_Horizon{key}_00'
        vertical=f'P_Verti{key}_00' if key not in ('ABXY','CrossKey') else f'P_VertiL{key}_00'
        start_x=original(line_name,0);start_y=original(line_name,1)
        sign=original(line_name,6)
        # Give the top-right routes and Purah Pad route a clear corridor above the face/d-pad diamonds.
        # Move each panel together with its localized text; the original order and spacing are retained.
        if key in ('ZL','L','ZR','R','Plus','Minus'):
            start_y+=24
            set_field(line_name,1,original(line_name,1)+24)
            label=f'N_{key}_00'
            set_field(label,1,original(label,1)+24)
        if key in ('LStick','CrossKey'):
            start_x+=original(f'N_IsHorse_{key}_00',0)+original(f'N_IsHorse_{key}_01',0)
            row_key=({'LStick':'CrossKey','CrossKey':'LStick'}[key] if style=='playstation' else key)
            start_y+=original(f'N_IsHorse_{row_key}_00',1)+original(f'N_IsHorse_{key}_01',1)
        assert sign in (-1,1)
        tx=picture_x+px-290;ty=picture_y+170-py
        radius=GROUP_RADIUS[style].get(key,0)
        width=(tx-line_x-start_x)/sign
        dy=ty-radius-line_y-start_y
        assert 0 < width < 300, (key,width)
        for prop,value in ((0,0),(1,0),(8,width),(9,3)):set_field(horizon,prop,value)
        origin(horizon,1)   # left/middle: right-hand routes inherit their parent's horizontal reflection
        for prop,value in ((0,width),(1,0),(8,3),(9,abs(dy))):set_field(vertical,prop,value)
        origin(vertical,4 if dy<0 else 8)   # top or bottom anchored vertical segment
        out[found[vertical]+8] |= 1
        if radius:
            endpoint=f'W_Circle{key}_00'; side=radius*math.sqrt(2)
            for prop,value in ((0,0),(1,dy+radius),(5,45),(8,side),(9,side)):set_field(endpoint,prop,value)
        else:
            endpoint=f'P_Circle{key}_00'
            # Plus/Minus endpoint dots are children of the horizontal segment, all others of the vertical segment.
            for prop,value in ((0,width if key in ('Minus','Plus') else 0),(1,dy),(8,12),(9,12)):
                set_field(endpoint,prop,value)
        origin(endpoint,0)   # endpoint positions always refer to the dot/diamond center
    return bytes(out),edits


def animation_tracks(data):
    """Yield checked native BFLAN track metadata, keeping all curve frames and unrelated tracks intact."""
    assert data[:6] == b'FLAN\xff\xfe', 'unsupported Controls animation'
    pos=struct.unpack_from('<H',data,6)[0]
    for _ in range(struct.unpack_from('<H',data,16)[0]):
        size=struct.unpack_from('<I',data,pos+4)[0];assert size>=8 and pos+size<=len(data)
        if data[pos:pos+4]==b'pai1':
            count=struct.unpack_from('<H',data,pos+14)[0];table=pos+struct.unpack_from('<I',data,pos+16)[0]
            for i in range(count):
                eo=pos+struct.unpack_from('<I',data,table+i*4)[0]
                name=data[eo:eo+28].split(b'\0')[0].decode()
                for t in range(data[eo+28]):
                    to=eo+struct.unpack_from('<I',data,eo+32+t*4)[0];magic=data[to:to+4]
                    if magic not in (b'FLPA',b'FLVI'):continue
                    for g in range(data[to+4]):
                        go=to+struct.unpack_from('<I',data,to+8+g*4)[0]
                        count=struct.unpack_from('<H',data,go+4)[0];curve=data[go+2]
                        ko=go+struct.unpack_from('<I',data,go+8)[0]
                        stride=12 if curve==2 else 8
                        assert ko+count*stride<=pos+size
                        yield name,magic,data[go+1],curve,[ko+k*stride for k in range(count)]
        pos+=size


def replace_callout_animation(data, edits, style):
    if not edits:return data
    out=bytearray(data);tracks=list(animation_tracks(data))
    horse_pairs={}
    if style=='playstation':
        for prefix in ('N_','N_IsHorse_'):
            for suffix in ('00','01') if prefix=='N_IsHorse_' else ('00',):
                a=f'{prefix}LStick_{suffix}';b=f'{prefix}CrossKey_{suffix}'
                horse_pairs[a]=b;horse_pairs[b]=a
    track_keys={(name,magic,prop):(curve,keys) for name,magic,prop,curve,keys in tracks}
    for name,magic,prop,curve,keys in tracks:
        if magic==b'FLPA' and prop==1 and name in horse_pairs:
            other_curve,other_keys=track_keys[horse_pairs[name],magic,prop]
            assert curve==other_curve==2 and len(keys)==len(other_keys), 'horse rows have incompatible curves'
            for at,other in zip(keys,other_keys):
                assert data[at:at+4]==data[other:other+4], 'horse row keyframes differ'
                out[at+4:at+12]=data[other+4:other+12]
            continue

        if magic==b'FLPA' and (name,prop) in edits:
            assert curve==2, 'expected a Hermite pane transform curve'
            for at in keys:struct.pack_into('<ff',out,at+4,edits[name,prop],0)  # value, zero tangent
        elif magic==b'FLVI' and name=='P_VertiMinus_00':
            assert curve==1
            for at in keys:struct.pack_into('<H',out,at+4,1)
    return bytes(out)
