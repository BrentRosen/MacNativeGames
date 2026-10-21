"""Original, procedural Controls-screen drawings; replace only controller textures in the player's UI archive.

The six Console/Grip/Pro textures (including their alternate state) share a canvas. BC3 uses the same 16-byte
blocks and storage as the original BC7; names, dimensions, pointers and all other textures stay untouched.
"""
import struct
from PIL import Image, ImageDraw, ImageFont


def drawing(style, width=580, height=340):
    scale = 3
    im = Image.new('RGBA', (width * scale, height * scale))
    d = ImageDraw.Draw(im)
    def box(bounds, radius=10, fill=None, outline='white', line=2):
        d.rounded_rectangle(tuple(round(v * scale) for v in bounds), radius * scale, fill=fill,
                            outline=outline, width=line * scale)
    def circle(x, y, r, fill=None):
        d.ellipse(((x-r)*scale, (y-r)*scale, (x+r)*scale, (y+r)*scale), fill=fill, outline='white', width=2*scale)
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
    else:
        # Distinct silhouettes and stick positions; the face buttons match the runtime's positional mapping.
        ps = style == 'playstation'
        body = [(100,55),(480,55),(510,95),(545,265),(515,302),(475,295),(410,225),
                (170,225),(105,295),(65,302),(35,265),(70,95)]
        d.polygon([(x*scale,y*scale) for x,y in body], fill='#202020', outline='white', width=3*scale)
        for x,label in ((138,'L1' if ps else 'LB'),(442,'R1' if ps else 'RB')):
            box((x-48,30,x+48,57),8,fill='#303030');text(x,44,label,14)
            text(x,17, 'L2' if ps and x<290 else 'R2' if ps else 'LT' if x<290 else 'RT',13)
        if ps: box((225,70,355,130),8,fill='#303030')
        else: circle(290,91,16);text(290,91,'X',15)
        lx,ly = (215,205) if ps else (146,125)
        for x,y in ((lx,ly),(365,205)):
            circle(x,y,32,'#383838');circle(x,y,24);text(x,y,'L3' if x==lx else 'R3',12)
        dx,dy = (140,143) if ps else (218,205)
        box((dx-10,dy-28,dx+10,dy+28),2,fill='#484848',outline=None)
        box((dx-28,dy-10,dx+28,dy+10),2,fill='#484848',outline=None)
        for x,y,label in ((445,108,'Y'),(410,143,'X'),(480,143,'B'),(445,178,'A')):
            circle(x,y,15,'#383838')
            if not ps: text(x,y,label,17)
            elif label=='B': circle(x,y,8)
            elif label=='Y':
                d.line([(x*scale,(y-8)*scale),((x-8)*scale,(y+7)*scale),((x+8)*scale,(y+7)*scale),(x*scale,(y-8)*scale)],fill='white',width=2*scale)
            elif label=='X': box((x-7,y-7,x+7,y+7),0,line=2)
            else:
                for sign in (-1,1): d.line([((x-7)*scale,(y-7*sign)*scale),((x+7)*scale,(y+7*sign)*scale)],fill='white',width=2*scale)
        text(205,92,'Create' if ps else 'View',11);text(376,92,'Options' if ps else 'Menu',11)
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
                for y in range(0,h,4):
                    for x in range(0,w,4):
                        off = block_offset(x//4*16,y//4,((w+3)//4)*16,tile & 7)
                        assert off+16 <= size
                        blocks[off:off+16] = bc3_block([px[min(x+i,w-1),min(y+j,h-1)] for j in range(4) for i in range(4)])
                cache[w,h,tile,size] = blocks
            out[start:start+size] = cache[w,h,tile,size]
            struct.pack_into('<I',out,at+0x1c,0x1c06)
        found.add(name)
    assert len(found) == 12, f'expected twelve controller textures, got {found}'
    return bytes(out)


def replace_callouts(layout):
    """Keep the action labels, but hide connectors aimed at the original Switch hardware.

    The replacement diagrams label every input directly. Original endpoint animations target Switch stick/button
    positions, so retaining those lines over a different device would point players at the wrong inputs.
    """
    assert layout[:4] == b'FLYT' and layout[4:6] == b'\xff\xfe'
    at = struct.unpack_from('<H',layout,6)[0]; out = bytearray(layout); found = 0
    for _ in range(struct.unpack_from('<H',layout,0x10)[0]):
        size = struct.unpack_from('<I',layout,at+4)[0]
        assert size >= 8 and at+size <= len(layout)
        if layout[at:at+4] == b'pan1' and layout[at+12:at+36].split(b'\0')[0] == b'N_Line_00':
            assert layout[at+8] & 1, 'connector parent already hidden'
            out[at+8] &= ~1; found += 1
        at += size
    assert found == 1, 'expected one Switch connector parent'
    return bytes(out)
