#!/usr/bin/env python3
"""Use U-King Mod Manager (UKMM, https://github.com/GingerAvalanche/ukmm) with the Breath of the Wild app (docs/ukmm.md).

UKMM merges RomFS mods and deploys them in the Switch layout; the app loads RomFS mods from a folder with a manifest
(docs/mods.md). This script connects the two, with no change to the app:

  dump   unpacks the app's RomFS (and DLC volume 1) into a folder UKMM reads as its game dump. UKMM merges against
         those files. Run once per app version; files already unpacked with the right size are kept, so an interrupted dump continues.
  sync   run after every UKMM deploy (UKMM's "Launch game" command can run it with --launch):
           - points <data>/mods/<version> at <deploy>/01007EF00011E000/romfs and <data>/mods/<version>-aoc/1 at
             <deploy>/01007EF00011F001/romfs (symbolic links; a folder that holds files is moved aside first, not
             deleted);
           - rebuilds UKMM's resource size table from the app's own: UKMM starts it from the stock 1.6.0 table its
             rstb crate carries, whose smaller sizes stop a 1.9.0 game at start (fix_rstb);
           - writes both manifests with games/totk/scripts/make_mod_manifest.py (the game checks every file's
             SHA-256 at start, so a deploy without a sync stops the start with an integrity mismatch);
           - merges UKMM's Pack/Bootup.pack with the button-icon sets in <data>/button-icons: every set replaces
             Pack/Bootup.pack too (its Layout/Common.sblarc carries the icons and the quick-menu fix), and two
             overlays cannot replace one file. Each set's own Bootup.pack is kept next to it as Bootup.pack.icons and
             its manifest as manifest.tsv.icons; the set then loads UKMM's Bootup.pack with the set's changed members
             in it, and the mod manifest leaves Bootup.pack out. A member both change keeps the mod's version (said
             so). A deploy without Bootup.pack puts the sets back as they were;
           - with --launch, opens the app.

UKMM settings (Switch mode): Base game and Update folders both <dump>/romfs (the app's RomFS is already base + update),
DLC folder <dump>/dlc; deploy method Copy or Hard Link (not Symlink: that swaps whole folders, and the manifest would be
written into UKMM's merge folder); layout without the mod name, or with it (both are found).

usage: ukmm.py dump --app <Breath of the Wild.app> --output <folder>
       ukmm.py sync --deploy <UKMM deploy folder> [--app <Breath of the Wild.app>] [--launch]
"""
import argparse
from datetime import datetime
import functools
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import struct
import subprocess
import sys
import zlib

SCRIPTS = Path(__file__).resolve().parents[2] / 'totk/scripts'
sys.path.insert(0, str(SCRIPTS))
from make_mod_manifest import JUNK, KEPT, read_index  # noqa: E402
from nx_formats import sarc_members, sarc_replace  # noqa: E402
from prepare_shader_seed import yaz0  # noqa: E402

CONTENT, AOC = '01007EF00011E000', '01007EF00011F001'   # the title folders of UKMM's Switch deploy (settings.rs)
NAMED = 'BreathOfTheWild_UKMM'                          # the "with name" deploy layout
VERSIONS = ('botw190', 'botw160')
BOOTUP = 'Pack/Bootup.pack'
RSTB = 'System/Resource/ResourceSizeTable.product.srsizetable'
KEPT_PACK, KEPT_MANIFEST, RECORD = 'Pack/Bootup.pack.icons', 'manifest.tsv.icons', 'ukmm.json'
UKMM_TEST_FILE = 'Map/MainField/A-1/A-1.00_Clustering.sblwp'   # what UKMM looks for in a base-game folder (unpacked.rs)
DEFAULT_APP = Path('/Applications/Breath of the Wild.app')
CHUNK = 8 << 20


