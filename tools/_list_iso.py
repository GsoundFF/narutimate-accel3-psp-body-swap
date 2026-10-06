import struct, sys

def list_iso(path):
    f = open(path, 'rb')
    f.seek(16 * 2048)
    pvd = f.read(2048)
    root_lba = struct.unpack('<I', pvd[156+2:156+6])[0]
    root_size = struct.unpack('<I', pvd[156+10:156+14])[0]

    def parse_dir(lba, size):
        f.seek(lba * 2048)
        data = f.read(((size + 2047) // 2048) * 2048)
        recs = []
        i = 0
        while i < len(data):
            ln = data[i]
            if ln == 0:
                i = ((i // 2048) + 1) * 2048
                if i >= len(data):
                    break
                continue
            if i + ln > len(data):
                break
            rlba = struct.unpack('<I', data[i+2:i+6])[0]
            rsize = struct.unpack('<I', data[i+10:i+14])[0]
            flags = data[i+25]
            nl = data[i+32]
            raw = data[i+33:i+33+nl]
            try:
                name = raw.decode('latin1')
            except Exception:
                name = repr(raw)
            name = name.split(';')[0]
            recs.append((name, rlba, rsize, flags))
            i += ln
        return recs

    def walk(lba, size, path=''):
        for name, rlba, rsize, flags in parse_dir(lba, size):
            if name in ('.', '..') or name in ('\x00', '\x01'):
                continue
            if flags & 0x02:
                yield from walk(rlba, rsize, path + name + '/')
            else:
                yield (path + name, rlba, rsize)

    yield from walk(root_lba, root_size)

if __name__ == '__main__':
    iso = sys.argv[1] if len(sys.argv) > 1 else 'game.iso'
    entries = list(list_iso(iso))
    total = 0
    for name, lba, size in entries:
        total += size
        print('%10d  LBA=%-8d abs=%-12d %s' % (size, lba, lba * 2048, name))
    print('--- %d files, total %d bytes' % (len(entries), total))
