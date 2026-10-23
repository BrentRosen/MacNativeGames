#!/usr/bin/env python3
"""Readers and writers for the game data formats that build steps edit: SARC archives, BYML documents and MSBT message
files. Every writer is checked by its users against the original (an unchanged document must come out with the same
content), and nothing here knows about any one file.

SARC: members are replaced in place, keeping their order, alignment and every other member byte-identical.
BYML (versions 2 to 7, either byte order): read into Python values that keep their BYML type (Int, UInt, Int64, UInt64,
Float, Double) and the original's shared containers, written back sharing exactly those.
MSBT (UTF-16, LBL1 and TXT2): labels added or texts replaced; the label hash table keeps its slot count.
"""
import struct

# ---- SARC ----


def sarc_members(data):
    """name -> (absolute start, end) of every SARC member."""
    assert data[:4] == b'SARC' and data[6:8] == b'\xff\xfe', 'not a little-endian SARC'
    header, size, start = struct.unpack_from('<HxxII', data, 4)
    assert size == len(data) and data[header:header + 4] == b'SFAT'
    count = struct.unpack_from('<H', data, header + 6)[0]; names = header + 12 + count * 16
    assert data[names:names + 4] == b'SFNT'; names += 8
    out = {}
    for i in range(count):
        _, attribute, lo, hi = struct.unpack_from('<4I', data, header + 12 + i * 16)
        offset = names + (attribute & 0xffffff) * 4
        out[data[offset:data.index(0, offset, start)].decode()] = (start + lo, start + hi)
    return out


def sarc_replace(sarc, replacements):
    """The SARC with the members named in `replacements` (name -> bytes) replaced, every other member byte-identical, in
    the original order and alignment (each member keeps the largest power-of-two alignment its old offset had)."""
    start = struct.unpack_from('<I', sarc, 12)[0]
    fat = struct.unpack_from('<H', sarc, 4)[0]; count = struct.unpack_from('<H', sarc, fat + 6)[0]
    nodes = [list(struct.unpack_from('<4I', sarc, fat + 12 + i * 16)) for i in range(count)]
    members = sarc_members(sarc); by_range = {(lo, hi): k for k, (lo, hi) in members.items()}
    missing = set(replacements) - set(members)
    assert not missing, f'not in the archive: {sorted(missing)}'
    names = [by_range[(start + n[2], start + n[3])] for n in nodes]
    blobs = [replacements.get(name, sarc[start + n[2]:start + n[3]]) for name, n in zip(names, nodes)]

    def alignment(offset):
        a = 1
        while offset % (a * 2) == 0 and a < 0x2000:
            a *= 2
        return a
    data, placed = bytearray(), {}
    for i in sorted(range(count), key=lambda i: nodes[i][2]):
        a = alignment(nodes[i][2]) if nodes[i][2] else 1
        while len(data) % a:
            data += b'\0'
        placed[i] = (len(data), len(data) + len(blobs[i])); data += blobs[i]
    head = bytearray(sarc[:start])
    for i in range(count):
        struct.pack_into('<II', head, fat + 12 + i * 16 + 8, *placed[i])
    out = bytearray(bytes(head) + bytes(data)); struct.pack_into('<I', out, 8, len(out)); out = bytes(out)
    check = sarc_members(out)
    for k, (lo, hi) in members.items():
        assert out[check[k][0]:check[k][1]] == replacements.get(k, sarc[lo:hi]), k
    return out


# ---- BYML ----

class Int(int):
    """BYML 0xD1 (signed 32-bit); plain Python ints are written as this too."""


class UInt(int):
    """BYML 0xD3 (unsigned 32-bit)."""


class Int64(int):
    """BYML 0xD4."""


class UInt64(int):
    """BYML 0xD5."""


class Float(float):
    """BYML 0xD2 (32-bit); plain Python floats are written as this too."""


class Double(float):
    """BYML 0xD6."""


