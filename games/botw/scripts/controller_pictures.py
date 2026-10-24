"""BotW controller textures and native blue callouts, generated from the player's Bootup.pack."""
import struct
import json
import sys
import zlib
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'totk/scripts'))
from controller_artwork import drawing, DIAGRAM_ANCHORS, GROUP_RADIUS
from make_button_icons import sarc_members, repack
from prepare_shader_seed import yaz0


def block_offset(x,y,row,tile):
    bh=1<<tile
    return ((y//(8*bh))*((row+63)//64)+(x//64))*512*bh+(y%(8*bh)//8)*512+(x%64//32)*256+(y%8//2)*64+(x%32//16)*32+(y%2)*16+x%16


def compress_yaz0(data,header):
    """Greedy LZ77 with a 4 KiB history; retain the original alignment metadata."""
    out=bytearray(header[:4]+struct.pack('>I',len(data))+header[8:16]);pos=0;cached=None
    def match(at):
        length=0;where=-1
        if at+3>len(data):return length,where
        key=data[at:at+3];lo=max(0,at-4096);end=at;limit=min(273,len(data)-at)
        for _ in range(64):
            found=data.rfind(key,lo,end)
            if found<0:break
            n=3
            while n<limit and data[found+n]==data[at+n]:n+=1
            if n>length:length=n;where=found
            if n==limit:break
            end=found
        return length,where
    while pos<len(data):
        flag=len(out);out.append(0);bits=0
        for bit in range(7,-1,-1):
            if pos>=len(data):break
            length,where=cached if cached is not None else match(pos);cached=None
            if 3<=length<273 and pos+1<len(data):
                following=match(pos+1)
                if following[0]>=length+2:length=0;cached=following
            if length>=3:
                distance=pos-where-1
                if length>=18:out.extend((distance>>8,distance&255,length-18))
                else:out.extend(((length-2)<<4|distance>>8,distance&255))
                pos+=length
            else:bits|=1<<bit;out.append(data[pos]);pos+=1
        out[flag]=bits
    return bytes(out)


def texture_rows(data):
    assert data[:8]==b'BNTX\0\0\0\0'
    table=struct.unpack_from('<Q',data,40)[0]
    for i in range(struct.unpack_from('<I',data,36)[0]):
        at=struct.unpack_from('<Q',data,table+8*i)[0];assert data[at:at+4]==b'BRTI'
        name_at=struct.unpack_from('<Q',data,at+96)[0]
        name=data[name_at+2:data.index(0,name_at+2)].decode()
        yield name,at


def shoulder(style):
    """Full rear/top view: sculpted shell, trigger caps, bumpers, ports and stick tips."""
    scale=4;im=Image.new('RGBA',(576*scale,100*scale));d=ImageDraw.Draw(im)
    def polygon(points,fill,outline='#777777',width=1):
        # Round the shell and molded button caps without changing the native texture geometry.
        for _ in range(3):
            points=[v for a,b in zip(points,points[1:]+points[:1])
                    for v in ((.75*a[0]+.25*b[0],.75*a[1]+.25*b[1]),
                              (.25*a[0]+.75*b[0],.25*a[1]+.75*b[1]))]
        pts=[(x*scale,y*scale) for x,y in points]
        d.polygon(pts,fill=fill);d.line(pts+[pts[0]],fill=outline,width=width*scale,joint='curve')
    def rect(box,fill,outline='#777777',radius=8):
        d.rounded_rectangle(tuple(v*scale for v in box),radius*scale,fill=fill,outline=outline,width=scale)
    def ellipse(box,fill):d.ellipse(tuple(v*scale for v in box),fill=fill,outline='#777777',width=scale)
    # Rounded rear shell with a recessed center and tapered grip ends.
    polygon([(76,36),(87,21),(111,10),(143,7),(179,14),(205,22),(371,22),(397,14),
             (433,7),(465,10),(489,21),(500,36),(505,56),(494,74),(466,84),
             (422,89),(154,89),(110,84),(82,74),(71,56)],'#bbbbbb')
    rect((190,30,386,77),'#aaaaaa',radius=18)
    for x,label in ((174,'L2' if style=='playstation' else 'LT'),(406,'R2' if style=='playstation' else 'RT')):
        polygon([(x-31,45),(x-35,28),(x-28,9),(x-14,2),(x+8,2),(x+22,10),
                 (x+29,29),(x+29,44)],'#eeeeee')
        d.text(((x+12)*scale,32*scale),label,font=ImageFont.load_default(size=8*scale),anchor='mm',fill='#888888')
    for x,label in ((142,'L1' if style=='playstation' else 'LB'),(438,'R1' if style=='playstation' else 'RB')):
        polygon([(x-37,45),(x+39,40),(x+39,60),(x+13,67),(x-21,63),(x-36,56)],'#eeeeee')
        d.text((x*scale,53*scale),label,font=ImageFont.load_default(size=8*scale),anchor='mm',fill='#888888')
    rect((273,47,303,52),'#bbbbbb',radius=3)
    if style=='xbox':ellipse((247,55,260,63),'#bbbbbb')
    else:rect((228,67,348,85),'#bbbbbb',radius=12)
    # Front-edge stick tips and controls visible under the rear shell.
    for x in ((229,352) if style=='playstation' else (194,350)):
        rect((x-7,84,x+7,95),'#aaaaaa',radius=3);ellipse((x-23,91,x+23,99),'#dddddd')
    for x in (404,431,458):ellipse((x-7,79,x+7,84),'#cccccc')
    ellipse((174,77,186,82),'#cccccc')
    return im.resize((576,100),Image.Resampling.LANCZOS)


ACTION_ICONS={'A':0xE040,'B':0xE041,'X':0xE042,'Y':0xE043,'L':0xE044,'ZL':0xE046}


def replace_action_textures(data,icons):
    """DoCommand (including Examine) uses R8 images, independently of the prompt font."""
    targets={f'Nt_KeyTex{key}_00^d':cp for key,cp in ACTION_ICONS.items()}
    out=bytearray(data);found=set()
    for name,at in texture_rows(data):
        if name not in targets:continue
        w,h,depth,layers,tile=struct.unpack_from('<5I',data,at+36)
        assert (w,h,depth,layers)==(48,48,1,1) and struct.unpack_from('<I',data,at+28)[0]==0x201, 'unexpected action icon format'
        size=struct.unpack_from('<I',data,at+80)[0];pt=struct.unpack_from('<Q',data,at+112)[0];start=struct.unpack_from('<Q',data,pt)[0]
        assert start+size<=len(data)
        bitmap=ImageOps.contain(icons[targets[name]],(46,46),Image.Resampling.LANCZOS)
        image=Image.new('L',(w,h));image.paste(bitmap,((w-bitmap.width)//2,(h-bitmap.height)//2))
        pixels=image.tobytes()
        for y in range(h):
            for x in range(w):
                off=block_offset(x,y,w,tile&7);assert off<size
                out[start+off]=pixels[y*w+x]
        found.add(name)
    assert found==set(targets), 'missing action icon textures'
    return bytes(out)


def replace_textures(data,style,art=None):
    out=bytearray(data);found=set()
    for name,at in texture_rows(data):
        if name not in ('Nt_NNillust_00^f','Nt_NNillust_01^f'):continue
        w,h,depth,layers,tile=struct.unpack_from('<5I',data,at+36)
        size=struct.unpack_from('<I',data,at+80)[0];pt=struct.unpack_from('<Q',data,at+112)[0];start=struct.unpack_from('<Q',data,pt)[0]
        assert struct.unpack_from('<I',data,at+28)[0]==0x901 and (w,h) in ((576,288),(576,100)) and depth==layers==1
        im=drawing(style).resize((w,h),Image.Resampling.LANCZOS) if h==288 else (
            Image.new('RGBA',(w,h)) if style=='keyboard' else shoulder(style))
        # BotW's illustrations use R8G8 with RRRG component mapping: grayscale in R,
        # alpha in G. Preserve the original format and tile geometry; changing them
        # to BC3 breaks the short shoulder texture when the game creates its view.
        assert struct.unpack_from('<I',data,at+88)[0]==0x03020202
        if art:
            custom=Image.open(Path(art)/('front.png' if h==288 else 'rear.png')).convert('RGBA')
            assert custom.size==((580,340) if h==288 else (576,100)), 'unexpected custom-art canvas'
            im=custom.resize((w,h),Image.Resampling.LANCZOS)
        pixels=Image.merge('LA',(im.convert('L'),im.getchannel('A'))).tobytes()
        body=bytearray(size);row=w*2
        for y in range(h):
            for x in range(w):
                off=block_offset(x*2,y,row,tile&7);linear=(y*w+x)*2
                assert off+2<=size;body[off:off+2]=pixels[linear:linear+2]
        assert start+size<=len(data);out[start:start+size]=body
        found.add(name)
    assert len(found)==2
    return bytes(out)


def panes(data):
    assert data[:6]==b'FLYT\xff\xfe'
    nodes={};parents={};stack=[];last=None;pos=struct.unpack_from('<H',data,6)[0]
    while pos<len(data):
        magic=data[pos:pos+4];size=struct.unpack_from('<I',data,pos+4)[0];assert size>=8 and pos+size<=len(data)
        if magic in (b'pan1',b'prt1',b'txt1',b'pic1',b'wnd1'):
            last=data[pos+12:pos+36].split(b'\0')[0].decode();assert last not in nodes
            nodes[last]=pos;parents[last]=stack[-1] if stack else None
        elif magic==b'pas1':stack.append(last)
        elif magic==b'pae1':stack.pop()
        pos+=size
    return nodes,parents


LINE_KEYS={0:'LStick',1:'RStick',2:'CrossKey',3:'Plus',4:'ZL',5:'ZR',6:'ABXY',7:'R',8:'LStick',9:'L',
           10:'LStick',11:'ZL',12:'ZL',13:'ABXY',14:'CrossKey',16:'L',17:'RStick',18:'Plus',19:'ZR',
           20:'R',21:'ABXY',22:'CrossKey',23:'ZR',24:'Plus',25:'RStick'}


def replace_layout(data,style,art=None):
    custom=json.loads((Path(art)/'layout.json').read_text()) if art else {}
    anchors=custom.get('anchors',DIAGRAM_ANCHORS.get(style,{}))
    radii=custom.get('radii',GROUP_RADIUS.get(style,{}))
    rear_height=custom.get('rear_height',190);rear_y=custom.get('rear_y',-194)
    shoulder_anchors=custom.get('shoulder_anchors',{'ZL':(174,22),'ZR':(406,22),'L':(142,53),'R':(438,53)})
    nodes,parents=panes(data);out=bytearray(data);edits={}
    def props(name):return list(struct.unpack_from('<10f',out,nodes[name]+44))
    def put(name,prop,value):struct.pack_into('<f',out,nodes[name]+44+4*prop,value);edits[name,prop]=value
    def visible(name,on):out[nodes[name]+8]=(out[nodes[name]+8]&~1)|bool(on)
    def world(name):
        x,y,_,_,_,_,sx,sy,*_=props(name)
        if parents[name]:
            px,py,psx,psy=world(parents[name]);return px+x*psx,py+y*psy,sx*psx,sy*psy
        return x,y,sx,sy
    put('P_NNillust_00',8,580);put('P_NNillust_00',9,340)
    put('P_NNillust_01',9,rear_height);put('P_NNillust_01',1,rear_y)
    if style=='playstation':
        # Put the d-pad above movement, matching the symmetric DualSense stick layout.
        for n in ('N_CrossKey_00','N_CrossKey_01','N_CrossKey_02'):
            put(n,1,props(n)[1]+(70 if n.endswith('_00') else 110))
        move={'W_Base_02','T_Icon_16','T_Lstick_00','T_Lstick_01',
              'T_Lstick_02','T_Lstick_03','T_Lstick_06','T_Icon_04','T_Icon_05','T_Icon_06',
              'T_Lstick_04','T_Lstick_05','T_Icon_07','T_Icon_08','N_Line_08','N_Line_10'}
        for n in move:put(n,1,props(n)[1]-80)
    # Keep localized text, blue panels and native per-action visibility gates.
    for name in nodes:
        if not name.startswith(('N_Line_','N_Minus_')):continue
        if style=='keyboard':
            for child in nodes:
                if parents[child]==name and out[nodes[child]:nodes[child]+4]==b'pic1':
                    visible(child,False);put(child,8,0);put(child,9,0)
            continue
        num=int(name.rsplit('_',1)[1])
        if not name.startswith('N_Minus_') and num not in LINE_KEYS:continue
        key='Minus' if name.startswith('N_Minus_') else LINE_KEYS[num];kids=[n for n in nodes if parents[n]==name and out[nodes[n]:nodes[n]+4]==b'pic1']
        if len(kids)<3:continue
        # Three native textured rectangles: horizontal line, vertical line and dot. Keep any native blue panel window.
        if key in ('ZL','ZR','L','R'):
            px,py=shoulder_anchors[key]
            tx=(px-288)*.67;ty=rear_y+(50-py)*(rear_height/100)*.67
        else:
            px,py=anchors[key];tx=(px-290)*.67;ty=-10+(170-py)*.67
        gx,gy,sx,sy=world(name);left=key in ('LStick','CrossKey','ZL','L')
        start_x=-245 if key=='Minus' else -195 if left else 195
        if key=='LStick':start_y=(52 if num==0 else 27)-(80 if style=='playstation' else 0)
        elif key=='CrossKey':start_y=(-15 if num==2 else -54)+((70 if num==2 else 110) if style=='playstation' else 0)
        elif key=='ABXY':start_y=27
        elif key=='RStick':start_y=-96
        elif key=='Plus':start_y=80 if num==3 else 76
        elif key=='Minus':start_y=154 if num==0 else 150
        else:start_y=-192 if key in ('L','R') else -158
        center=(tx,ty)
        if key in ('ABXY','CrossKey'):
            tx+=radii[key]*.67*(1 if key=='ABXY' else -1)
        a=((start_x-gx)/sx,(start_y-gy)/sy);b=((tx-gx)/sx,(start_y-gy)/sy);c=((tx-gx)/sx,(ty-gy)/sy)
        for n in kids:visible(n,False);put(n,8,0);put(n,9,0)
        for n,xy,wh,angle,material in ((kids[0],((a[0]+b[0])/2,a[1]),(abs(b[0]-a[0]),10),0,42),
                (kids[1],(b[0],(b[1]+c[1])/2),(abs(c[1]-b[1]),10),90,42),
                (kids[2],c,(10,10),0,13)):
            visible(n,True);out[nodes[n]+9]=0;struct.pack_into('<H',out,nodes[n]+100,material)
            for prop,value in ((0,xy[0]),(1,xy[1]),(5,angle),(6,1),(7,1),(8,max(1,wh[0])),(9,wh[1])):put(n,prop,value)
        if key in ('ABXY','CrossKey') and len(kids)>=4:
            ring=next((n for n in kids if 'TipsLineCircle' in n),kids[3])
            visible(kids[2],False)  # grouped inputs use an outline instead of a center dot
            visible(ring,True);out[nodes[ring]+9]=0
            struct.pack_into('<H',out,nodes[ring]+100,51)
            radius=radii[key]*.67
            for prop,value in ((0,(center[0]-gx)/sx),(1,(center[1]-gy)/sy),
                               (5,180 if (key=='ABXY')==(sx<0) else 0),
                               (6,1),(7,1),(8,radius*8/3),(9,radius*8/3)):
                put(ring,prop,value)
    return bytes(out),edits


def replace_animation(data,edits):
    out=bytearray(data);pos=struct.unpack_from('<H',data,6)[0]
    for _ in range(struct.unpack_from('<H',data,16)[0]):
        size=struct.unpack_from('<I',data,pos+4)[0]
        if data[pos:pos+4]==b'pai1':
            count=struct.unpack_from('<H',data,pos+14)[0];table=pos+struct.unpack_from('<I',data,pos+16)[0]
            for i in range(count):
                eo=pos+struct.unpack_from('<I',data,table+4*i)[0];name=data[eo:eo+28].split(b'\0')[0].decode()
                for t in range(data[eo+28]):
                    at=eo+struct.unpack_from('<I',data,eo+32+4*t)[0]
                    if data[at:at+4]!=b'FLPA':continue
                    for g in range(data[at+4]):
                        go=at+struct.unpack_from('<I',data,at+8+4*g)[0];prop=data[go+1]
                        if (name,prop) not in edits:continue
                        assert data[go+2]==2
                        keys=go+struct.unpack_from('<I',data,go+8)[0]
                        for k in range(struct.unpack_from('<H',data,go+4)[0]):struct.pack_into('<ff',out,keys+12*k+4,edits[name,prop],0)
        pos+=size
    return bytes(out)


def verify_pack_budget(table):
    """Bootup.pack must use the pack loader's file-size allocation, not a fixed RSTB entry."""
    if table[:4]==b'Yaz0':table=yaz0(table)
    assert table[:4]==b'RSTB'
    count,named=struct.unpack_from('<II',table,4)
    assert len(table)==12+count*8+named*132
    assert zlib.crc32(b'Pack/Bootup.pack') not in {struct.unpack_from('<I',table,12+i*8)[0] for i in range(count)}, 'Bootup has a fixed resource budget'
    for i in range(named):
        name=table[12+count*8+i*132:12+count*8+i*132+128].split(b'\0')[0]
        assert name!=b'Pack/Bootup.pack', 'Bootup has a fixed named resource budget'


def replace_bootup(boot,style,art=None,prompt_icons=None):
    members=sarc_members(boot);name='Layout/Common.sblarc';raw=boot[slice(*members[name])];common=yaz0(raw);cm=sarc_members(common)
    image='timg/__Combined.bntx';textures=replace_textures(common[slice(*cm[image])],style,art)
    if prompt_icons is not None:textures=replace_action_textures(textures,prompt_icons)
    common=repack(common,image,textures)
    layout='blyt/PaAllControllerTipsNN_00.bflyt';cm=sarc_members(common);changed,edits=replace_layout(common[slice(*cm[layout])],style,art);common=repack(common,layout,changed)
    for n in cm:
        if n.startswith('anim/PaAllControllerTipsNN_00') and n.endswith('.bflan'):
            cm=sarc_members(common);data=common[slice(*cm[n])];new=replace_animation(data,edits)
            if new!=data:common=repack(common,n,new)
    assert len(common)==struct.unpack_from('>I',raw,4)[0], 'decoded Controls archive size changed'
    packed=compress_yaz0(common,raw);assert yaz0(packed)==common
    # Keep Bootup's member allocation and every other member exactly intact when compression fits its existing slot.
    if len(packed)<=len(raw):packed+=bytes(len(raw)-len(packed))
    # Bootup.pack is a file-size allocated pack, not an RSTB resource. Common's decoded budget is unchanged.
    result=repack(boot,name,packed)
    return result
