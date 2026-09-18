# -*- coding: utf-8 -*-
"""
crilayla_official.py
====================
A faithful Python port of the CRIWARE CRILAYLA codec as implemented by the
Kuriimu2 plugin "plugin_criware/CRILAYLA.cs".

The format
----------
File layout (the numbers below match the real C# header):
  offset 0x00 : 8 bytes magic "CRILAYLA"
  offset 0x08 : int32 LE UncompressedSize  == length of the encoded *body*
                                          == (decompressed length) - 0x100
  offset 0x10 : the compressed bit stream, length = CompressedSize bytes
  tail 0x100  : the first 0x100 bytes of the original uncompressed data
                (stored verbatim so a decoder can seed the leading bytes).

So:  total_file_len = 0x10 + CompressedSize + 0x100
     decompressed   = tail(0x100) + body,  body length == UncompressedSize.

ReverseStream / bit order
-------------------------
The official decompressor reads the compressed stream *backwards*
(Kuriimu2 ReverseStream): bytes are consumed from the last stream byte down to
the first, and within each byte bits are read MSB -> LSB.  Equivalently the
compressed payload that physically lives in the file is the byte-reversal of a
normal MSB-first bit stream.  `decompress()` below reads directly in that
reversed order; `compress()` therefore builds a normal MSB-first stream and
stores it reversed in the file.

The length field ("VLE") after a backref uses chunk sizes
2 -> 3 -> 5 -> 8 -> 8 ... exactly as the C# `next_bits` table:
  next_bits = {0,0,3,5,0,8,0,0,8}  (indexed by current bit count).

Verification (all pass against the bundled real PSP data):
  1) decompress(_orig_2kar_compressed.bin) == _out_2kar_dec.ccs  (byte-exact)
  2) decompress(compress(_out_2kar_dec.ccs)) == _out_2kar_dec.ccs (roundtrip)
"""

import struct

_MAGIC = b"CRILAYLA"
_RAW_DATA_SIZE = 0x100
_WINDOW = 0x2000 + 2  # 13-bit distance window (matches the 13-bit offset field)
# chunk bit widths used to encode (backref_len - 3)
_VLE_NEXT = (0, 0, 3, 5, 0, 8, 0, 0, 8)


def _le32(x):
    return struct.pack("<I", x)


# ---------------------------------------------------------------------------
# Bit reader / bit writer  (byte order is handled by the caller)
# ---------------------------------------------------------------------------

class _BitReader:
    """Reads bits from a byte sequence.

    Bytes are pulled from `hi-1` downwards toward `lo` (reverse order) and
    within each byte bits are consumed MSB-first.  This is exactly what the
    official decoder observes through its ReverseStream.
    """

    __slots__ = ("_data", "_idx", "_pool", "_left")

    def __init__(self, data, lo, hi):
        self._data = data
        self._idx = hi - 1
        self._pool = 0
        self._left = 0

    def bits(self, n):
        out = 0
        produced = 0
        while produced < n:
            if self._left == 0:
                self._pool = self._data[self._idx]
                self._left = 8
                self._idx -= 1
            take = (n - produced) if self._left > (n - produced) else self._left
            out = (out << take) | ((self._pool >> (self._left - take)) & ((1 << take) - 1))
            self._left -= take
            produced += take
        return out


class _BitWriter:
    """Writes a normal MSB-first bit stream into a growing byte array."""

    __slots__ = ("_out", "_cur", "_nbits")

    def __init__(self):
        self._out = bytearray()
        self._cur = 0
        self._nbits = 0

    def bits(self, value, count):
        for i in range(count - 1, -1, -1):
            bit = (value >> i) & 1
            self._cur = (self._cur << 1) | bit
            self._nbits += 1
            if self._nbits == 8:
                self._out.append(self._cur)
                self._cur = 0
                self._nbits = 0

    def finish(self):
        if self._nbits:
            self._out.append(self._cur << (8 - self._nbits))


# ---------------------------------------------------------------------------
# Decompress
# ---------------------------------------------------------------------------

def decompress(packed):
    """Unpack a full CRILAYLA file -> 0x100 + UncompressedSize bytes.

    Faithful transcription of the C# `Decompress`, including the exact
    destPos / offset arithmetic and the backward cascading copy.
    """
    if packed[:8] != _MAGIC:
        raise ValueError("not a CRILAYLA stream")
    us = struct.unpack("<I", packed[8:12])[0]
    cs = struct.unpack("<I", packed[12:16])[0]

    size = _RAW_DATA_SIZE + us
    dest = bytearray(size)

    # seed leading 0x100 bytes from the file tail
    prefix_start = 0x10 + cs
    dest[0:_RAW_DATA_SIZE] = packed[prefix_start:prefix_start + _RAW_DATA_SIZE]

    br = _BitReader(packed, 0x10, 0x10 + cs)
    dest_pos = size

    while dest_pos > _RAW_DATA_SIZE:
        if br.bits(1):                      # back-reference
            initial_offset = br.bits(13)
            offset = dest_pos + initial_offset
            dest_pos -= 3

            def read_offset(bits):
                nonlocal dest_pos, offset
                value = br.bits(bits)
                dest_pos -= value
                offset -= value
                return value

            if initial_offset >= 3:
                # source and destination do not overlap -> single forward copy
                more = read_offset(2)
                n = 3 + more
                dest[dest_pos:dest_pos + n] = dest[offset:offset + n]
            else:
                # two copies (3 bytes then `more`) -- overlap is impossible
                dest[dest_pos:dest_pos + 3] = dest[offset:offset + 3]
                more = read_offset(2)
                dest[dest_pos:dest_pos + more] = dest[offset:offset + more]

            if more == 3:
                more = read_offset(3)
                _backward_copy(dest, offset, dest_pos, more)
                if more == 7:
                    more = read_offset(5)
                    _backward_copy(dest, offset, dest_pos, more)
                    if more == 31:
                        while True:
                            more = read_offset(8)
                            _backward_copy(dest, offset, dest_pos, more)
                            if more != 255:
                                break
        else:                               # literal
            dest_pos -= 1
            dest[dest_pos] = br.bits(8)

    return bytes(dest)