STRING, ARRAY, DICT, KEYS = 0xA0, 0xC0, 0xC1, 0xC2
BOOL, INT, FLOAT, UINT, INT64, UINT64, DOUBLE, NULL = 0xD0, 0xD1, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xFF
LONG = (INT64, UINT64, DOUBLE)


def byml_read(data):
    """(root value, byte order '<' or '>', version) of a BYML document."""
    order = {b'YB': '<', b'BY': '>'}[data[:2]]
    version, keys_at, strings_at, root_at = struct.unpack_from(order + 'HIII', data, 2)
    assert 2 <= version <= 7, f'BYML version {version}'

    def u24(o):
        return int.from_bytes(data[o:o + 3], 'little' if order == '<' else 'big')

    def table(o):
        if not o:
            return []
        assert data[o] == KEYS
        n = u24(o + 1); offsets = struct.unpack_from(order + f'{n + 1}I', data, o + 4)
        return [data[o + offsets[i]:data.index(0, o + offsets[i])].decode() for i in range(n)]
    keys, strings = table(keys_at), table(strings_at)

    def value(kind, raw):
        if kind == STRING:
            return strings[raw]
        if kind == BOOL:
            return bool(raw)
        if kind == INT:
            return Int(struct.unpack(order + 'i', struct.pack(order + 'I', raw))[0])
        if kind == FLOAT:
            return Float(struct.unpack(order + 'f', struct.pack(order + 'I', raw))[0])
        if kind == UINT:
            return UInt(raw)
        if kind == INT64:
            return Int64(struct.unpack_from(order + 'q', data, raw)[0])
        if kind == UINT64:
            return UInt64(struct.unpack_from(order + 'Q', data, raw)[0])
        if kind == DOUBLE:
            return Double(struct.unpack_from(order + 'd', data, raw)[0])
        if kind == NULL:
            return None
        if kind in (ARRAY, DICT):
            return node(raw)
        raise ValueError(f'BYML node type {kind:#x} is not supported')

    shared = {}

    def node(o):   # a container referenced twice is one object, so a rewrite shares exactly what the original shares
        if o not in shared:
            shared[o] = container(o)
        return shared[o]

    def container(o):
        kind, n = data[o], u24(o + 1)
        if kind == ARRAY:
            kinds = data[o + 4:o + 4 + n]; base = (o + 4 + n + 3) & ~3
            return [value(kinds[i], struct.unpack_from(order + 'I', data, base + i * 4)[0]) for i in range(n)]
        if kind == DICT:
            out = {}
            for i in range(n):
                e = o + 4 + i * 8
                out[keys[u24(e)]] = value(data[e + 3], struct.unpack_from(order + 'I', data, e + 4)[0])
            return out
        raise ValueError(f'BYML container type {kind:#x} is not supported')
    return (node(root_at) if root_at else None), order, version


def _kind(v):
    if isinstance(v, bool):
        return BOOL
    if isinstance(v, dict):
        return DICT
    if isinstance(v, list):
        return ARRAY
    if isinstance(v, str):
        return STRING
    if v is None:
        return NULL
    for cls, kind in ((UInt, UINT), (Int64, INT64), (UInt64, UINT64), (Double, DOUBLE), (Int, INT), (Float, FLOAT)):
        if isinstance(v, cls):
            return kind
    if isinstance(v, int):
        return INT
    if isinstance(v, float):
        return FLOAT
    raise TypeError(f'no BYML type for {type(v).__name__}')


