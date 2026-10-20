#!/usr/bin/env python3
"""Add a "Button icons" row (Switch / Xbox / PlayStation) to the game's own System > Options menu, from the player's RomFS.

How the options menu works (Tears of the Kingdom 1.4.3; see docs/controls-option.md):
- Its rows are data: UI/OptionSetTable/OptionSetTable.game__ui__OptionSetTable.bgyml in Pack/Bootup.Nin_NX_NVN.pack lists
  each row's OptionType, ButtonType (Toggle, Selection, Button, Separator) and ChoiceType names. The screen clones its
  row templates (layout SystemOption_00) for each entry, so no layout changes.
- OptionType is a fixed enum. Type 7, IsControlStickUpDownReverse, is in it but unused: not in the table, no saved value,
  no text, and no code reads it by hash. This row uses it.
- Row text is LayoutMsg/SystemOption_00.msbt: the name is 10NN and the description 00NN (NN = type - 1, so 1006 and
  0006), the choices 10NN_VV in table order.
- A row's value is the GameData struct OptionData's member named after the OptionType; the screen reads and writes it
  through the struct (murmur3 of "OptionData", then of the member name). Selection values are Enum entries whose values
  are murmur3 hashes of ChoiceType names, so the choices reuse three existing ChoiceType names (Normal, Pro, Dark) as
  Switch, Xbox and PlayStation. GameData/GameDataList gets the struct member and the Enum (SaveFileIndex 1: option.sav).
- option.sav is read by hash: an entry the list lacks is skipped and a missing one keeps its default, so saves load
  both with and without this row. Its stored size and the offsets in the list's MetaData grow by one 8-byte entry; the
  size model is checked against the original numbers first.
- The game reads its button icons from Font/Font.Nin_NX_NVN.bfarc once at start. An archive is written for the Xbox and
  the PlayStation style (scripts/make_button_icons.py); the runtime serves the one option.sav selects (none for Switch),
  so a change shows from the next start.
- System/Resource/ResourceSizeTable gets the new sizes of the files this changes (each keeps its original allowance
  above the file size), so the game sizes their buffers for them.

Output (each folder with a manifest.tsv that runtime/romfs.c checks at start):
  <output>/menu                    the option table, GameData list, size table and the messages of every language
  <output>/icons-<xbox|playstation>  the font archive

usage: make_controls_option.py --output <folder> (--app <Tears of the Kingdom.app> --version v143 | --romfs <folder>)
"""
import argparse
import hashlib
import json
import shutil
import struct
import sys
import zlib
from pathlib import Path

try:
    import compression.zstd as zstd
except ImportError:
    sys.exit('needs Python 3.14 (compression.zstd): run it with python3.14')
from make_mod_manifest import VERSIONS, read_index
from nx_formats import (Int, Msbt, UInt, UInt64, byml_equal, byml_read, byml_write, sarc_members, sarc_replace)
import make_button_icons as icons

OPTION_PACK = 'Pack/Bootup.Nin_NX_NVN.pack.zs'
OPTION_TABLE = 'UI/OptionSetTable/OptionSetTable.game__ui__OptionSetTable.bgyml'
MESSAGES = 'LayoutMsg/SystemOption_00.msbt'
OPTION_TYPE = 'IsControlStickUpDownReverse'   # OptionType 7: text 1006 / 0006
AFTER = 'IsChangeJumpButton'                  # the row goes below "Swap jump controls", with the other controls
CHOICES = ('Normal', 'Pro', 'Dark')           # ChoiceType names standing for Switch, Xbox, PlayStation
STYLES = ('xbox', 'playstation')                # Switch is the game's own font
SAVE_TYPES = ('Bool BoolArray Int IntArray Float FloatArray Enum EnumArray Vector2 Vector2Array Vector3 Vector3Array '
              'String16 String16Array String32 String32Array String64 String64Array Binary BinaryArray UInt UIntArray '
              'Int64 Int64Array UInt64 UInt64Array WString16 WString16Array WString32 WString32Array WString64 '
              'WString64Array Bool64bitKey').split()   # the order of a save file's type sections
