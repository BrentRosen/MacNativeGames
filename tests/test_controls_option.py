"""make_controls_option.py and nx_formats.py: the Options menu's Button icons row, on small synthetic documents (no game
data). The hashes checked below are values from the game's own GameDataList."""
import struct
import sys
import unittest
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'games/totk/scripts'))
import nx_formats as nx  # noqa: E402
import make_controls_option as co  # noqa: E402


def msbt(entries, slots=29):
    """An MSBT (LBL1 + TXT2, UTF-16LE) holding label -> text, built by hand in the game's layout."""
    names = list(entries)
    rows = [[n for n in names if nx._msbt_hash(n, slots) == s] for s in range(slots)]
    table, labels, at = struct.pack('<I', slots), b'', 4 + 8 * slots
    for row in rows:
        table += struct.pack('<II', len(row), at + len(labels))
        for n in row:
            labels += bytes([len(n)]) + n.encode() + struct.pack('<I', names.index(n))
    texts = [entries[n].encode('utf-16-le') + b'\0\0' for n in names]
    txt, body, at = struct.pack('<I', len(texts)), b'', 4 + 4 * len(texts)
    for t in texts:
        txt += struct.pack('<I', at + len(body)); body += t

    def section(magic, data):
        return magic + struct.pack('<I', len(data)) + b'\0' * 8 + data + b'\xab' * (-len(data) % 16)
    out = bytearray(b'MsgStdBn\xff\xfe\0\0\x01\x03\x02\0' + b'\0' * 16)
    out += section(b'LBL1', table + labels) + section(b'TXT2', txt + body)
    struct.pack_into('<I', out, 0x12, len(out))
    return bytes(out)


def game_data(option_entries=3):
    """A GameDataList with an OptionData struct, a DisplayMode Enum and MetaData that match the option.sav size model."""
    h = co.murmur3
    bools = [{'DefaultValue': False, 'Hash': nx.UInt(h(f'OptionData.B{i}')), 'ResetTypeValue': nx.Int(4),
              'SaveFileIndex': nx.Int(1)} for i in range(option_entries)]
    display = {'DefaultValue': nx.UInt(h('Normal')), 'Hash': nx.UInt(h('OptionData.DisplayMode')),
               'RawValues': ['Normal', 'Pro'], 'ResetTypeValue': nx.Int(4), 'SaveFileIndex': nx.Int(1),
               'Values': [nx.UInt64(h('Normal')), nx.UInt64(h('Pro'))]}
    data = {'Data': {'Bool': bools, 'Enum': [display], 'Bool64bitKey': [{'Hash': nx.UInt64(5), 'SaveFileIndex': nx.Int(0)}],
                     'Struct': [{'DefaultValue': [{'Hash': nx.UInt(h('DisplayMode')), 'Value': nx.UInt(h('OptionData.DisplayMode'))}],
                                 'Hash': nx.UInt(h('OptionData')), 'ResetTypeValue': nx.Int(0), 'SaveFileIndex': nx.Int(-1)}]},
            'MetaData': {'SaveDirectory': ['slot_%02d/progress.sav', 'option.sav'], 'SaveDataSize': [nx.Int(0), nx.Int(0)],
                         'SaveDataOffsetPos': [nx.Int(0), nx.Int(0)], 'AllDataSaveOffset': nx.Int(0), 'AllDataSaveSize': nx.Int(100)}}
    option, every = co.option_save_layout(data)
    data['MetaData']['SaveDataOffsetPos'][1] = nx.Int(option); data['MetaData']['SaveDataSize'][1] = nx.Int(option + 248)
    data['MetaData']['AllDataSaveOffset'] = nx.Int(every)
    return data


class Hashes(unittest.TestCase):
    def test_matches_the_games_lists(self):
        self.assertEqual(co.murmur3('OptionData'), 0x834d9d9e)
        self.assertEqual(co.murmur3('OptionData.DisplayMode'), 0x4e767f10)
        self.assertEqual(co.murmur3('OptionData.IsCameraUpDownReverse'), 0x520ddc44)
        self.assertEqual([co.murmur3(c) for c in co.CHOICES], [0x390b012d, 0xd4b93848, 0xf106eb35])
        self.assertEqual(co.murmur3(f'OptionData.{co.OPTION_TYPE}'), 0xce2cee8e)   # what runtime/romfs.c looks for


class Byml(unittest.TestCase):
    DOC = {'b': True, 'i': nx.Int(-3), 'u': nx.UInt(7), 'f': nx.Float(0.5), 'l': nx.Int64(-1), 'q': nx.UInt64(1 << 40),
           'd': nx.Double(2.25), 's': 'text', 'n': None, 'list': [nx.UInt64(0), nx.Int64(0), 'text', [nx.Int(1)]]}

    def test_round_trip_both_byte_orders(self):
        for order in '<>':
            data = nx.byml_write(self.DOC, order)
            value, got_order, version = nx.byml_read(data)
            self.assertEqual((got_order, version), (order, 7))
            self.assertTrue(nx.byml_equal(value, self.DOC))
            self.assertEqual(nx.byml_write(value, order), data)

    def test_types_are_kept(self):
        self.assertFalse(nx.byml_equal({'a': nx.Int(1)}, {'a': nx.UInt(1)}))
        value = nx.byml_read(nx.byml_write(self.DOC))[0]
        self.assertIsInstance(value['u'], nx.UInt); self.assertIsInstance(value['q'], nx.UInt64)

    def test_sharing_follows_the_original(self):
        shared = {'k': 'v'}
        data = nx.byml_write({'a': [shared, shared], 'b': [{'k': 'v'}]})
        value = nx.byml_read(data)[0]
        self.assertIs(value['a'][0], value['a'][1])          # written once, read back as one object
        self.assertIsNot(value['a'][0], value['b'][0])       # equal but separate in the source: separate in the file
        self.assertEqual(nx.byml_write(value), data)

    def test_long_values_shared_per_type_or_not_at_all(self):
        doc = {'a': [nx.UInt64(9), nx.UInt64(9), nx.Int64(9)]}
        self.assertEqual(len(nx.byml_write(doc, share_longs=False)) - len(nx.byml_write(doc)), 8)