def byml_write(root, order='<', version=7, share_longs=True):
    """A BYML document of `root` (a dict or list). Keys and strings are sorted tables; a container object reached twice
    is written once, and so is a long value of a type (without share_longs, every long value has its own place, as in
    1.0.0's GameDataList)."""
    keys, strings = set(), set()

    def collect(v):
        if isinstance(v, dict):
            keys.update(v)
            for x in v.values():
                collect(x)
        elif isinstance(v, list):
            for x in v:
                collect(x)
        elif isinstance(v, str):
            strings.add(v)
    collect(root)
    key_list = sorted(keys, key=lambda s: s.encode()); string_list = sorted(strings, key=lambda s: s.encode())
    key_index = {k: i for i, k in enumerate(key_list)}; string_index = {s: i for i, s in enumerate(string_list)}

    def u24(n):
        assert n < 1 << 24
        return n.to_bytes(3, 'little' if order == '<' else 'big')

    def string_table(items):
        if not items:
            return b''
        blobs = [s.encode() + b'\0' for s in items]
        offsets, at = [], 4 + 4 * (len(items) + 1)
        for b in blobs:
            offsets.append(at); at += len(b)
        offsets.append(at)
        out = bytes([KEYS]) + u24(len(items)) + struct.pack(order + f'{len(offsets)}I', *offsets) + b''.join(blobs)
        return out + b'\0' * (-len(out) % 4)

    # Containers are shared only when they are the same Python object (byml_read gives a container the original
    # references twice as one object): the game's parsers do not all accept shared nodes where its files have none.
    # Long values come first (equal ones of a type once), then the containers in depth-first pre-order, as in the game's files.
    containers, container_id, longs, long_id = [], {}, [], {}

    def ident(v):
        kind = _kind(v)
        if kind in LONG:
            blob = struct.pack(order + {INT64: 'q', UINT64: 'Q', DOUBLE: 'd'}[kind], v)
            key = (kind, blob) if share_longs else len(longs)   # shared per type: an Int64 0 and a UInt64 0 are two
            if key not in long_id:
                long_id[key] = len(longs); longs.append(blob)
            return (kind, 'long', long_id[key])
        if kind in (ARRAY, DICT):
            if id(v) in container_id:
                return (kind, 'node', container_id[id(v)])
            slot = len(containers); containers.append(None); container_id[id(v)] = slot
            if kind == DICT:
                body = tuple((key_index[k], ident(v[k])) for k in sorted(v, key=lambda s: key_index[s]))
            else:
                body = tuple(ident(x) for x in v)
            containers[slot] = (kind, body)
            return (kind, 'node', slot)
        if kind == STRING:
            return (kind, 'raw', string_index[v])
        if kind == BOOL:
            return (kind, 'raw', int(v))
        if kind == INT:
            return (kind, 'raw', struct.unpack(order + 'I', struct.pack(order + 'i', v))[0])
        if kind == FLOAT:
            return (kind, 'raw', struct.unpack(order + 'I', struct.pack(order + 'f', v))[0])
        if kind == UINT:
            return (kind, 'raw', int(v))
        return (kind, 'raw', 0)
    root_ident = ident(root)

    key_blob, string_blob = string_table(key_list), string_table(string_list)
    at = 16
    keys_at = at if key_blob else 0; at += len(key_blob)
    strings_at = at if string_blob else 0; at += len(string_blob)
    long_at = []
    for blob in longs:
        long_at.append(at); at += 8
    offsets = []
    for kind, body in containers:
        offsets.append(at)
        at += 4 + 8 * len(body) if kind == DICT else 4 + ((len(body) + 3) & ~3) + 4 * len(body)

    def raw(i):
        kind, how, n = i
        return offsets[n] if how == 'node' else long_at[n] if how == 'long' else n
    out = bytearray(b'YB' if order == '<' else b'BY')
    out += struct.pack(order + 'HIII', version, keys_at, strings_at, offsets[root_ident[2]] if root_ident[1] == 'node' else 0)
    out += key_blob + string_blob
    for blob in longs:
        out += blob
    for kind, body in containers:
        out += bytes([kind]) + u24(len(body))
        if kind == DICT:
            for k, i in body:
                out += u24(k) + bytes([i[0]]) + struct.pack(order + 'I', raw(i))
        else:
            out += bytes(i[0] for i in body) + b'\0' * (-len(body) % 4)
            out += b''.join(struct.pack(order + 'I', raw(i)) for i in body)
    assert len(out) == at
    return bytes(out)


