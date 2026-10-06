# -*- coding: utf-8 -*-
"""
_rebuild_cpk.py  --  CRIWARE CPK full rebuilder (Path B, faithful to CriPakTools).

Reads every file's *compressed* byte stream out of a CPK (no decompression),
lets you replace selected (DirName, FileName) entries, then re-packs the whole
content region sequentially aligned to Align (2048) from ContentOffset, updates
each TOC FileOffset so that (stored FileOffset + add_offset) == the absolute
position where the bytes were actually written, moves ETOC right after the
content, patches the CPK main header (ContentSize / EtocOffset / EtocSize /
ContentOffset) and re-encrypts every @UTF packet with the same XOR keystream
the file already uses.

Structural facts verified against _data.cpk (Naruto Gekitou Ninja Taisen!
Special / "究极觉醒3" style CPKFB):
  * CPK main header packet at 0, encrypted.  ContentOffset=61440,
    ContentSize=301340672, Align=2048, TocOffset=2048, TocSize=58928,
    EtocOffset=301402112, EtocSize=15920, Files=1297, CpkMode=1.
  * TOC packet at TocOffset, encrypted.  One row per content file.
    Columns: DirName(str),FileName(str),FileSize(u32),ExtractSize(u32),
             FileOffset(u64),ID(u32),UserString(str),CRC(u32).
    Row length = 32.  FileOffset stored value + add_offset == absolute.
  * add_offset = 0x800 here  (= min(ContentOffset, min(TocOffset,0x800)))
    which matches CriPakTools CPK.cs ReadTOC exactly.
  * Content region [ContentOffset, ContentOffset+ContentSize) holds every file
    packed sequentially, each ceil(size) padded to Align=2048, no extra gaps.
    ETOC sits immediately after content.
  * ETOC packet encrypted, columns [UpdateDateTime(u64), LocalDir(str)],
    1298 rows (one extra empty trailing row), rows indexed to files.

Only numeric field *values* change during a rebuild (all columns are fixed
width), so the decrypted TOC/header/ETOC packet byte length never changes and
we can safely re-encrypt in place -- we never have to re-encode the @UTF table
structure.  This is exactly what CriPakTools' UpdateFileEntry does.
"""

import struct

# ---------------------------------------------------------------------------
# UTF / CPK low-level helpers
# ---------------------------------------------------------------------------

def decrypt_utf(inp):
    """XOR decrypt/encrypt an @UTF payload (involution)."""
    m = 0x655F
    t = 0x4115
    out = bytearray(len(inp))
    for i, b in enumerate(inp):
        out[i] = b ^ (m & 0xFF)
        m = (m * t) & 0xFFFFFFFF
    return bytes(out)


def _rd_be(buf, off, n):
    return int.from_bytes(buf[off:off + n], 'big')


def _utf_cols(dec):
    """Parse the column descriptors of a decrypted @UTF payload.

    Returns (cols, rows_offset, strings_offset, data_offset, row_length,
    num_rows) with rows_offset etc relative to the START of `dec`
    (i.e. already +8 inside @UTF as stored in the packet).  Each col entry:
    (name, flags, per_row_size_in_bytes).
    """
    rows_offset = _rd_be(dec, 8, 4)
    strings_offset = _rd_be(dec, 12, 4)
    data_offset = _rd_be(dec, 16, 4)
    num_columns = _rd_be(dec, 24, 2)
    row_length = _rd_be(dec, 26, 2)
    num_rows = _rd_be(dec, 28, 4)
    strings_abs = 8 + strings_offset
    cols = []
    q = 32
    for _ in range(num_columns):
        flags = dec[q]
        q += 1
        if flags == 0:
            q += 3
            flags = dec[q]
            q += 1
        name_off = _rd_be(dec, q, 4)
        q += 4
        end = dec[strings_abs + name_off:].find(b'\x00')
        name = dec[strings_abs + name_off: strings_abs + name_off + end].decode('ascii', 'replace')
        storage = flags & 0xF0
        typ = flags & 0x0F
        if storage == 0x50:                      # per-row
            if typ in (0, 1):
                psize = 1
            elif typ in (2, 3):
                psize = 2
            elif typ in (4, 5):
                psize = 4
            elif typ in (6, 7):
                psize = 8
            elif typ == 8:
                psize = 4
            elif typ == 0xA:                     # string -> row stores u32 offset
                psize = 4
            elif typ == 0xB:                     # bytearray -> offset(4)+size(4)
                psize = 8
            else:
                psize = 0
        else:                                    # NONE / ZERO / CONSTANT: no row bytes
            psize = 0
        cols.append((name, flags, psize))
    return cols, rows_offset, strings_offset, data_offset, row_length, num_rows


