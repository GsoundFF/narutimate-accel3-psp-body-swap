# roundtrip: read CCS with ccsLib, write it back, to compare against original bytes
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '_ccs_lib'))
from ccs_lib.ccs import readCCS
from ccs_lib.utils.PyBinaryReader.binary_reader import BinaryReader

def roundtrip(src, dst, version=None):
    ccs = readCCS(src)
    ver = version if version is not None else ccs.version
    br = BinaryReader(encoding='cp932')
    br.write_struct(ccs, ver)
    data = bytes(br.buffer())
    with open(dst, 'wb') as f:
        f.write(data)
    print(f"roundtrip: {src} -> {dst}  version=0x{ver:X}  out_size={len(data)}")
    return ccs

if __name__ == '__main__':
    src = sys.argv[1]
    dst = sys.argv[2]
    ver = int(sys.argv[3], 0) if len(sys.argv) > 3 else None
    roundtrip(src, dst, ver)