OPTION_SAVE = 1                               # SaveFileIndex of option.sav

# Row name, description (line breaks as the game's own descriptions use them) per message archive language. The choice
# names are the consoles' names in every language; they are plain text because the choice box draws with a different
# font stack per language (Nintendo's text font, or the system's Chinese and Korean fonts) that has no button icons.
TEXT = {
    'en': ('Button icons', "Choose which controller's buttons appear in\non-screen prompts. Takes effect the next time\nyou start the game."),
    'de': ('Tastensymbole', 'Lege fest, welche Controller-Tasten in den\nHinweisen auf dem Bildschirm erscheinen. Gilt\nab dem nächsten Spielstart.'),
    'fr': ('Icônes des boutons', "Choisissez les boutons de manette affichés\ndans les indications à l'écran. Prend effet\nau prochain lancement du jeu."),
    'es': ('Iconos de botones', 'Elige qué botones de mando aparecen en las\nindicaciones en pantalla. Se aplicará la\npróxima vez que inicies el juego.'),
    'it': ('Icone dei pulsanti', 'Scegli quali pulsanti del controller mostrare\nnei suggerimenti a schermo. La modifica avrà\neffetto al prossimo avvio del gioco.'),
    'pt': ('Ícones dos botões', 'Escolha quais botões de controle aparecem nas\nindicações na tela. A mudança vale a partir da\npróxima vez que você iniciar o jogo.'),
    'nl': ('Knoppictogrammen', 'Kies welke controllerknoppen in de aanwijzingen\nop het scherm verschijnen. Wordt toegepast\nwanneer je het spel opnieuw start.'),
    'ru': ('Значки кнопок', 'Выберите, кнопки какого контроллера\nпоказывать в подсказках на экране. Изменение\nвступит в силу при следующем запуске игры.'),
    'ja': ('ボタンアイコン', '画面のボタン表示に使うコントローラーを\n選びます。次にゲームを起動したときに\n反映されます。'),
    'ko': ('버튼 아이콘', '화면의 버튼 안내에 표시할 컨트롤러를\n선택합니다. 다음에 게임을 시작할 때\n적용됩니다.'),
    'zh-Hans': ('按键图标', '选择画面上的按键提示显示哪种手柄的按键。\n下次启动游戏时生效。'),
    'zh-Hant': ('按鍵圖示', '選擇畫面上的按鍵提示顯示哪種控制器的按鍵。\n下次啟動遊戲時生效。'),
}
LANGUAGE = {'CNzh': 'zh-Hans', 'TWzh': 'zh-Hant', 'JPja': 'ja', 'KRko': 'ko'}   # other archives: by their last two letters
CHOICE_NAMES = ('Switch', 'Xbox', 'PlayStation')


def murmur3(text, seed=0):
    """MurmurHash3 x86 32-bit, the game's name hash (GameData keys, enum values)."""
    data = text.encode(); h = seed; c1, c2 = 0xcc9e2d51, 0x1b873593; n = len(data) // 4

    def mix(k):
        k = (k * c1) & 0xffffffff; k = ((k << 15) | (k >> 17)) & 0xffffffff
        return (k * c2) & 0xffffffff
    for i in range(n):
        h ^= mix(int.from_bytes(data[i * 4:i * 4 + 4], 'little'))
        h = ((h << 13) | (h >> 19)) & 0xffffffff; h = (h * 5 + 0xe6546b64) & 0xffffffff
    tail = data[n * 4:]
    if tail:
        h ^= mix(int.from_bytes(tail, 'little'))
    h ^= len(data); h ^= h >> 16; h = (h * 0x85ebca6b) & 0xffffffff; h ^= h >> 13
    h = (h * 0xc2b2ae35) & 0xffffffff
    return h ^ (h >> 16)