def _read_string(dec, strings_abs, off):
    end = dec[strings_abs + off:].find(b'\x00')
    if end < 0:
        end = len(dec) - (strings_abs + off)
    return dec[strings_abs + off: strings_abs + off + end].decode('ascii', 'replace')


def _read_row(dec, row_base, cols, strings_abs):
    """Read one row into a list aligned with `cols`."""
    rp = row_base
    out = []
    for (name, flags, psize) in cols:
        storage = flags & 0xF0
        typ = flags & 0x0F
        if storage != 0x50:
            out.append(None)
            continue
        if typ in (0, 1):
            v = dec[rp]
        elif typ in (2, 3):
            v = _rd_be(dec, rp, 2)
        elif typ in (4, 5):
            v = _rd_be(dec, rp, 4)
        elif typ in (6, 7):
            v = _rd_be(dec, rp, 8)
        elif typ == 8:
            v = struct.unpack('>f', dec[rp:rp + 4])[0]
        elif typ == 0xA:
            soff = _rd_be(dec, rp, 4)
            v = _read_string(dec, strings_abs, soff)
        else:
            v = None
        rp += psize
        out.append(v)
    return out


def _read_packet(data, offset):
    """Return (magic, full_packet_len_from_magic_start, decrypted_utf)."""
    magic = data[offset:offset + 4]
    utf_size = struct.unpack('<q', data[offset + 8:offset + 16])[0]
    payload = data[offset + 16:offset + 16 + utf_size]
    dec = payload if payload[:4] == b'@UTF' else decrypt_utf(payload)
    return magic, 16 + utf_size, dec


def _encrypt_if_was(data_byte_at_packet_payload_start_was_not_utf,
                    dec, magic_utf):
    return dec


# ---------------------------------------------------------------------------
# Main rebuild
# ---------------------------------------------------------------------------

