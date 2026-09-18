# diff two binary files, report contiguous diff regions with samples
import sys
from collections import Counter

def diff_regions(a, b, gap=8):
    regions = []
    n = min(len(a), len(b))
    i = 0
    while i < n:
        if a[i] != b[i]:
            j = i
            last = i
            while j < n:
                if a[j] != b[j]:
                    last = j
                    j += 1
                elif j - last <= gap:
                    j += 1
                else:
                    break
            regions.append((i, last + 1))
            i = j
        else:
            i += 1
    return regions

def main(a_path, b_path, max_show=80, gap=8):
    a = open(a_path, 'rb').read()
    b = open(b_path, 'rb').read()
    print(f"A={a_path} len={len(a)} (0x{len(a):X})")
    print(f"B={b_path} len={len(b)} (0x{len(b):X})")
    if len(a) != len(b):
        print(f"*** SIZE MISMATCH delta={len(b)-len(a)}")
    n = min(len(a), len(b))
    regs = diff_regions(a[:n], b[:n], gap)
    total = sum(e - s for s, e in regs)
    print(f"diff regions (gap<={gap} merge): {len(regs)}, total diff bytes: {total}")
    for k, (s, e) in enumerate(regs[:max_show]):
        print(f"[{k}] 0x{s:06X}-0x{e:06X} len={e-s}")
        print(f"    A: {a[s:min(e, s+24)].hex(' ')}")
        print(f"    B: {b[s:min(e, s+24)].hex(' ')}")
    if len(regs) > max_show:
        print(f"... {len(regs)-max_show} more regions not shown")
    c = Counter((s >> 16) for s, e in regs)
    print("region distribution by 64K block:")
    for blk in sorted(c):
        print(f"  0x{blk:04X}0000: {c[blk]} regions, bytes={sum(min(e,((blk+1)<<16))-max(s,blk<<16) for s,e in regs if (s>>16)==blk)}")

if __name__ == '__main__':
    a_path = sys.argv[1]
    b_path = sys.argv[2]
    max_show = int(sys.argv[3]) if len(sys.argv) > 3 else 80
    main(a_path, b_path, max_show)
