"""Shared original Xbox, DualSense and keyboard vector diagrams (580 x 340)."""
import math
from PIL import Image, ImageDraw, ImageFont


# Coordinates are shared by the vector drawings and native callout placement (580 x 340 canvas).
# They describe a front-facing Xbox pad and a DualSense, matching the game's flat, outlined illustration style.
DIAGRAM_ANCHORS = {
    'xbox': {'ZL': (174,12), 'ZR': (406,12), 'L': (142,33), 'R': (438,33),
             'Minus': (254,69), 'Plus': (326,69), 'LStick': (170,112),
             'CrossKey': (226,184), 'ABXY': (414,112), 'RStick': (362,184)},
    'playstation': {'ZL': (150,12), 'ZR': (430,12), 'L': (122,30), 'R': (458,30),
                    'Minus': (178,56), 'Plus': (402,56), 'LStick': (222,188),
                    'CrossKey': (154,106.4), 'ABXY': (426,106.4), 'RStick': (358,188)},
}
GROUP_RADIUS = {'xbox': {'CrossKey': 39, 'ABXY': 54}, 'playstation': {'CrossKey': 43, 'ABXY': 54}}


def controller_diagram(style, width=580, height=340):
    """Light controller diagrams with white inputs and fine grey seams, drawn at 4x."""
    assert style in DIAGRAM_ANCHORS
    scale = 4; image = Image.new('RGBA', (580*scale,340*scale)); draw = ImageDraw.Draw(image)
    def point(x,y): return ((50+.8*x)*scale,.8*y*scale)
    def line(points, color='#777777', stroke=2):
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
    def oval(x,y,rx,ry=None,fill='#eeeeee',stroke=2):
        ry=rx if ry is None else ry
        draw.ellipse((*point(x-rx,y-ry),*point(x+rx,y+ry)),fill=fill,outline='#777777',width=max(1,round(stroke*.8*scale)))
    def rounded(bounds,radius=8,fill='#242424',stroke=2):
        x0,y0,x1,y1=bounds
        draw.rounded_rectangle((*point(x0,y0),*point(x1,y1)),radius=radius*.8*scale,fill=fill,
                               outline='#777777',width=max(1,round(stroke*.8*scale)))
    def label(x,y,value,size=20,color='#777777'):
        draw.text(point(x,y),value,font=ImageFont.load_default(size=round(size*.8*scale)),fill=color,anchor='mm')
    def stick(x,y):
        oval(x,y,45,fill='#aaaaaa',stroke=3);oval(x,y,36,fill='#f0f0f0',stroke=2)
        oval(x,y,31,fill=None,stroke=1)
    def plus(x,y):
        pts=[(-11,-33),(11,-33),(11,-11),(33,-11),(33,11),(11,11),(11,33),(-11,33),(-11,11),(-33,11),(-33,-11),(-11,-11)]
        path([('M',x+pts[0][0],y+pts[0][1]),*[('L',x+a,y+b) for a,b in pts[1:]],('Z',)],fill='#eeeeee',stroke=2)
        for dx,dy in ((0,-1),(0,1),(-1,0),(1,0)):
            cx,cy=x+dx*23,y+dy*23
            triangle=[(cx+dx*4,cy+dy*4),(cx-dx*3+dy*4,cy-dy*3-dx*4),(cx-dx*3-dy*4,cy-dy*3+dx*4)]
            draw.polygon([point(*p) for p in triangle],fill='#888888')
    # Separate trigger/bumper pods and a curved shoulder rim, rather than the old angular generic silhouette.
    for x in (155,445):
        path([('M',x-48,28),('C',x-42,6,x+35,5,x+45,27),('L',x+44,48),('L',x-47,48),('Z',)],fill='#999999')
    if style=='xbox':
        path([('M',130,30),('C',100,29,76,39,65,66),('C',46,112,33,186,20,265),
              ('C',8,328,18,368,48,387),('C',75,405,111,390,139,351),('L',193,278),
              ('C',210,253,253,252,300,253),('C',347,252,390,253,407,278),('L',461,351),
              ('C',489,390,525,405,552,387),('C',582,368,592,328,580,265),
              ('C',567,186,554,112,535,66),('C',524,39,500,29,470,30),
              ('C',410,23,365,24,300,25),('C',235,24,190,23,130,30),('Z',)],fill='#aaaaaa')
        path([('M',72,77),('C',142,44,224,44,300,45),('C',376,44,458,44,528,77),
              ('L',548,162),('C',514,190,474,230,432,286),('C',393,256,366,251,300,253),
              ('C',234,251,207,256,168,286),('C',126,230,86,190,52,162),('Z',)],fill='#b6b6b6',stroke=1.5)
        path([('M',70,69),('C',152,33,229,36,300,36),('C',371,36,448,33,530,69)],fill=None,stroke=2)
        oval(300,65,20,fill='#aaaaaa')
        # Xbox sphere/X mark, drawn as four curved lobes rather than a literal letter X in a circle.
        for sign in (-1,1):
            path([('M',300,49),('C',300+sign*4,50,300+sign*10,55,300+sign*15,65),
                  ('C',300+sign*10,61,300+sign*4,58,300,58),('C',300-sign*3,60,300-sign*9,67,300-sign*15,79),
                  ('C',300-sign*12,64,300-sign*5,54,300,49),('Z',)],fill='#b6b6b6',stroke=0)
        for x in (255,345): oval(x,86,13,fill='#eeeeee')
        # Native View and Menu marks.
        for x,y in ((252,83),(258,89)):
            line([(x-4,y-4),(x+4,y-4),(x+4,y+4),(x-4,y+4),(x-4,y-4)],'#777777',1.3)
        for y in (81,86,91): line([(339,y),(351,y)],'#777777',1.4)
        rounded((282,122,318,141),8,fill='#777777');line([(292,133),(308,133)],'#aaa',1.5)
        line([(300,133),(300,125),(296,128),(300,125),(304,128)],'#aaa',1.5)
        stick(150,140);stick(390,230);plus(220,230)
        for x,y,letter in ((455,100,'Y'),(415,140,'X'),(495,140,'B'),(455,180,'A')):
            oval(x,y,21,fill='#eeeeee');label(x,y,letter,25)
    else:
        # DualSense: broad white wings, tapered touchpad and a recessed grey center.
        path([('M',112,28),('C',81,23,62,32,49,61),('C',31,102,22,179,14,278),
              ('C',10,334,14,369,33,384),('L',91,402),('C',111,360,141,304,180,266),
              ('C',211,245,249,250,300,251),('C',351,250,389,245,420,266),
              ('C',459,304,489,360,509,402),('L',567,384),('C',586,369,590,334,586,278),
              ('C',578,179,569,102,551,61),('C',538,32,519,23,488,28),
              ('C',421,24,359,27,300,27),('C',241,27,179,24,112,28),('Z',)],fill='#cccccc',stroke=2)
        path([('M',181,38),('C',194,102,198,147,214,161),('L',386,161),
              ('C',402,147,406,102,419,38),('L',457,124),('C',468,174,457,224,421,262),
              ('C',452,309,479,361,490,397),('L',509,402),('C',489,360,459,304,420,266),
              ('C',389,245,351,250,300,251),('C',249,250,211,245,180,266),
              ('C',141,304,111,360,91,402),('L',110,397),('C',121,361,148,309,179,262),
              ('C',143,224,132,174,143,124),('Z',)],fill='#999999',stroke=0)
        path([('M',181,29),('L',419,29),('L',402,137),('C',400,155,388,162,371,162),
              ('L',229,162),('C',212,162,200,155,198,137),('Z',)],fill='#bdbdbd',stroke=2)
        rounded((154,54,166,84),6,fill='#eeeeee');rounded((434,54,446,84),6,fill='#eeeeee')
        for row in range(3):
            for column in range(5-row): oval(284+column*8+row*4,182+row*8,1.7,fill='#151515',stroke=1)
        rounded((285,229,315,235),3,fill='#777777');rounded((286,199,314,210),4,fill='#777777')
        stick(215,235);stick(385,235)
        # Four independently outlined direction buttons, matching the DualShock reference.
        for turn in range(4):
            points=[(-12,-36),(12,-36),(14,-20),(0,-5),(-14,-20)];rotated=[]
            for x,y in points:
                for _ in range(turn):x,y=-y,x
                rotated.append((130+x,133+y))
            path([('M',*rotated[0]),*[('L',*p) for p in rotated[1:]],('Z',)],fill='#eeeeee',stroke=2.5)
        for x,y,symbol in ((470,93,'triangle'),(430,133,'square'),(510,133,'circle'),(470,173,'cross')):
            oval(x,y,23,fill='#eeeeee')
            if symbol=='circle':
                draw.ellipse((*point(x-14,y-14),*point(x+14,y+14)),outline='#777777',width=round(2*.8*scale))
            elif symbol=='triangle':line([(x,y-15),(x-15,y+12),(x+15,y+12),(x,y-15)],'#777777',2)
            elif symbol=='square':line([(x-12,y-12),(x+12,y-12),(x+12,y+12),(x-12,y+12),(x-12,y-12)],'#777777',2)
            else:
                line([(x-12,y-12),(x+12,y+12)],'#777777',2);line([(x-12,y+12),(x+12,y-12)],'#777777',2)
    image=image.resize((580,340),Image.Resampling.LANCZOS)
    return image if (width,height)==(580,340) else image.resize((width,height),Image.Resampling.LANCZOS)


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


