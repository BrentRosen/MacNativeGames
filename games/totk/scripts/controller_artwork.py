"""Shared original Xbox, DualShock 4 and keyboard vector diagrams (580 x 340)."""
import math
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