def option_save_layout(data):
    """(option.sav table size, AllData table size) predicted from a GameDataList's entries: a 0x20 header, a type
    marker per save type, 8 bytes per entry and an end marker; AllData counts every entry except Bool64bitKey."""
    entries = data['Data']
    saved = sum(1 for t in SAVE_TYPES for e in entries.get(t, []) if e['SaveFileIndex'] == OPTION_SAVE)
    every = sum(len(entries.get(t, [])) for t in SAVE_TYPES if t != 'Bool64bitKey')
    head = 0x20 + 8 * len(SAVE_TYPES) + 8
    return head + 8 * saved, head + 8 * every


def add_option_data(data):
    """GameDataList with the OptionData member and its Enum added, MetaData grown to match."""
    meta = data['MetaData']
    assert meta['SaveDirectory'][OPTION_SAVE] == 'option.sav', 'unexpected save file order'
    assert option_save_layout(data) == (meta['SaveDataOffsetPos'][OPTION_SAVE], meta['AllDataSaveOffset']), \
        'the option.sav size model does not match this GameDataList'
    flat = murmur3(f'OptionData.{OPTION_TYPE}')
    struct_entry = [s for s in data['Data']['Struct'] if s['Hash'] == murmur3('OptionData')]
    assert len(struct_entry) == 1, 'no OptionData struct'
    members = struct_entry[0]['DefaultValue']
    for kind, entries in data['Data'].items():
        assert all(e.get('Hash') != flat for e in entries), f'{OPTION_TYPE} already has a GameData entry ({kind})'
    assert all(m['Hash'] != murmur3(OPTION_TYPE) for m in members), f'OptionData already has {OPTION_TYPE}'
    template = [e for e in data['Data']['Enum'] if e['Hash'] == murmur3('OptionData.DisplayMode')]
    assert len(template) == 1, 'no OptionData.DisplayMode to copy the entry layout from'
    template = template[0]
    entry = {'DefaultValue': UInt(murmur3(CHOICES[0])), 'Hash': UInt(flat), 'RawValues': list(CHOICES),
             'ResetTypeValue': Int(template['ResetTypeValue']), 'SaveFileIndex': Int(OPTION_SAVE),
             'Values': [UInt64(murmur3(c)) for c in CHOICES]}
    assert entry.keys() == template.keys()
    members.append({'Hash': UInt(murmur3(OPTION_TYPE)), 'Value': UInt(flat)})
    data['Data']['Enum'].append(entry)
    for key in ('SaveDataOffsetPos', 'SaveDataSize'):
        meta[key][OPTION_SAVE] = Int(meta[key][OPTION_SAVE] + 8)
    for key in ('AllDataSaveOffset', 'AllDataSaveSize'):
        meta[key] = Int(meta[key] + 8)
    assert option_save_layout(data) == (meta['SaveDataOffsetPos'][OPTION_SAVE], meta['AllDataSaveOffset'])
    return data


def add_option_row(table):
    rows = table['OptionSetArray']
    assert all(r.get('OptionType') != OPTION_TYPE for r in rows), f'the option table already has {OPTION_TYPE}'
    after = [i for i, r in enumerate(rows) if r.get('OptionType') == AFTER]
    assert len(after) == 1, f'no {AFTER} row'
    rows.insert(after[0] + 1, {'ButtonType': 'Selection', 'ChoiceType': list(CHOICES), 'OptionType': OPTION_TYPE})
    return table


def add_option_text(msbt, language):
    name, description = TEXT[language]
    for label in ('1006', '0006', *(f'1006_{i:02d}' for i in range(len(CHOICES)))):
        assert label not in msbt.labels, f'{MESSAGES} already has {label}'
    assert '1005' in msbt.labels and '0005' in msbt.labels, f'{MESSAGES} lacks the neighbouring rows'
    msbt.set('1006', name.encode('utf-16-le')); msbt.set('0006', description.encode('utf-16-le'))
    for i, choice in enumerate(CHOICE_NAMES):
        msbt.set(f'1006_{i:02d}', choice.encode('utf-16-le'))
    return msbt


