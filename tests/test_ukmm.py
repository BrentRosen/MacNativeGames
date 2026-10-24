"""games/botw/scripts/ukmm.py with a synthetic app, data folder and UKMM Switch deploy: the dump, the links, the
manifests and the Bootup.pack merge with the button-icon sets."""
from pathlib import Path
import hashlib
import importlib.util
import io
import contextlib
import struct
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ukmm', ROOT / 'games/botw/scripts/ukmm.py')
ukmm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ukmm)


def sarc(members):
    """A little-endian SARC of name -> bytes (names sorted, data 8-aligned)."""
    names = sorted(members)
    table = b''
    offsets = []
    for name in names:
        offsets.append(len(table) // 4)
        raw = name.encode() + b'\0'
        table += raw + b'\0' * (-len(raw) % 4)
    fat = 0x14
    sfnt = fat + 12 + 16 * len(names)
    start = sfnt + 8 + len(table)
    start += -start % 8
    data, nodes = b'', b''
    for name, at in zip(names, offsets):
        data += b'\0' * (-len(data) % 8)
        nodes += struct.pack('<4I', 0, 0x01000000 | at, len(data), len(data) + len(members[name]))
        data += members[name]
    head = (b'SARC' + struct.pack('<HHIIHH', 0x14, 0xfeff, start + len(data), start, 0x100, 0) +
            b'SFAT' + struct.pack('<HHI', 12, len(names), 0x65) + nodes + b'SFNT' + struct.pack('<HH', 8, 0) + table)
    return head + b'\0' * (start - len(head)) + data


def image(folder, files):
    """romfs.bin and runtime-index.bin (TOTKRFS1) of name -> bytes."""
    folder.mkdir(parents=True, exist_ok=True)
    blob, entries, strings = b'', b'', b''
    for name, data in sorted(files.items()):
        entries += struct.pack('<QQII', len(blob), len(data), len(strings), len(name) + 1)
        strings += name.encode() + b'\0'
        blob += data
    (folder / 'romfs.bin').write_bytes(blob)
    (folder / 'runtime-index.bin').write_bytes(struct.pack('<8sQQ', b'TOTKRFS1', len(files), 24 + 24 * len(files)) +
                                               entries + strings)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def rstb(sizes):
    return ukmm.rstb_write({zlib.crc32(name.encode()): size for name, size in sizes.items()}, {}, [])


VANILLA_BOOTUP = sarc({'Layout/Common.sblarc': b'common-original', 'GameData/gamedata.ssarc': b'flags-original'})
ICON_BOOTUP = sarc({'Layout/Common.sblarc': b'common-icons!!', 'GameData/gamedata.ssarc': b'flags-original'})


class Ukmm(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.app = t / 'Breath of the Wild.app'
        ext = self.app / 'Contents/Resources/totk/extracted/botw190'
        self.vanilla_rstb = rstb({'Actor/A.bin': 100, 'Other/X.bin': 500, 'Aoc/0010/Sound/S.bfstm': 70})
        self.base_files = {ukmm.BOOTUP: VANILLA_BOOTUP, 'Actor/A.bin': b'actor-a', ukmm.UKMM_TEST_FILE: b'cluster',
                           'Font/Font_US.sbfarc': b'font-original', ukmm.RSTB: self.vanilla_rstb}
        image(ext / 'romfs', self.base_files)
        image(ext / 'aoc/1', {'Pack/AocMainField.pack': b'aoc-pack', 'Sound/S.bfstm': b'stream'})
        self.data = t / 'data'
        self.style = self.data / 'button-icons/xbox'
        (self.style / 'Pack').mkdir(parents=True)
        (self.style / 'Font').mkdir()
        (self.style / ukmm.BOOTUP).write_bytes(ICON_BOOTUP)
        (self.style / 'Font/Font_US.sbfarc').write_bytes(b'font-icons')
        self.icon_manifest = ('# path\tsize\tsha256\toriginal_sha256\n'
                              f'Font/Font_US.sbfarc\t10\t{sha(b"font-icons")}\t{sha(b"font-original")}\n'
                              f'{ukmm.BOOTUP}\t{len(ICON_BOOTUP)}\t{sha(ICON_BOOTUP)}\t{sha(VANILLA_BOOTUP)}\n')
        (self.style / 'manifest.tsv').write_text(self.icon_manifest)
        self.deploy = t / 'deploy'
        self.base = self.deploy / ukmm.CONTENT / 'romfs'
        self.aoc = self.deploy / ukmm.AOC / 'romfs'
        (self.base / 'Pack').mkdir(parents=True)
        (self.base / 'Actor').mkdir()
        (self.aoc / 'Sound').mkdir(parents=True)
        (self.aoc / 'Sound/S.bfstm').write_bytes(b'stream-mod')

    def tearDown(self):
        self.tmp.cleanup()

    def sync(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            ukmm.sync(self.deploy, self.app, False, self.data)
        return out.getvalue()

    def test_dump_unpacks_both_images(self):
        out = Path(self.tmp.name) / 'dump'
        with contextlib.redirect_stdout(io.StringIO()):
            ukmm.dump(self.app, out)
        self.assertEqual((out / 'romfs/Actor/A.bin').read_bytes(), b'actor-a')
        self.assertEqual((out / 'dlc/Sound/S.bfstm').read_bytes(), b'stream')
        (out / 'romfs/Actor/A.bin').write_bytes(b'short')   # a wrong size is written again, the rest kept
        with contextlib.redirect_stdout(io.StringIO()) as log:
            ukmm.dump(self.app, out)
        self.assertIn('1 files written', log.getvalue())
        self.assertEqual((out / 'romfs/Actor/A.bin').read_bytes(), b'actor-a')

    def test_sync_links_and_writes_manifests(self):
        (self.base / 'Actor/A.bin').write_bytes(b'actor-mod')
        self.sync()
        self.assertEqual((self.data / 'mods/botw190').resolve(), self.base.resolve())
        self.assertEqual((self.data / 'mods/botw190-aoc/1').resolve(), self.aoc.resolve())
        self.assertEqual(ukmm.manifest_paths(self.base / 'manifest.tsv'), {'Actor/A.bin'})
        self.assertEqual(ukmm.manifest_paths(self.aoc / 'manifest.tsv'), {'Sound/S.bfstm'})
        self.assertEqual((self.style / 'manifest.tsv').read_text(), self.icon_manifest)   # no Bootup.pack: unchanged

    def test_existing_folder_is_moved_aside(self):
        own = self.data / 'mods/botw190'
        own.mkdir(parents=True)
        (own / 'kept.bin').write_bytes(b'x')
        (self.base / 'Actor/A.bin').write_bytes(b'actor-mod')
        self.sync()
        backups = list((self.data / 'mods').glob('botw190.backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'kept.bin').read_bytes(), b'x')

    def test_bootup_merged_into_icon_sets_and_restored(self):
        mod = sarc({'Layout/Common.sblarc': b'common-original', 'GameData/gamedata.ssarc': b'flags-from-mod'})
        (self.base / ukmm.BOOTUP).write_bytes(mod)
        (self.base / 'Actor/A.bin').write_bytes(b'actor-mod')
        self.sync()
        self.assertNotIn(ukmm.BOOTUP, ukmm.manifest_paths(self.base / 'manifest.tsv'))
        merged = (self.style / ukmm.BOOTUP).read_bytes()
        members = ukmm.sarc_members(merged)
        self.assertEqual(merged[slice(*members['Layout/Common.sblarc'])], b'common-icons!!')
        self.assertEqual(merged[slice(*members['GameData/gamedata.ssarc'])], b'flags-from-mod')
        line = [l for l in (self.style / 'manifest.tsv').read_text().splitlines() if l.startswith(ukmm.BOOTUP)][0]
        self.assertEqual(line.split('\t')[1:], [str(len(merged)), sha(merged), sha(VANILLA_BOOTUP)])
        self.assertEqual((self.style / ukmm.KEPT_PACK).read_bytes(), ICON_BOOTUP)
        self.sync()   # a second sync merges from the kept copy, not from its own output
        self.assertEqual((self.style / ukmm.BOOTUP).read_bytes(), merged)
        (self.base / ukmm.BOOTUP).unlink()   # the mod is gone: the set is back as it was
        self.sync()
        self.assertEqual((self.style / ukmm.BOOTUP).read_bytes(), ICON_BOOTUP)
        self.assertEqual((self.style / 'manifest.tsv').read_text(), self.icon_manifest)

    def test_member_both_change_keeps_the_mod(self):
        mod = sarc({'Layout/Common.sblarc': b'common-mod', 'GameData/gamedata.ssarc': b'flags-original'})
        (self.base / ukmm.BOOTUP).write_bytes(mod)
        log = self.sync()
        self.assertIn('the mod changes it too', log)
        self.assertEqual((self.style / ukmm.BOOTUP).read_bytes(), mod)

    def test_changes_inside_one_archive_are_combined(self):
        y = lambda data: ukmm.literal_yaz0(data, bytes(16))
        common = lambda anim, tex: y(sarc({'anim/A.bflan': anim, 'timg/T.bin': tex}))
        vanilla = sarc({'Layout/Common.sblarc': common(b'anim-v', b'tex-v'), 'GameData/gamedata.ssarc': b'g'})
        icons = sarc({'Layout/Common.sblarc': common(b'anim-i', b'tex-v'), 'GameData/gamedata.ssarc': b'g'})
        mod = sarc({'Layout/Common.sblarc': common(b'anim-v', b'tex-m'), 'GameData/gamedata.ssarc': b'g-mod'})
        merged, notes = ukmm.merge_bootup(vanilla, icons, mod)
        self.assertEqual(notes, [])
        outer = ukmm.sarc_members(merged)
        self.assertEqual(merged[slice(*outer['GameData/gamedata.ssarc'])], b'g-mod')
        inner = ukmm.unpacked(merged[slice(*outer['Layout/Common.sblarc'])])
        members = ukmm.sarc_members(inner)
        self.assertEqual(inner[slice(*members['anim/A.bflan'])], b'anim-i')
        self.assertEqual(inner[slice(*members['timg/T.bin'])], b'tex-m')
        clash = sarc({'Layout/Common.sblarc': common(b'anim-m', b'tex-v'), 'GameData/gamedata.ssarc': b'g'})
        merged, notes = ukmm.merge_bootup(vanilla, icons, clash)
        self.assertEqual(merged, clash)
        self.assertTrue(any('anim/A.bflan' in note for note in notes))

    def test_mod_font_wins_over_icon_font(self):
        (self.base / 'Font').mkdir()
        (self.base / 'Font/Font_US.sbfarc').write_bytes(b'font-mod')
        self.sync()
        self.assertNotIn('Font/Font_US.sbfarc', ukmm.manifest_paths(self.style / 'manifest.tsv'))
        self.assertIn('Font/Font_US.sbfarc', ukmm.manifest_paths(self.base / 'manifest.tsv'))

    def test_regenerated_icon_set_becomes_the_kept_copy(self):
        mod = sarc({'Layout/Common.sblarc': b'common-original', 'GameData/gamedata.ssarc': b'flags-from-mod'})
        (self.base / ukmm.BOOTUP).write_bytes(mod)
        self.sync()
        newer = sarc({'Layout/Common.sblarc': b'common-icons-v2', 'GameData/gamedata.ssarc': b'flags-original'})
        (self.style / ukmm.BOOTUP).write_bytes(newer)   # an app update writes the set again
        self.sync()
        self.assertEqual((self.style / ukmm.KEPT_PACK).read_bytes(), newer)
        merged = (self.style / ukmm.BOOTUP).read_bytes()
        self.assertEqual(merged[slice(*ukmm.sarc_members(merged)['Layout/Common.sblarc'])], b'common-icons-v2')

    def test_size_table_rebuilt_from_the_apps_own(self):
        (self.base / 'Actor/A.bin').write_bytes(b'actor-mod')
        (self.base / 'System/Resource').mkdir(parents=True)
        # UKMM's table: its stock values (Other/X.bin smaller than this version's, an entry this version lacks) plus
        # the sizes of what it deployed
        (self.base / ukmm.RSTB).write_bytes(rstb({'Actor/A.bin': 200, 'Other/X.bin': 50, 'Stock/Only.bin': 9,
                                                  'Aoc/0010/Sound/S.bfstm': 90}))
        self.sync()
        table, _, _ = ukmm.rstb_read((self.base / ukmm.RSTB).read_bytes())
        crc = lambda name: zlib.crc32(name.encode())
        self.assertEqual(table, {crc('Actor/A.bin'): 200, crc('Other/X.bin'): 500, crc('Aoc/0010/Sound/S.bfstm'): 90})

    def test_dlc_archive_members_are_sized_under_aoc(self):
        (self.aoc / 'Pack').mkdir()
        (self.aoc / 'Pack/AocMainField.pack').write_bytes(sarc({'Map/MainField/A-1/A-1_Static.smubin': b'unit'}))
        (self.base / 'System/Resource').mkdir(parents=True)
        (self.base / ukmm.RSTB).write_bytes(rstb({'Aoc/0010/Map/MainField/A-1/A-1_Static.mubin': 900,
                                                  'Map/MainField/A-1/A-1_Static.mubin': 5,
                                                  'Aoc/0010/Pack/AocMainField.pack': 64,
                                                  'Aoc/0010/Sound/S.bfstm': 90}))
        self.sync()
        table, _, _ = ukmm.rstb_read((self.base / ukmm.RSTB).read_bytes())
        self.assertEqual(table[zlib.crc32(b'Aoc/0010/Map/MainField/A-1/A-1_Static.mubin')], 900)
        self.assertNotIn(zlib.crc32(b'Map/MainField/A-1/A-1_Static.mubin'), table)   # not a base resource of this deploy

    def test_size_table_entry_ukmm_removed_stays_removed(self):
        (self.base / 'Actor/A.bin').write_bytes(b'actor-mod')
        (self.base / 'System/Resource').mkdir(parents=True)
        (self.base / ukmm.RSTB).write_bytes(rstb({'Other/X.bin': 50}))   # UKMM could not size Actor/A.bin
        self.sync()
        table, _, _ = ukmm.rstb_read((self.base / ukmm.RSTB).read_bytes())
        self.assertNotIn(zlib.crc32(b'Actor/A.bin'), table)
        self.assertEqual(table[zlib.crc32(b'Other/X.bin')], 500)
        self.sync()   # again without a deploy: still from UKMM's table, not from the last output
        table, _, _ = ukmm.rstb_read((self.base / ukmm.RSTB).read_bytes())
        self.assertNotIn(zlib.crc32(b'Actor/A.bin'), table)
        (self.base / ukmm.RSTB).write_bytes(rstb({'Actor/A.bin': 300}))   # a new deploy
        self.sync()
        table, _, _ = ukmm.rstb_read((self.base / ukmm.RSTB).read_bytes())
        self.assertEqual(table[zlib.crc32(b'Actor/A.bin')], 300)
        self.assertIn(ukmm.RSTB, ukmm.manifest_paths(self.base / 'manifest.tsv'))

    def test_size_table_without_raises_is_the_original(self):
        (self.base / 'Actor/A.bin').write_bytes(b'actor-mod')
        (self.base / 'System/Resource').mkdir(parents=True)
        (self.base / ukmm.RSTB).write_bytes(rstb({'Actor/A.bin': 80, 'Other/X.bin': 50, 'Aoc/0010/Sound/S.bfstm': 60}))
        self.sync()
        self.assertEqual((self.base / ukmm.RSTB).read_bytes(), self.vanilla_rstb)
        self.assertNotIn(ukmm.RSTB, ukmm.manifest_paths(self.base / 'manifest.tsv'))

    def test_second_sync_without_changes_is_skipped(self):
        (self.base / 'Actor/A.bin').write_bytes(b'actor-mod')
        self.assertNotIn('nothing changed', self.sync())
        self.assertIn('nothing changed', self.sync())
        (self.base / 'Actor/A.bin').write_bytes(b'actor-mod2')
        self.assertNotIn('nothing changed', self.sync())

    def test_deploy_finished_reads_pending_yml(self):
        pending = Path(self.tmp.name) / 'pending.yml'
        empty = ''.join(f'{key}:\n  folders: {{}}\n  files: []\n'
                        for key in ('content_copies', 'aoc_copies', 'content_deletes', 'aoc_deletes'))
        pending.write_text(empty)
        self.assertTrue(ukmm.deploy_finished(pending))
        pending.write_text(empty.replace('files: []', 'files:\n  - Pack/Bootup.pack', 1))
        self.assertFalse(ukmm.deploy_finished(pending))
        pending.unlink()
        self.assertFalse(ukmm.deploy_finished(pending))

    def test_symlink_deploy_is_refused(self):
        target = Path(self.tmp.name) / 'merged'
        target.mkdir()
        alt = Path(self.tmp.name) / 'deploy2'
        (alt / ukmm.CONTENT).mkdir(parents=True)
        (alt / ukmm.CONTENT / 'romfs').symlink_to(target)
        with self.assertRaises(ukmm.UkmmError):
            ukmm.deploy_folders(alt)


if __name__ == '__main__':
    unittest.main()