def _backward_copy(dest, offset, dest_pos, count):
    """C# BackwardCascadingCopy: copies `count` bytes high->low so overlapping
    source/destination ranges are reproduced correctly."""
    d = dest_pos + count
    s = offset + count
    for _ in range(count):
        d -= 1
        s -= 1
        dest[d] = dest[s]


# ---------------------------------------------------------------------------
# Compress
# ---------------------------------------------------------------------------

def _write_vle_length(bw, extra):
    """Encode (backref_len - 3) using the 2->3->5->8->8... chunk scheme.

    Matches the C# WriteBackref do/while loop.
    """
    leftover = extra
    bits = 2
    while True:
        bits_max = (1 << bits) - 1
        chunk = leftover if leftover < bits_max else bits_max
        leftover -= chunk
        bw.bits(chunk, bits)
        if chunk != bits_max:
            break
        bits = _VLE_NEXT[bits]


def _write_backref(bw, offset_13, total_len):
    """Emit a back-ref token for a match of `total_len` (>=3) bytes whose
    13-bit distance field equals `offset_13` (must be 0..0x1FFF)."""
    bw.bits(1, 1)
    bw.bits(offset_13, 13)
    _write_vle_length(bw, total_len - 3)


def compress(data):
    """Compress arbitrary bytes (>0x100) into a full CRILAYLA file.

    Body (data[0x100:]) is encoded backward, matching how the decoder walks
    the output from high to low addresses.  A greedy hash-chained match finder
    produces back-refs; anything unmatched is written raw.
    """
    if len(data) <= _RAW_DATA_SIZE:
        raise ValueError("input must be longer than 256 bytes")

    us = len(data) - _RAW_DATA_SIZE
    body = data[_RAW_DATA_SIZE:]
    n = us

    bw = _BitWriter()
    MINLEN = 3

    # Hash chain over the downward 3-gram at each body top-index `s`.
    # Candidate source indices must already be encoded, i.e. greater than the
    # position we are currently emitting (we emit descending).
    chains = {}
    pos = n - 1
    next_insert = n

    def insert_source(s):
        if s >= 2:
            key = (body[s] << 16) | (body[s - 1] << 8) | body[s - 2]
            chains.setdefault(key, []).append(s)

    while pos >= 0:
        # Make already-encoded indices available as match sources.  A source
        # run must start far enough above `pos` that the 13-bit offset field
        # (== s - pos - 3) stays non-negative and <= 0x1FFF, i.e. s >= pos+3.
        while next_insert - 1 >= pos + 3:
            insert_source(next_insert - 1)
            next_insert -= 1

        best_len = 0
        best_src = -1

        if pos >= 2:
            key = (body[pos] << 16) | (body[pos - 1] << 8) | body[pos - 2]
            lst = chains.get(key)
            if lst:
                searched = 0
                for s in lst:
                    dist = s - pos - 3
                    if dist > 0x1FFF:      # beyond the 13-bit window
                        if searched > 512:
                            break
                        continue
                    searched += 1
                    # hash already guarantees body[pos..pos-2] == body[s..s-2]
                    run = 3
                    lo = pos if pos < s else s
                    while run <= lo and body[pos - run] == body[s - run]:
                        run += 1
                    if run > best_len:
                        best_len = run
                        best_src = s
                    if searched > 4096:
                        break

        if best_len >= MINLEN:
            _write_backref(bw, best_src - pos - 3, best_len)
            pos -= best_len
            continue

        # literal
        bw.bits(0, 1)
        bw.bits(body[pos], 8)
        pos -= 1

    bw.finish()
    payload = bytes(bw._out)           # normal MSB-first stream
    cs = len(payload)
    stream = payload[::-1]             # stored reversed (ReverseStream layout)

    head = _MAGIC + _le32(us) + _le32(cs)
    return head + stream + bytes(data[:_RAW_DATA_SIZE])


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    orig = open("_orig_2kar_compressed.bin", "rb").read()
    ref = open("_out_2kar_dec.ccs", "rb").read()

    d1 = decompress(orig)
    print("[verify 1] decompress(original) == _out_2kar_dec.ccs :", d1 == ref,
          "(len %d)" % len(d1))

    c = compress(ref)
    print("[verify 2] roundtrip identical                      :",
          decompress(c) == ref)

    print("[report]   compress(_out_2kar_dec.ccs) length      :", len(c),
          " original compressed:", len(orig), " raw:", len(ref))