def byml_equal(a, b):
    """Deep equality that also compares BYML types (an Int is not a UInt)."""
    if _kind(a) != _kind(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(byml_equal(a[k], b[k]) for k in a)
    if isinstance(a, list):
        return len(a) == len(b) and all(byml_equal(x, y) for x, y in zip(a, b))
    if isinstance(a, float):
        return struct.pack('<d', a) == struct.pack('<d', b)
    return a == b


# ---- MSBT ----

def _msbt_hash(label, slots):
    h = 0
    for c in label.encode():
        h = (h * 0x492 + c) & 0xffffffff
    return h % slots


class Msbt:
    """An MSBT with LBL1 and TXT2 sections (UTF-16LE): labels in their hash slots, texts as raw UTF-16 bytes."""

    def __init__(self, data):
        assert data[:8] == b'MsgStdBn' and data[8:10] == b'\xff\xfe', 'not a little-endian MSBT'
        assert data[0xc] == 1, 'not a UTF-16 MSBT'
        self.header = bytearray(data[:0x20]); count = struct.unpack_from('<H', data, 0xe)[0]
        sections, at = [], 0x20
        for _ in range(count):
            magic, size = data[at:at + 4], struct.unpack_from('<I', data, at + 4)[0]
            sections.append((magic, data[at + 16:at + 16 + size])); at += 16 + ((size + 15) & ~15)
        names = [m for m, _ in sections]
        assert names == [b'LBL1', b'TXT2'], f'unsupported MSBT sections {names}'
        lbl, txt = sections[0][1], sections[1][1]
        self.slots = struct.unpack_from('<I', lbl, 0)[0]; self.labels = {}; self.slot_order = []
        for s in range(self.slots):
            n, o = struct.unpack_from('<II', lbl, 4 + s * 8); row = []
            for _ in range(n):
                length = lbl[o]; name = lbl[o + 1:o + 1 + length].decode()
                self.labels[name] = struct.unpack_from('<I', lbl, o + 1 + length)[0]; row.append(name); o += 5 + length
            self.slot_order.append(row)
        n = struct.unpack_from('<I', txt, 0)[0]; offsets = list(struct.unpack_from(f'<{n}I', txt, 4)) + [len(txt)]
        self.texts = [txt[offsets[i]:offsets[i + 1]] for i in range(n)]

    def text(self, label):
        """The text of `label` without its terminating NUL, as raw UTF-16LE (tags included)."""
        raw = self.texts[self.labels[label]]
        return raw[:-2] if raw.endswith(b'\0\0') else raw

    def set(self, label, utf16):
        """Replace or add `label` with raw UTF-16LE text (a terminating NUL is added)."""
        raw = utf16 + b'\0\0'
        if label in self.labels:
            self.texts[self.labels[label]] = raw
        else:
            self.labels[label] = len(self.texts); self.texts.append(raw)
            self.slot_order[_msbt_hash(label, self.slots)].append(label)

    def bytes(self):
        def section(magic, body):
            return magic + struct.pack('<I', len(body)) + b'\0' * 8 + body + b'\xab' * (-len(body) % 16)
        rows = b''; table = struct.pack('<I', self.slots); at = 4 + 8 * self.slots
        for row in self.slot_order:
            table += struct.pack('<II', len(row), at + len(rows))
            for name in row:
                b = name.encode(); rows += bytes([len(b)]) + b + struct.pack('<I', self.labels[name])
        txt = struct.pack('<I', len(self.texts)); at = 4 + 4 * len(self.texts); body = b''
        for t in self.texts:
            txt += struct.pack('<I', at + len(body)); body += t
        out = bytes(self.header) + section(b'LBL1', table + rows) + section(b'TXT2', txt + body)
        out = bytearray(out); struct.pack_into('<I', out, 0x12, len(out))
        return bytes(out)
