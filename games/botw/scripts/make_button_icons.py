#!/usr/bin/env python3
"""Replace BotW's bitmap button prompts with Xbox, PlayStation or keyboard icons from the shared vector designs.
Reads the player's own font archives and shared font; keeps archive/font sizes and glyph metrics unchanged.
No rebuild is needed. Fixed-image tutorials and controller diagrams keep their original artwork.
"""
import argparse
import io
import struct
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'totk/scripts'))
import make_button_icons as icons
from make_mod_manifest import manifest, read_index
from prepare_shader_seed import yaz0
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.reverseContourPen import ReverseContourPen
from fontTools.ttLib import TTFont
from PIL import Image, ImageFont


def block_offset(x, y, row_bytes, tile):
    bh = 1 << tile
    return ((y//(8*bh))*((row_bytes+63)//64)+(x//64))*512*bh + (y%(8*bh)//8)*512 + \
        (x%64//32)*256 + (y%8//2)*64 + (x%32//16)*32 + (y%2)*16 + x%16


def bc4(pixels):
    high, low = max(pixels), min(pixels)
    palette = [high, low] + [(high*(7-i)+low*i)//7 for i in range(1,7)] if high>low else [high,low]+[high]*4+[0,255]
    bits = sum(min(range(8),key=lambda k:abs(palette[k]-v)) << (3*i) for i,v in enumerate(pixels))
    return bytes((high,low))+bits.to_bytes(6,'little')


def literal_yaz0(data, original):
    # Archive's uncompressed length never changes, so the existing resource-size table remains valid.
    return original[:4]+struct.pack('>I',len(data))+original[8:16]+b''.join(
        b'\xff'+data[i:i+8] for i in range(0,len(data),8))


def icon_bitmaps(shared_font, style):
    font,_ = icons.bfotf_decode(shared_font)
    text = TTFont(io.BytesIO(font),fontNumber=0)
    class SharedGlyphs(icons.Glyphs):
        def outline(self, ch):
            rec, box, upm, advance = super().outline(ch)
            # Shared fonts are TrueType: reverse their clockwise outer contours to the CFF convention.
            if 'glyf' in text:
                normalized=RecordingPen();rec.replay(ReverseContourPen(normalized));rec=normalized
            return rec, box, upm, advance
    designs = icons.STYLES[style](SharedGlyphs([text]))
    if style=='keyboard':
        # These two extra stick variants exist only in TOTK's icon font.
        for cp in (0xE05C,0xE068):designs.pop(cp)
    order=['.notdef']+[f'u{cp:X}' for cp in designs]
    fb=FontBuilder(1000,isTTF=False);fb.setupGlyphOrder(order)
    fb.setupCharacterMap({cp:f'u{cp:X}' for cp in designs})
    chars={'.notdef':T2CharStringPen(600,None).getCharString()};metrics={'.notdef':(600,0)}
    for cp,(advance,draw) in designs.items():
        pen=T2CharStringPen(advance,None);draw(pen);name=f'u{cp:X}'
        chars[name]=pen.getCharString();metrics[name]=(advance,0)
    fb.setupHorizontalMetrics(metrics);fb.setupHorizontalHeader(ascent=1000,descent=-200)
    fb.setupNameTable({'familyName':'Local Button Icons','styleName':'Regular','psName':'LocalButtonIcons'})
    fb.setupOS2(sTypoAscender=1000,sTypoDescender=-200,usWinAscent=1000,usWinDescent=200)
    fb.setupPost();fb.setupCFF('LocalButtonIcons',{},chars,{})
    stream=io.BytesIO();fb.save(stream);face=ImageFont.truetype(io.BytesIO(stream.getvalue()),256)
    result={}
    for cp in designs:
        mask=face.getmask(chr(cp),mode='L');im=Image.frombytes('L',mask.size,bytes(mask))
        result[cp]=im.crop(im.getbbox())
    return result


def patch_font(data, bitmaps):
    assert data[:6]==b'FFNT\xff\xfe', 'unsupported bitmap font'
    sections={};pos=struct.unpack_from('<H',data,6)[0]
    while pos<len(data):
        size=struct.unpack_from('<I',data,pos+4)[0];assert size>=8 and pos+size<=len(data)
        sections.setdefault(data[pos:pos+4],[]).append(pos);pos+=size
    assert pos==len(data)
    cmap={}
    for p in sections[b'CMAP']:
        first,last=struct.unpack_from('<II',data,p+8);method=struct.unpack_from('<H',data,p+16)[0]
        assert method==1, 'unsupported External font cmap'
        for cp in range(first,last+1):
            g=struct.unpack_from('<H',data,p+24+2*(cp-first))[0]
            if g!=65535:cmap[cp]=g
    t=sections[b'TGLP'][0]+8
    cw,ch,sheets=struct.unpack_from('<BBB',data,t)
    cols,rows,width,height=struct.unpack_from('<4H',data,t+12)
    bntx=struct.unpack_from('<I',data,t+20)[0]
    assert sheets==1 and (cw,ch,cols,rows,width,height)==(50,50,5,20,256,1024)
    b=data[bntx:];assert b[:8]==b'BNTX\0\0\0\0'
    assert struct.unpack_from('<I',b,0x24)[0]==1
    table=struct.unpack_from('<Q',b,0x28)[0];at=struct.unpack_from('<Q',b,table)[0]
    assert b[at:at+4]==b'BRTI' and struct.unpack_from('<I',b,at+28)[0]==0x1d01
    w,h,depth,layers,tile=struct.unpack_from('<5I',b,at+36)
    size=struct.unpack_from('<I',b,at+80)[0];ptr=struct.unpack_from('<Q',b,at+112)[0]
    start=struct.unpack_from('<Q',b,ptr)[0]
    assert (w,h,depth,layers)==(width,height,1,1) and start+size<=len(b)
    row=width//4*8
    locations=[start+block_offset(x*8,y,row,tile&7) for y in range(height//4) for x in range(width//4)]
    original=Image.frombytes('L',(width,height),b''.join(b[o:o+8] for o in locations),'bcn',4)
    image=original.copy();count=0
    for cp,bitmap in bitmaps.items():
        assert cp in cmap, f'button U+{cp:04X} absent from External font'
        g=cmap[cp];x=g%cols*(cw+1);y=height-(g//cols+1)*(ch+1)
        cell=original.crop((x,y,x+cw+1,y+ch+1));box=cell.getbbox();assert box
        # Keep the native size, bearings and advance, so localized text needs no layout changes.
        image.paste(0,(x,y,x+cw+1,y+ch+1))
        # BFFNT's texture coordinates read each cell bottom-to-top.
        bitmap=bitmap.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
        image.paste(bitmap.resize((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS),(x+box[0],y+box[1]))
        count+=1
    out=bytearray(data)
    for i,o in enumerate(locations):
        x=i%(width//4)*4;y=i//(width//4)*4
        crop=image.crop((x,y,x+4,y+4))
        if crop.tobytes()!=original.crop((x,y,x+4,y+4)).tobytes():out[bntx+o:bntx+o+8]=bc4(list(crop.tobytes()))
    assert len(out)==len(data)
    return bytes(out),count,image


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('mod',type=Path)
    source=ap.add_mutually_exclusive_group(required=True)
    source.add_argument('--app',type=Path);source.add_argument('--romfs',type=Path)
    ap.add_argument('--shared-fonts',type=Path)
    ap.add_argument('--version',choices=('botw160','botw190'))
    ap.add_argument('--style',choices=sorted(icons.STYLES),default='xbox')
    ap.add_argument('--replace',action='store_true');ap.add_argument('--preview',type=Path)
    ap.add_argument('--controller-art',type=Path,help='optional front.png, rear.png and layout.json from player-supplied artwork')
    args=ap.parse_args();version=args.version or args.mod.name
    if version not in ('botw160','botw190'):ap.error('use a botw160/botw190 mod folder or --version')
    root=args.app/'Contents/Resources/totk' if args.app else None
    romfs=args.romfs or root/f'extracted/{version}/romfs'
    fonts=args.shared_fonts or (root/'extracted/firmware/shared-fonts' if root else None)
    if not fonts:ap.error('--romfs requires --shared-fonts')
    index=read_index(romfs/'runtime-index.bin')
    names=[n for n in index if n.startswith('Font/Font_') and n.endswith('.sbfarc')]
    assert names, 'no BotW font archives'
    for n in names:
        if (args.mod/n).exists() and not args.replace:ap.error(f'{args.mod/n} exists; use --replace to change styles')
    designs=icon_bitmaps((fonts/'0-standard.bfttf').read_bytes(),args.style)
    outputs={};cache={}
    with (romfs/'romfs.bin').open('rb') as f:
        for n in names:
            offset,size=index[n];f.seek(offset);raw=f.read(size);archive=yaz0(raw);members=icons.sarc_members(archive)
            font=archive[slice(*members['External_00.bffnt'])]
            if font not in cache:cache[font]=patch_font(font,designs)
            changed,count,preview=cache[font];new=icons.repack(archive,'External_00.bffnt',changed)
            assert len(new)==len(archive), 'font archive grew: resource-size table would need updating'
            outputs[n]=literal_yaz0(new,raw)
            assert yaz0(outputs[n])==new
    from controller_pictures import replace_bootup, verify_pack_budget
    with (romfs/'romfs.bin').open('rb') as f:
        offset,size=index['Pack/Bootup.pack'];f.seek(offset);boot=f.read(size)
        offset,size=index['System/Resource/ResourceSizeTable.product.srsizetable'];f.seek(offset);verify_pack_budget(f.read(size))
    if (args.mod/'Pack/Bootup.pack').exists() and not args.replace:
        ap.error('a Controls picture mod already exists; use --replace to change styles')
    outputs['Pack/Bootup.pack']=replace_bootup(boot,args.style,args.controller_art)
    for n,data in outputs.items():
        target=args.mod/n;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    lines,_,added,misspelt=manifest(args.mod,romfs);assert not added and not misspelt
    (args.mod/'manifest.tsv').write_text('# path\tsize\tsha256\toriginal_sha256\n'+'\n'.join(lines)+'\n')
    if args.preview:preview.save(args.preview)
    print(f'{args.style}: {count} button icons in {len(names)} localized font archives plus Controls pictures; {args.mod}/manifest.tsv')

if __name__=='__main__':main()