class RomFS:
    """A verified RomFS image: index.json of the extraction (during a build) or the app's runtime-index.bin."""
    def __init__(self, folder):
        if (folder / 'index.json').is_file():
            self.index = {f['path']: (f['offset'], f['size']) for f in json.loads((folder / 'index.json').read_text())['files']}
        else:
            self.index = read_index(folder / 'runtime-index.bin')
        self.image = (folder / 'romfs.bin').open('rb')
        pack = zstd.decompress(self.read('Pack/ZsDic.pack.zs')); self.dictionaries = {}
        for lo, hi in sarc_members(pack).values():
            d = zstd.ZstdDict(pack[lo:hi]); self.dictionaries[d.dict_id] = d

    def read(self, path):
        offset, size = self.index[path]; self.image.seek(offset); data = self.image.read(size)
        assert len(data) == size
        return data

    def glob(self, prefix, suffix):
        found = sorted(p for p in self.index if p.startswith(prefix) and p.endswith(suffix))
        assert found, f'no {prefix}*{suffix} in the RomFS'
        return found

    def unpack(self, path):
        """(decompressed bytes, dictionary or None) of a .zs file."""
        raw = self.read(path); info = zstd.get_frame_info(raw)
        dictionary = self.dictionaries[info.dictionary_id] if info.dictionary_id else None
        data = zstd.decompress(raw, zstd_dict=dictionary); assert len(data) == info.decompressed_size
        return data, dictionary

    @staticmethod
    def pack(data, dictionary):
        out = zstd.compress(data, level=19, zstd_dict=dictionary)
        assert zstd.decompress(out, zstd_dict=dictionary) == data
        return out


def edit_byml(data, change):
    """BYML bytes with change(value) applied, written the way that gives back the original bytes unchanged (long values
    shared in 1.4.3's files, not in 1.0.0's); the edit must re-read as written."""
    value, order, version = byml_read(data)
    modes = [share for share in (True, False) if byml_write(value, order, version, share) == data]
    assert modes, 'no BYML rewrite of the unchanged document gives the original bytes'
    value = change(value)
    out = byml_write(value, order, version, modes[0])
    assert byml_equal(byml_read(out)[0], value)
    return out


def rstb_update(data, sizes):
    """ResourceSizeTable bytes with the entries of `sizes` (path -> (original size, new size[, extra])) raised so each
    keeps its allowance above the file size: new value = max(old value, new size + old value - original size + extra)."""
    assert data[:6] == b'RESTBL', 'not a ResourceSizeTable'
    version, name_size, crcs, names = struct.unpack_from('<IIII', data, 6)
    out = bytearray(data); found = {}
    for i in range(crcs):
        crc, value = struct.unpack_from('<II', data, 22 + i * 8); found[crc] = 22 + i * 8 + 4
    named = {}
    at = 22 + crcs * 8
    for i in range(names):
        name = data[at:at + name_size].split(b'\0')[0].decode(); named[name] = at + name_size; at += name_size + 4
    report = []
    for path, (old_size, new_size, *extra) in sorted(sizes.items()):
        where = named.get(path) or found.get(zlib.crc32(path.encode()))
        if where is None:   # the game sizes files the table does not list from the file itself
            report.append(f'{path}: not listed'); continue
        value = struct.unpack_from('<I', out, where)[0]
        raised = max(value, new_size + value - old_size + sum(extra))
        struct.pack_into('<I', out, where, raised); report.append(f'{path}: {value} -> {raised}')
    return bytes(out), report