class UkmmError(Exception):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for block in iter(lambda: f.read(CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def app_version(app):
    """The BotW version folder the app holds its RomFS in (botw190 or botw160)."""
    extracted = app / 'Contents/Resources/totk/extracted'
    found = [v for v in VERSIONS if (extracted / v / 'romfs/runtime-index.bin').is_file()]
    if len(found) != 1:
        raise UkmmError(f'{app}: not a Breath of the Wild app (no extracted/botw190 or botw160 RomFS in it)')
    return found[0]


def data_folder(app):
    """~/Library/Application Support/MacNativeGames/<MNGDataFolder>, as the launcher reads it (BotW by default)."""
    name = 'BotW'
    plist = app / 'Contents/Info.plist'
    if plist.is_file():
        name = plistlib.loads(plist.read_bytes()).get('MNGDataFolder', name)
    return Path.home() / 'Library/Application Support/MacNativeGames' / name


def romfs_files(folder):
    """[(RomFS path, offset, size)] of an app RomFS folder (romfs.bin and runtime-index.bin), in image order."""
    files = []
    for name, (offset, size) in read_index(folder / 'runtime-index.bin').items():
        parts = name.split('/')
        if name.startswith('/') or any(part in ('', '.', '..') for part in parts):
            raise UkmmError(f'{folder}: unsafe path in the RomFS index: {name!r}')
        files.append((name, offset, size))
    return sorted(files, key=lambda item: item[1])


def unpack(folder, dest):
    """Every file of the image under dest; a file already there with the right size is kept. Returns (written, kept)."""
    written = kept = 0
    with open(folder / 'romfs.bin', 'rb') as image:
        for name, offset, size in romfs_files(folder):
            target = dest / name
            if target.is_file() and target.stat().st_size == size:
                kept += 1
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + '.part')
            image.seek(offset)
            left = size
            with open(part, 'wb') as out:
                while left:
                    block = image.read(min(CHUNK, left))
                    if not block:
                        raise UkmmError(f'{folder}/romfs.bin ends inside {name}')
                    out.write(block)
                    left -= len(block)
            os.replace(part, target)
            written += 1
    return written, kept


def dump(app, output):
    version = app_version(app)
    extracted = app / f'Contents/Resources/totk/extracted/{version}'
    parts = [(extracted / 'romfs', output / 'romfs', 'game (base + update)')]
    if (extracted / 'aoc/1/runtime-index.bin').is_file():
        parts.append((extracted / 'aoc/1', output / 'dlc', 'DLC'))
    need = sum(size for source, dest, _ in parts for name, _, size in romfs_files(source)
               if not ((dest / name).is_file() and (dest / name).stat().st_size == size))
    output.mkdir(parents=True, exist_ok=True)
    free = shutil.disk_usage(output).free
    if need > free:
        raise UkmmError(f'the dump needs {need / 2**30:.1f} GB more and {output} has {free / 2**30:.1f} GB free')
    for source, dest, what in parts:
        print(f'unpacking the {what} RomFS of {app.name} ({version}) into {dest} ...', flush=True)
        written, kept = unpack(source, dest)
        print(f'   {written} files written, {kept} already there')
    if not (output / 'romfs' / UKMM_TEST_FILE).is_file():
        raise UkmmError(f'{output / "romfs"} lacks {UKMM_TEST_FILE}, which UKMM checks for')
    (output / 'ukmm-dump.json').write_text(json.dumps({'app': str(app), 'version': version}, indent=2) + '\n')
    print('UKMM settings (Switch mode):')
    print(f'   Base game folder: {output / "romfs"}')
    print(f'   Update folder:    {output / "romfs"}')
    if len(parts) > 1:
        print(f'   DLC folder:       {output / "dlc"}')


# ---- sync ----

def deploy_folders(deploy):
    """(base RomFS, DLC RomFS) in a UKMM Switch deploy folder, in either layout."""
    for base, aoc in ((deploy / CONTENT / 'romfs', deploy / AOC / 'romfs'),
                      (deploy / CONTENT / NAMED / 'romfs', deploy / AOC / NAMED / 'romfs')):
        if base.is_dir():
            for folder in (base, aoc):
                if folder.is_symlink():
                    raise UkmmError(f'{folder} is a symbolic link: set UKMM\'s deploy method to Copy or Hard Link '
                                    '(Symlink deploys a whole folder, and the manifest would be written into UKMM\'s '
                                    'merge folder)')
            return base, aoc
    raise UkmmError(f'{deploy}: no {CONTENT}/romfs in it - is this the deploy folder of UKMM in Switch mode, '
                    'and has it deployed?')


def holds_files(folder):
    return any(p.name.lower() not in JUNK for p in folder.rglob('*') if p.is_file())


def link(port, target):
    """Make the port's mod folder a symbolic link to target. A folder holding files is moved aside, never deleted."""
    if port.is_symlink():
        if Path(os.readlink(port)) == target:
            return
        port.unlink()
    elif port.is_dir():
        if holds_files(port):
            backup = port.with_name(f'{port.name}.backup-{datetime.now():%Y%m%d-%H%M%S}')
            port.rename(backup)
            print(f'{port}: held files of its own; moved to {backup.name} (the game does not load it)')
        else:
            shutil.rmtree(port)
    elif port.exists():
        raise UkmmError(f'{port} is a file, not a folder')
    port.parent.mkdir(parents=True, exist_ok=True)
    port.symlink_to(target, target_is_directory=True)
    print(f'{port} -> {target}')


def write_manifest(folder, app, version, aoc_index=None, excludes=()):
    """make_mod_manifest.py on folder. Returns the RomFS paths of the manifest (empty when the folder changes nothing;
    then a stale manifest is removed, so the folder means "no mod")."""
    manifest = folder / 'manifest.tsv'
    command = [sys.executable, str(SCRIPTS / 'make_mod_manifest.py'), str(folder), '--app', str(app), '--version', version]
    if aoc_index:
        command += ['--aoc-index', str(aoc_index)]
    for pattern in excludes:
        command += ['--exclude', pattern]
    run = subprocess.run(command, capture_output=True, text=True)
    output = (run.stdout + run.stderr).strip()
    if run.returncode:
        if 'replaces or adds no file' in output:
            manifest.unlink(missing_ok=True)
            print(f'{folder}: no changed files; no manifest (the game loads no mod from it)')
            return set()
        raise UkmmError(f'make_mod_manifest.py failed for {folder}:\n{output}')
    for line in output.splitlines():
        if not line.startswith('left out (same as the original)'):   # UKMM deploys many unchanged files
            print('   ' + line)
    return manifest_paths(manifest)


def manifest_paths(path):
    return {line.split('\t', 1)[0] for line in path.read_text().splitlines() if line and not line.startswith('#')}


def vanilla_file(app, version, name):
    folder = app / f'Contents/Resources/totk/extracted/{version}/romfs'
    offset, size = read_index(folder / 'runtime-index.bin')[name]
    with open(folder / 'romfs.bin', 'rb') as image:
        image.seek(offset)
        return image.read(size)


@functools.lru_cache(maxsize=16)
def unpacked(member):
    return yaz0(member) if member[:4] == b'Yaz0' else member


def same(a, b):
    """Byte-identical, or the same once decompressed: UKMM writes every member of a pack it deploys again, so a member
    no mod changed comes out compressed differently."""
    return a == b or (a is not None and b is not None and unpacked(a) == unpacked(b))


def bntx_textures(bank):
    """name -> (BRTI offset, (width, height, format, tile, size, component mapping), data start) of a BNTX bank."""
    if bank[:8] != b'BNTX\0\0\0\0':
        raise ValueError('not a BNTX bank')
    table, out = struct.unpack_from('<Q', bank, 40)[0], {}
    for i in range(struct.unpack_from('<I', bank, 36)[0]):
        at = struct.unpack_from('<Q', bank, table + 8 * i)[0]
        if bank[at:at + 4] != b'BRTI':
            raise ValueError('not a BNTX texture')
        name_at = struct.unpack_from('<Q', bank, at + 96)[0]
        name = bank[name_at + 2:bank.index(0, name_at + 2)].decode()
        width, height, depth, layers, tile = struct.unpack_from('<5I', bank, at + 36)
        size = struct.unpack_from('<I', bank, at + 80)[0]
        start = struct.unpack_from('<Q', bank, struct.unpack_from('<Q', bank, at + 112)[0])[0]
        if depth != 1 or layers != 1 or start + size > len(bank):
            raise ValueError(f'unknown storage of texture {name}')
        shape = (width, height, struct.unpack_from('<I', bank, at + 28)[0], tile, size, bank[at + 88:at + 92])
        out[name] = (at, shape, start)
    return out


def merge_bntx(vanilla, icons, mod, where):
    """The mod's texture bank with the pixels of every texture the icon set changed, where the mod left that texture as
    it was and the size, format and tiling are the same in all three. Returns (bank or None, notes)."""
    try:
        vt, it, mt = bntx_textures(vanilla), bntx_textures(icons), bntx_textures(mod)
    except (ValueError, struct.error) as error:
        return None, [f'{where}: {error}']
    out, notes = bytearray(mod), []
    pixels = lambda bank, textures, name: bank[textures[name][2]:textures[name][2] + textures[name][1][4]]
    for name in it:
        if name in vt and it[name][1] == vt[name][1] and pixels(icons, it, name) == pixels(vanilla, vt, name):
            continue
        if name not in vt or name not in mt or not (it[name][1] == vt[name][1] == mt[name][1]):
            return None, [f'{where}/{name}: its size or format differs between the game, the icon set and the mod']
        if pixels(mod, mt, name) != pixels(vanilla, vt, name):
            notes.append(f'{where}/{name}: the mod changes this texture too; the mod\'s version is kept')
            continue
        start, size = mt[name][2], mt[name][1][4]
        out[start:start + size] = pixels(icons, it, name)
    return bytes(out), notes


def literal_yaz0(data, header):
    """Yaz0 with every byte a literal (no encoder needed); header[8:16] keeps the original's alignment field."""
    return (b'Yaz0' + struct.pack('>I', len(data)) + header[8:16] +
            b''.join(b'\xff' + data[i:i + 8] for i in range(0, len(data), 8)))


def yaz0_patched(compressed, data):
    """data (the same length as what compressed decodes to) Yaz0-encoded by reusing compressed's own tokens: a token
    that still produces the right bytes in data is kept, any other becomes literals. A merge that changes a few small
    parts of a large archive stays about as small as the original - a size the game's size table holds - in seconds,
    without an encoder."""
    size = struct.unpack_from('>I', compressed, 4)[0]
    if size != len(data):
        raise ValueError('patched Yaz0 needs data of the original length')
    out, items, o, i = bytearray(compressed[:16]), [], 0, 16

    def flush():
        while len(items) >= 8:
            group = items[:8]; del items[:8]
            out.append(sum(0x80 >> k for k, item in enumerate(group) if isinstance(item, int)))
            for item in group:
                out.extend(bytes([item]) if isinstance(item, int) else item)
    while o < size:
        code = compressed[i]; i += 1
        for bit in (0x80, 0x40, 0x20, 0x10, 8, 4, 2, 1):
            if o >= size:
                break
            if code & bit:
                items.append(data[o]); o += 1; i += 1
                continue
            first = compressed[i]; dist = ((first & 0xF) << 8 | compressed[i + 1]) + 1
            length = first >> 4
            token = compressed[i:i + (2 if length else 3)]
            i += len(token)
            length = length + 2 if length else compressed[i - 1] + 0x12
            length = min(length, size - o)
            src = o - dist
            if dist >= length:
                still = data[src:src + length] == data[o:o + length]
            else:   # overlapping copy: each byte repeats the one dist back
                still = all(data[o + k] == data[src + k] for k in range(length))
            if still:
                items.append(bytes(token))
            else:
                items.extend(data[o:o + length])
            o += length
        flush()
    while items:   # the last group, padded only in its flag byte
        group = items[:8]; del items[:8]
        out.append(sum(0x80 >> k for k, item in enumerate(group) if isinstance(item, int)))
        for item in group:
            out.extend(bytes([item]) if isinstance(item, int) else item)
    return bytes(out)


def merge_resource(vanilla, icons, mod, where):
    """The icon set's change from vanilla applied to the mod's version of one resource: the icon set's file when the mod
    left it as it was, else inside it - an archive member by member, a texture bank texture by texture. Returns
    (resource or None when the two cannot be combined, notes)."""
    if same(icons, vanilla) or icons == mod:
        return mod, []
    if same(mod, vanilla):
        return icons, []
    v, i, m = unpacked(vanilla), unpacked(icons), unpacked(mod)
    if v[:4] == i[:4] == m[:4] == b'SARC':
        merged, notes = merge_sarc(v, i, m, where)
    elif v[:4] == i[:4] == m[:4] == b'BNTX':
        merged, notes = merge_bntx(v, i, m, where)
    else:
        return None, []
    if merged is None:
        return None, notes
    if len(merged) > len(m):   # the size table sizes the mod's version
        return None, notes + [f'{where}: the combined file is larger than the mod\'s']
    if merged == m:
        return mod, notes
    if mod[:4] != b'Yaz0':
        return merged, notes
    if len(merged) == len(m):
        return yaz0_patched(mod, merged), notes
    return literal_yaz0(merged, mod), notes


def merge_sarc(vanilla, icons, mod, where=''):
    """The mod's archive with every member the icon set changes from vanilla (merge_resource). Returns
    (archive or None, notes)."""
    vm, im, um = sarc_members(vanilla), sarc_members(icons), sarc_members(mod)
    replacements, notes = {}, []
    for name, (lo, hi) in sorted(im.items()):
        theirs = icons[lo:hi]
        original = vanilla[slice(*vm[name])] if name in vm else None
        if original is not None and same(theirs, original):
            continue
        label = f'{where}/{name}' if where else name
        if name not in um or original is None:
            notes.append(f'{label}: not in both the game\'s and the mod\'s archive; the icon set\'s version is left out')
            continue
        merged, member_notes = merge_resource(original, theirs, mod[slice(*um[name])], label)
        notes += member_notes
        if merged is None:
            notes.append(f'{label}: the mod changes it too; the mod\'s version is kept, so the icon set\'s change to it '
                         '(button icons, quick-menu fix) is off while the mod is deployed')
        elif merged != mod[slice(*um[name])]:
            replacements[name] = merged
    return (sarc_replace(mod, replacements) if replacements else mod), notes


def merge_bootup(vanilla, icons, mod):
    """The mod's Bootup.pack with every change the icon set makes to the game's, down to members of archives in it and
    textures of texture banks, unless the mod changes the same thing. Returns (archive, notes)."""
    return merge_sarc(vanilla, icons, mod)


def rstb_read(data):
    """(crc32 -> size, name -> size, names in order) of a Switch ResourceSizeTable (Yaz0 or not)."""
    data = unpacked(data)
    if data[:4] != b'RSTB':
        raise UkmmError(f'{RSTB} is not a resource size table')
    crcs, count = struct.unpack_from('<II', data, 4)
    table = dict(struct.unpack_from('<II', data, 12 + 8 * i) for i in range(crcs))
    at, names, order = 12 + 8 * crcs, {}, []
    for _ in range(count):
        name = data[at:at + 128].split(b'\0', 1)[0].decode()
        names[name] = struct.unpack_from('<I', data, at + 128)[0]
        order.append(name)
        at += 132
    return table, names, order


def rstb_write(table, names, order):
    body = b'RSTB' + struct.pack('<II', len(table), len(names))
    body += b''.join(struct.pack('<II', crc, table[crc]) for crc in sorted(table))
    body += b''.join(name.encode().ljust(128, b'\0') + struct.pack('<I', names[name]) for name in order)
    # Yaz0 with every byte a literal: the game decompresses it as any other, no encoder needed
    return (b'Yaz0' + struct.pack('>I', len(body)) + bytes(8) +
            b''.join(b'\xff' + body[i:i + 8] for i in range(0, len(body), 8)))


def resource_names(data, name, found, prefix=''):
    """Add the canonical name of a resource and, for an archive, of every resource in it (UKMM's canonicalize: every
    '.s' becomes '.'; archive members by their own paths, under Aoc/0010/ in the DLC like the files themselves - the
    table sizes a map unit in AocMainField.pack as Aoc/0010/Map/MainField/...)."""
    found.add(prefix + name.replace('.s', '.'))
    try:
        inner = yaz0(data) if data[:4] == b'Yaz0' else data   # not unpacked(): its cache would hold every archive
        members = sarc_members(inner) if inner[:4] == b'SARC' else {}
    except (ValueError, AssertionError, struct.error):
        return
    for member, (lo, hi) in members.items():
        resource_names(inner[lo:hi], member, found, prefix)


def deployed_names(base, aoc):
    found = set()
    for root, prefix in ((base, ''), (aoc, 'Aoc/0010/')):
        if not root.is_dir():
            continue
        for file in root.rglob('*'):
            rel = file.relative_to(root).as_posix()
            if (not file.is_file() or rel in ('manifest.tsv', RSTB) or file.name.lower() in JUNK or rel.endswith('.part')
                    or rel.endswith(KEPT)):
                continue
            resource_names(file.read_bytes(), rel, found, prefix)
    return found


def fix_rstb(base, aoc, app, version, data):
    """UKMM writes its resource size table from the stock 1.6.0 table its rstb crate carries, not from the game dump
    (deploy.rs apply_rstb), so on 1.9.0 every other entry would say 1.6.0's size - smaller for some resources, which
    the game then reserves too little memory for. The table is rebuilt from the app's own: an entry keeps the app's size
    unless it names a resource this deploy holds (a file, or a member of an archive in it), which gets the larger of
    the two sizes, or no entry when UKMM removed it.

    The table is rewritten in the deploy folder, so UKMM's own is kept next to it (<name>.mod-original, which
    make_mod_manifest.py skips) and <data>/ukmm-sync.json records what this wrote: a later sync without a new deploy
    starts from UKMM's table again, not from its own output."""
    path = base / RSTB
    kept, record_path = path.with_name(path.name + KEPT), data / 'ukmm-sync.json'
    if not path.is_file():
        kept.unlink(missing_ok=True)
        return
    record = json.loads(record_path.read_text()) if record_path.is_file() else {}
    if not (kept.is_file() and record.get('rstb') == sha256_file(path)):   # a table UKMM deployed since
        shutil.copyfile(path, kept)
    vanilla_bytes = vanilla_file(app, version, RSTB)
    table, names, order = rstb_read(vanilla_bytes)
    ukmm_table, ukmm_names, _ = rstb_read(kept.read_bytes())
    raised = removed = 0
    for name in deployed_names(base, aoc):
        crc = zlib.crc32(name.encode())
        size = ukmm_names.get(name, ukmm_table.get(crc))
        if size is None:
            # UKMM removes the entry of a resource whose size it cannot calculate, so the game sizes it from the file;
            # the app's own entry would reserve the original's size for the mod's (larger) file
            if name in names:
                del names[name]
                order.remove(name)
                removed += 1
            elif crc in table:
                del table[crc]
                removed += 1
            continue
        if name in names:
            if size > names[name]:
                names[name] = size
                raised += 1
        elif size > table.get(crc, 0):
            table[crc] = size
            raised += 1
    ignored = sum(1 for crc, size in ukmm_table.items() if table.get(crc) != size)
    replace_bytes(path, vanilla_bytes if raised == removed == 0 else rstb_write(table, names, order))
    record['rstb'] = sha256_file(path)
    record_path.write_text(json.dumps(record) + '\n')
    print(f'size table: rebuilt from the app\'s own; for resources this deploy holds, {raised} entries raised and '
          f'{removed} removed as UKMM removed them; {ignored} of UKMM\'s stock-table sizes not used')


def replace_bytes(path, data):
    if path.is_file() and path.read_bytes() == data:
        return
    part = path.with_name(path.name + '.part')
    part.write_bytes(data)
    os.replace(part, path)


def icon_sets(data):
    root = data / 'button-icons'
    return sorted(p for p in root.iterdir() if (p / 'manifest.tsv').is_file()) if root.is_dir() else []


def kept_state(style):
    """Save the set's own Bootup.pack and manifest next to them, unless what is there now is what the last sync wrote.
    Returns (the set's own manifest text, its own Bootup.pack or None)."""
    record_path, manifest = style / RECORD, style / 'manifest.tsv'
    record = json.loads(record_path.read_text()) if record_path.is_file() else {}
    pack = style / BOOTUP
    current = {'manifest': sha256_file(manifest), 'bootup': sha256_file(pack) if pack.is_file() else None}
    if record != current:   # first sync, or the set was regenerated since (an app update): this is the set's own state
        shutil.copyfile(manifest, style / KEPT_MANIFEST)
        if pack.is_file():
            shutil.copyfile(pack, style / KEPT_PACK)
        else:
            (style / KEPT_PACK).unlink(missing_ok=True)
    kept_pack = style / KEPT_PACK
    return (style / KEPT_MANIFEST).read_text(), (kept_pack.read_bytes() if kept_pack.is_file() else None)


def sync_icons(data, app, version, mod_bootup, mod_paths):
    """Give every button-icon set the mod's Bootup.pack (merged with the set's change) and leave out of each set any
    other path the mod replaces (the mod wins)."""
    vanilla = vanilla_file(app, version, BOOTUP) if mod_bootup is not None else None
    for style in icon_sets(data):
        own_manifest, own_pack = kept_state(style)
        lines, notes = [], []
        for line in own_manifest.splitlines():
            name = line.split('\t', 1)[0]
            if line.startswith('#') or not line:
                lines.append(line)
            elif name == BOOTUP and mod_bootup is not None:
                continue   # written below
            elif name in mod_paths:
                notes.append(f'{name}: the mod replaces it; the icon set\'s version is off while the mod is deployed')
            else:
                lines.append(line)
        if mod_bootup is not None:
            merged, merge_notes = merge_bootup(vanilla, own_pack if own_pack is not None else vanilla, mod_bootup)
            notes += merge_notes
            replace_bytes(style / BOOTUP, merged)
            lines.append(f'{BOOTUP}\t{len(merged)}\t{hashlib.sha256(merged).hexdigest()}\t'
                         f'{hashlib.sha256(vanilla).hexdigest()}')
        elif own_pack is not None:
            replace_bytes(style / BOOTUP, own_pack)
        elif (style / BOOTUP).is_file():
            (style / BOOTUP).unlink()
        (style / 'manifest.tsv').write_text('\n'.join(lines) + '\n')
        (style / RECORD).write_text(json.dumps({'manifest': sha256_file(style / 'manifest.tsv'),
                                                'bootup': sha256_file(style / BOOTUP) if (style / BOOTUP).is_file() else None}))
        state = 'merged with the mod\'s Bootup.pack' if mod_bootup is not None else 'its own files'
        print(f'button icons {style.name}: {state}')
        for note in notes:
            print(f'   {note}')


def game_running(app):
    """The launcher in Contents/MacOS replaces itself with Contents/Resources/totk/build/totk-native: either counts."""
    run = subprocess.run(['pgrep', '-f', f'{app.resolve()}/Contents/'], capture_output=True, text=True)
    return run.returncode == 0


def fingerprint(app, version, data, base, aoc):
    """What a sync reads and writes: every deploy and icon-set file (path, size, modification time), the app's version
    and this script. Equal to the record of the last sync: nothing to do."""
    digest = hashlib.sha256(f'{app.resolve()}\0{version}\0'.encode())
    digest.update(Path(__file__).read_bytes())
    for root in (base, aoc, data / 'button-icons'):
        if not root.is_dir():
            continue
        for file in sorted(root.rglob('*')):
            if file.is_file():
                st = file.stat()
                digest.update(f'{file}\0{st.st_size}\0{st.st_mtime_ns}\n'.encode())
    for link_path in (data / 'mods' / version, data / 'mods' / f'{version}-aoc' / '1'):
        digest.update(f'{link_path}\0{os.readlink(link_path) if link_path.is_symlink() else "-"}\n'.encode())
    return digest.hexdigest()


def record(data):
    path = data / 'ukmm-sync.json'
    return json.loads(path.read_text()) if path.is_file() else {}


def sync(deploy, app, launch, data=None):
    version = app_version(app)
    data = data or data_folder(app)
    if game_running(app):
        raise UkmmError(f'{app.name} is running: quit the game first (the mod files must not change while it runs)')
    base, aoc = deploy_folders(deploy.resolve())
    if record(data).get('fingerprint') == fingerprint(app, version, data, base, aoc):
        print('nothing changed since the last sync: the mod folders are ready')
        if launch:
            subprocess.run(['open', str(app)], check=True)
            print(f'opened {app}')
        return
    has_aoc = (app / f'Contents/Resources/totk/extracted/{version}/aoc/1/runtime-index.bin').is_file()
    link(data / 'mods' / version, base)
    if has_aoc and aoc.is_dir():
        link(data / 'mods' / f'{version}-aoc' / '1', aoc)
    elif aoc.is_dir() and holds_files(aoc):
        print(f'{aoc}: DLC files, but {app.name} holds no DLC; they are not loaded')

    mod_bootup = None
    sets = icon_sets(data)
    if (base / BOOTUP).is_file() and sets:
        candidate = (base / BOOTUP).read_bytes()
        if hashlib.sha256(candidate).digest() != hashlib.sha256(vanilla_file(app, version, BOOTUP)).digest():
            mod_bootup = candidate
    elif (base / BOOTUP).is_file():
        print(f'no button-icon sets in {data / "button-icons"}: the game turns its button icons off while a mod '
              f'replaces {BOOTUP}')
    fix_rstb(base, aoc, app, version, data)
    print(f'{data / "mods" / version}:')
    paths = write_manifest(base, app, version, excludes=[BOOTUP] if mod_bootup is not None else ())
    if has_aoc and aoc.is_dir():
        print(f'{data / "mods" / f"{version}-aoc" / "1"}:')
        write_manifest(aoc, app, version, aoc_index=1)
    if sets:
        sync_icons(data, app, version, mod_bootup, paths)
    done = record(data)
    done['fingerprint'] = fingerprint(app, version, data, base, aoc)
    (data / 'ukmm-sync.json').write_text(json.dumps(done) + '\n')
    if launch:
        subprocess.run(['open', str(app)], check=True)
        print(f'opened {app}')


AGENT = 'org.macnativegames.botw.ukmm-sync'


def deploy_finished(pending):
    """UKMM writes nx/pending.yml with every list empty when a deploy is done (deploy.rs: clear, then save); after an
    Apply it lists the files still to deploy."""
    text = pending.read_text() if pending.is_file() else ''
    return bool(text) and all(line.strip() in ('folders: {}', 'files: []') or line.endswith(':')
                              for line in text.splitlines() if line.strip())


def notify(message):
    subprocess.run(['osascript', '-e', f'display notification {json.dumps(message)} with title "Breath of the Wild mods"'],
                   capture_output=True)


def watch(deploy, app, pending):
    """Run by the login agent whenever UKMM writes pending.yml: after a finished deploy, sync, and say so."""
    if not deploy_finished(pending):
        return
    data = data_folder(app)
    lock = data / '.ukmm-sync.lock'
    try:
        lock.mkdir()
    except FileExistsError:
        return   # a sync is running; it reads the deploy as it is when it gets there
    try:
        sync(deploy, app, False)
        notify('Mods synced: the game is ready to open from Finder.')
    except UkmmError as error:
        notify(f'Mods not synced: {error}')
        raise
    finally:
        lock.rmdir()


def install_watcher(deploy, app, pending):
    data = data_folder(app)
    plist = Path.home() / f'Library/LaunchAgents/{AGENT}.plist'
    plist.parent.mkdir(parents=True, exist_ok=True)
    plist.write_bytes(plistlib.dumps({
        'Label': AGENT,
        'ProgramArguments': [sys.executable, str(Path(__file__).resolve()), 'watch', '--deploy', str(deploy.resolve()),
                             '--app', str(app.resolve()), '--pending', str(pending)],
        'WatchPaths': [str(pending)],
        'StandardOutPath': str(data / 'ukmm-sync.log'),
        'StandardErrorPath': str(data / 'ukmm-sync.log'),
    }))
    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{AGENT}'], capture_output=True)
    subprocess.run(['launchctl', 'bootstrap', f'gui/{os.getuid()}', str(plist)], check=True)
    print(f'{plist}: installed; every UKMM deploy now runs sync (log: {data / "ukmm-sync.log"})')


def uninstall_watcher():
    plist = Path.home() / f'Library/LaunchAgents/{AGENT}.plist'
    subprocess.run(['launchctl', 'bootout', f'gui/{os.getuid()}/{AGENT}'], capture_output=True)
    plist.unlink(missing_ok=True)
    print(f'{plist}: removed')


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    commands = parser.add_subparsers(dest='command', required=True)
    d = commands.add_parser('dump', help='unpack the app\'s RomFS into a folder for UKMM\'s game dump settings')
    d.add_argument('--app', type=Path, default=DEFAULT_APP)
    d.add_argument('--output', type=Path, required=True)
    s = commands.add_parser('sync', help='after a UKMM deploy: link the mod folders, write the manifests, merge Bootup.pack')
    s.add_argument('--deploy', type=Path, required=True, help='UKMM\'s deploy output folder (Settings > Deployment)')
    s.add_argument('--app', type=Path, default=DEFAULT_APP)
    s.add_argument('--data', type=Path, help='the app\'s data folder (default: from the app\'s Info.plist)')
    s.add_argument('--launch', action='store_true', help='open the app afterwards')
    pending_default = Path.home() / 'Library/Application Support/ukmm/nx/pending.yml'
    for name, text in (('watch', 'run by the login agent after UKMM writes pending.yml'),
                       ('install-watcher', 'sync after every UKMM deploy, so the game opens from Finder')):
        w = commands.add_parser(name, help=text)
        w.add_argument('--deploy', type=Path, required=True)
        w.add_argument('--app', type=Path, default=DEFAULT_APP)
        w.add_argument('--pending', type=Path, default=pending_default, help='UKMM\'s nx/pending.yml')
    commands.add_parser('uninstall-watcher', help='remove the login agent')
    args = parser.parse_args()
    try:
        if args.command == 'dump':
            dump(args.app, args.output)
        elif args.command == 'sync':
            sync(args.deploy, args.app, args.launch, args.data)
        elif args.command == 'watch':
            watch(args.deploy, args.app, args.pending)
        elif args.command == 'install-watcher':
            install_watcher(args.deploy, args.app, args.pending)
        else:
            uninstall_watcher()
    except UkmmError as error:
        sys.exit(f'ukmm.py: {error}')


if __name__ == '__main__':
    main()