class Messages(unittest.TestCase):
    def test_unchanged_rewrite_is_identical_and_labels_are_added(self):
        data = msbt({'1005': 'Swap jump controls', '0005': 'Assign jump.', 'T_Title_00': 'Options'})
        m = nx.Msbt(data)
        self.assertEqual(m.bytes(), data)
        co.add_option_text(m, 'en')
        again = nx.Msbt(m.bytes())
        self.assertEqual(again.text('1006').decode('utf-16-le'), 'Button icons')
        self.assertEqual([again.text(f'1006_{i:02d}').decode('utf-16-le') for i in range(3)], list(co.CHOICE_NAMES))
        self.assertIn('1006', again.slot_order[nx._msbt_hash('1006', again.slots)])
        with self.assertRaises(AssertionError):
            co.add_option_text(again, 'en')

    def test_every_language_archive_has_text(self):
        regions = 'CNzh EUde EUen EUes EUfr EUit EUnl EUru JPja KRko TWzh USen USes USfr USpt'.split()
        for region in regions:
            self.assertIn(co.LANGUAGE.get(region, region[2:]), co.TEXT, region)


class OptionTable(unittest.TestCase):
    def test_row_goes_below_swap_jump(self):
        table = {'OptionSetArray': [{'OptionType': 'IsUseGyro'}, {'ButtonType': 'Toggle', 'OptionType': 'IsChangeJumpButton'},
                                    {'ButtonType': 'Separator', 'OptionType': 'None'}]}
        rows = co.add_option_row(table)['OptionSetArray']
        self.assertEqual(rows[2], {'ButtonType': 'Selection', 'ChoiceType': list(co.CHOICES), 'OptionType': co.OPTION_TYPE})
        with self.assertRaises(AssertionError):
            co.add_option_row(table)


class GameData(unittest.TestCase):
    def test_member_enum_and_save_sizes(self):
        data = game_data()
        before = {k: v[1] if isinstance(v, list) else v for k, v in data['MetaData'].items()}
        co.add_option_data(data)
        meta = data['MetaData']
        self.assertEqual(meta['SaveDataOffsetPos'][1], before['SaveDataOffsetPos'] + 8)
        self.assertEqual(meta['SaveDataSize'][1], before['SaveDataSize'] + 8)
        self.assertEqual(meta['AllDataSaveOffset'], before['AllDataSaveOffset'] + 8)
        self.assertEqual(meta['AllDataSaveSize'], before['AllDataSaveSize'] + 8)
        enum = data['Data']['Enum'][-1]
        self.assertEqual(enum['Hash'], 0xce2cee8e); self.assertEqual(enum['RawValues'], list(co.CHOICES))
        self.assertEqual(data['Data']['Struct'][0]['DefaultValue'][-1], {'Hash': co.murmur3(co.OPTION_TYPE), 'Value': 0xce2cee8e})
        # the edited list survives a BYML round trip with its types
        self.assertTrue(nx.byml_equal(nx.byml_read(nx.byml_write(data, '>'))[0], data))

    def test_refuses_a_list_the_size_model_does_not_fit(self):
        data = game_data(); data['MetaData']['SaveDataOffsetPos'][1] += 8
        with self.assertRaises(AssertionError):
            co.add_option_data(data)


class SizeTable(unittest.TestCase):
    def test_entries_keep_their_allowance(self):
        crc = sorted([(zlib.crc32(b'A/a.bin'), 1000), (zlib.crc32(b'B/b.bin'), 500)])
        named = b'C/c.bin'.ljust(160, b'\0') + struct.pack('<I', 300)
        data = b'RESTBL' + struct.pack('<IIII', 1, 160, len(crc), 1) + b''.join(struct.pack('<II', *e) for e in crc) + named
        out, report = co.rstb_update(data, {'A/a.bin': (900, 950), 'C/c.bin': (200, 150), 'D/d.bin': (1, 2),
                                            'B/b.bin': (400, 400, 64)})
        values = dict(struct.unpack_from('<II', out, 22 + 8 * i) for i in range(2))
        self.assertEqual(values[zlib.crc32(b'A/a.bin')], 1050)   # 950 + (1000 - 900)
        self.assertEqual(values[zlib.crc32(b'B/b.bin')], 564)    # extra allowance for the parsed objects
        self.assertEqual(struct.unpack_from('<I', out, len(out) - 4)[0], 300)   # never lowered
        self.assertIn('D/d.bin: not listed', report)


if __name__ == '__main__':
    unittest.main()