def rstb_value(romfs, path):
    """The ResourceSizeTable value of a RomFS path (None when the table does not list it)."""
    data, _ = romfs.unpack(romfs.glob('System/Resource/ResourceSizeTable.Product.', '.rsizetable.zs')[0])
    _, name_size, crcs, names = struct.unpack_from('<IIII', data, 6)
    at = 22 + crcs * 8
    for i in range(names):
        if data[at:at + name_size].split(b'\0')[0].decode() == path:
            return struct.unpack_from('<I', data, at + name_size)[0]
        at += name_size + 4
    crc = zlib.crc32(path.encode())
    for i in range(crcs):
        c, value = struct.unpack_from('<II', data, 22 + i * 8)
        if c == crc:
            return value
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--output', type=Path, required=True, help='folder for menu/ and icons-<style>/ (replaced)')
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--app', type=Path, help='the built Tears of the Kingdom.app')
    source.add_argument('--romfs', type=Path, help='a folder holding romfs.bin and runtime-index.bin')
    parser.add_argument('--version', choices=VERSIONS, help='the game version, with --app')
    args = parser.parse_args()
    romfs_dir = args.romfs
    if args.app:
        if not args.version:
            parser.error('name the game version with --version')
        romfs_dir = args.app / f'Contents/Resources/totk/extracted/{args.version}/romfs'
    romfs = RomFS(romfs_dir)
    files, sizes = {}, {}

    data, dictionary = romfs.unpack(OPTION_PACK)
    original = data[slice(*sarc_members(data)[OPTION_TABLE])]
    table = edit_byml(original, add_option_row)
    pack = sarc_replace(data, {OPTION_TABLE: table})
    files[OPTION_PACK] = romfs.pack(pack, dictionary); sizes[OPTION_PACK[:-3]] = (len(data), len(pack))
    # The table's entry also budgets the objects the game builds from it (about 440 bytes a row in 1.4.3; at 16 rows
    # the 17th's allocation fails): the new row gets twice the average allowance of the existing ones.
    rows = len(byml_read(original)[0]['OptionSetArray'])
    sizes[OPTION_TABLE] = (len(original), len(table), 2 * (rstb_value(romfs, OPTION_TABLE) - len(original)) // rows)

    for path in romfs.glob('GameData/GameDataList.Product.', '.byml.zs'):
        data, dictionary = romfs.unpack(path)
        out = edit_byml(data, add_option_data)
        files[path] = romfs.pack(out, dictionary); sizes[path[:-3]] = (len(data), len(out))

    for path in romfs.glob('Mals/', '.sarc.zs'):
        region = path.split('/')[1].split('.')[0]
        language = LANGUAGE.get(region, region[2:])
        data, dictionary = romfs.unpack(path)
        original = data[slice(*sarc_members(data)[MESSAGES])]
        msbt = Msbt(original); assert msbt.bytes() == original, f'{path}: MSBT rewrite differs'
        text = add_option_text(msbt, language).bytes()
        archive = sarc_replace(data, {MESSAGES: text})
        files[path] = romfs.pack(archive, dictionary); sizes[path[:-3]] = (len(data), len(archive))

    fonts, font_sizes = {}, []
    for style in STYLES:
        blob, count, unpacked = icons.font_archive(romfs.read, romfs.dictionaries, style)
        fonts[style] = blob; font_sizes.append(unpacked)
    font_original = zstd.get_frame_info(romfs.read(icons.ARCHIVE)).decompressed_size
    sizes[icons.ARCHIVE[:-3]] = (font_original, max(font_sizes))

    rstb = romfs.glob('System/Resource/ResourceSizeTable.Product.', '.rsizetable.zs')
    assert len(rstb) == 1, rstb
    data, dictionary = romfs.unpack(rstb[0])
    table, report = rstb_update(data, sizes)
    files[rstb[0]] = romfs.pack(table, dictionary)

    if args.output.exists():
        shutil.rmtree(args.output)
    def write(folder, entries):   # the files and the manifest.tsv runtime/romfs.c checks (every file replaces one)
        lines = []
        for path, blob in sorted(entries.items()):
            target = folder / path; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(blob)
            original = hashlib.sha256(romfs.read(path)).hexdigest()
            lines.append(f'{path}\t{len(blob)}\t{hashlib.sha256(blob).hexdigest()}\t{original}')
        (folder / 'manifest.tsv').write_text('# path\tsize\tsha256\toriginal_sha256 (generated by scripts/make_controls_option.py)\n'
                                             + '\n'.join(lines) + '\n')
        print(f'{folder}: {len(lines)} files')
    write(args.output / 'menu', files)
    for style, blob in fonts.items():
        write(args.output / f'icons-{style}', {icons.ARCHIVE: blob})
    for line in report:
        print('  size table:', line)


if __name__ == '__main__':
    main()