def rebuild_cpk(src_cpk_path, out_cpk_path, replacements=None,
                replacement_extract=None, align=None, pad_to_src_len=True):
    """Rebuild a CPK after replacing selected file data.

    replacements            : {(DirName, FileName): compressed_bytes}
                              The bytes are stored verbatim (already the exact
                              byte stream that used to live at that TOC entry).
    replacement_extract     : optional {(DirName, FileName): extract_size}
                              Defaults: if the entry is a CRILAYLA stream we
                              derive ExtractSize from the header, else we keep
                              the original ExtractSize.
    align                   : byte alignment for each file slot (default from
                              header Align; fallback 2048).
    pad_to_src_len          : if True, pad output with zeroes up to the source
                              file length so the CPK is a same-size drop-in for
                              an ISO/Umd region.

    Returns a small dict of layout statistics.
    """
    if replacements is None:
        replacements = {}
    src = open(src_cpk_path, 'rb').read()
    src_len = len(src)

    # ---- main header packet ------------------------------------------------
    hdr_magic, hdr_pkt_len, hdr_dec = _read_packet(src, 0)
    assert hdr_magic[:4] == b'CPK '
    hcols, hro, hso, hdo, hrl, hnr = _utf_cols(hdr_dec)
    hname_idx = {name: i for i, (name, _, _) in enumerate(hcols)}
    hrow_base = 8 + hro
    hvals = _read_row(hdr_dec, hrow_base, hcols, 8 + hso)
    hmap = {name: hvals[i] for i, (name, _, _) in enumerate(hcols)}

    def hfield_pos(name):
        # absolute byte position of a per-row u64/u32 field within hdr_dec
        idx = hname_idx[name]
        before = sum(hcols[k][2] for k in range(idx))
        return hrow_base + before

    ContentOffset = hmap['ContentOffset']
    TocOffset = hmap['TocOffset']
    TocSize = hmap['TocSize']
    EtocOffset0 = hmap['EtocOffset']
    EtocSize0 = hmap['EtocSize']
    ContentSize0 = hmap['ContentSize']
    Files = hmap['Files']
    Align = hmap.get('Align') or 2048
    if align is not None:
        Align = align

    # ---- TOC packet ----------------------------------------------------------
    toc_magic, toc_pkt_len, toc_dec = _read_packet(src, TocOffset)
    assert toc_magic[:4] == b'TOC '
    tcols, tro, tso, tdo, trl, tnr = _utf_cols(toc_dec)
    tstrings_abs = 8 + tso
    trow_base = 8 + tro
    name_i = {name: i for i, (name, _, _) in enumerate(tcols)}
    # per-row field start offset (within the row) for the columns we edit
    def col_row_off(name):
        return sum(tcols[k][2] for k in range(name_i[name]))
    fo_off = col_row_off('FileOffset')   # u64
    fs_off = col_row_off('FileSize')     # u32
    es_off = col_row_off('ExtractSize')  # u32
    dir_off = col_row_off('DirName')     # string offset (u32 in row)
    fn_off = col_row_off('FileName')

    rows = []
    for r in range(tnr):
        rb = trow_base + r * trl
        DirName = _read_string(toc_dec, tstrings_abs,
                               _rd_be(toc_dec, rb + dir_off, 4))
        FileName = _read_string(toc_dec, tstrings_abs,
                                _rd_be(toc_dec, rb + fn_off, 4))
        FileSize = _rd_be(toc_dec, rb + fs_off, 4)
        ExtractSize = _rd_be(toc_dec, rb + es_off, 4)
        FileOffset_field = _rd_be(toc_dec, rb + fo_off, 8)
        rows.append(dict(r=r, DirName=DirName, FileName=FileName,
                         FileSize=FileSize, ExtractSize=ExtractSize,
                         FileOffset=FileOffset_field))
    assert tnr == Files, (tnr, Files)

    # add_offset per CriPakTools
    fTocOffset = min(TocOffset, 0x800)
    if ContentOffset < 0:
        add_offset = fTocOffset
    elif TocOffset < 0:
        add_offset = ContentOffset
    else:
        add_offset = min(ContentOffset, fTocOffset)

    # sort by absolute stored position (== physical packing order)
    order = sorted(range(len(rows)), key=lambda i: rows[i]['FileOffset'])

    # ---- read raw compressed bytes for every file in physical order ---------
    blob = bytearray()          # new content region (build streaming)
    out_rows = {}               # r -> (new_file_size, new_extract, new_abs)
    cursor = ContentOffset
    for idx in order:
        row = rows[idx]
        key = (row['DirName'], row['FileName'])
        abs_pos = row['FileOffset'] + add_offset
        raw = src[abs_pos:abs_pos + row['FileSize']]
        if len(raw) != row['FileSize']:
            raise ValueError('short read for %s/%s' % key)
        if key in replacements:
            data = replacements[key]
            if not isinstance(data, (bytes, bytearray)):
                raise TypeError('replacement for %r must be bytes' % (key,))
            data = bytes(data)
        else:
            data = raw
        # ExtractSize
        if replacement_extract is not None and key in replacement_extract:
            extract = int(replacement_extract[key])
        elif key in replacements and data[:8] == b'CRILAYLA':
            # UncompressedSize header (body len) + 0x100 raw tail
            us = struct.unpack('<I', data[8:12])[0]
            cs = struct.unpack('<I', data[12:16])[0]
            if 16 + cs + 0x100 <= len(data):
                extract = us + 0x100
            else:
                extract = row['ExtractSize']
        else:
            extract = row['ExtractSize']
        out_rows[idx] = (len(data), extract, cursor)
        blob += data
        # pad to Align
        rem = len(blob) % Align
        if rem:
            blob += b'\x00' * (Align - rem)
        cursor = ContentOffset + len(blob)

    content_end = cursor
    new_content_size = content_end - ContentOffset
    new_etoc_offset = content_end

    # ---- patch TOC decrypted payload (values only) --------------------------
    toc_dec = bytearray(toc_dec)
    for idx in order:
        rb = trow_base + idx * trl
        nfs, nex, nabs = out_rows[idx]
        # FileOffset stored = abs - add_offset
        struct.pack_into('>Q', toc_dec, rb + fo_off, nabs - add_offset)
        struct.pack_into('>I', toc_dec, rb + fs_off, nfs)
        struct.pack_into('>I', toc_dec, rb + es_off, nex)

    # ---- patch main header decrypted payload --------------------------------
    hdr_dec = bytearray(hdr_dec)
    # ContentSize field
    cs_pos = hfield_pos('ContentSize')
    struct.pack_into('>Q', hdr_dec, cs_pos, new_content_size)
    # EtocOffset field
    eo_pos = hfield_pos('EtocOffset')
    struct.pack_into('>Q', hdr_dec, eo_pos, new_etoc_offset)
    # EtocSize: we keep the same ETOC payload, so keep original EtocSize
    # (do not change).  ContentOffset unchanged.  EnabledPackedSize etc we
    # leave as-is (CriPakTools does not recalc them either).

    # ---- ETOC packet: move to new_etoc_offset, payload unchanged -------------
    etoc_magic, etoc_pkt_len, etoc_dec = _read_packet(src, EtocOffset0)
    assert etoc_magic[:4] == b'ETOC'
    # ETOC payload is not modified (files/order unchanged), so copy the whole
    # packet verbatim (magic+unk1+utf_size+payload) from the source to the new
    # offset.
    etoc_packet_bytes = src[EtocOffset0: EtocOffset0 + etoc_pkt_len]

    # ---- assemble output file ------------------------------------------------
    # Region [0, ContentOffset) holds the original CPK header packet and TOC
    # packet at fixed offsets.  We rebuild it from the *original* bytes but with
    # the two (same-length) packets re-encrypted.
    out = bytearray(src_len if pad_to_src_len else (new_etoc_offset + etoc_pkt_len))

    # 1) copy everything before ContentOffset from the original (this already
    #    includes the original encrypted header & TOC packets at offsets 0/2048)
    out[0:ContentOffset] = src[0:ContentOffset]

    # 2) re-encrypt & overwrite the header packet at 0
    enc_hdr = decrypt_utf(bytes(hdr_dec))
    out[16:16 + len(enc_hdr)] = enc_hdr

    # 3) re-encrypt & overwrite the TOC packet at TocOffset
    enc_toc = decrypt_utf(bytes(toc_dec))
    toc_payload_abs = TocOffset + 16
    out[toc_payload_abs: toc_payload_abs + len(enc_toc)] = enc_toc

    # 4) content region (already padded to Align inside blob)
    out[ContentOffset: content_end] = blob

    # 5) ETOC at new_etoc_offset (identical packet bytes)
    out[new_etoc_offset: new_etoc_offset + etoc_pkt_len] = etoc_packet_bytes

    # 6) zero padding to src_len already provided by the bytearray init

    open(out_cpk_path, 'wb').write(bytes(out))
    stats = dict(
        ContentOffset=ContentOffset, ContentSize=new_content_size,
        TocOffset=TocOffset, EtocOffset=new_etoc_offset,
        EtocSize=etoc_pkt_len, Files=len(rows), Align=Align,
        add_offset=add_offset, out_len=len(out), src_len=src_len,
    )
    return stats


if __name__ == '__main__':
    print('module ok: rebuild_cpk(src, out, replacements=None, '
          'replacement_extract=None, align=None, pad_to_src_len=True)')
