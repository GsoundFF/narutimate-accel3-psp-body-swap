# Rebuild the Tenten mod ISO the CORRECT way:
#   FileSize = EXACT CRILAYLA length (16+cs+0x100), NO zero padding
#   (all 1213 original files satisfy this invariant; padding made them malformed)
#   ExtractSize = actual decompressed size of the mod CCS
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import crilayla_official as cri
import _rebuild_cpk as rc
import _write_iso as wi

MOD = '_out_2karbod1_mod.ccs'
CPK_OUT = '_out_data_mod2.cpk'
ISO_OUT = 'game_mod2.iso'

mod = open(MOD,'rb').read()
print('mod decompressed len', len(mod))
packed = cri.compress(mod)
us = int.from_bytes(packed[8:12],'little')
cs = int.from_bytes(packed[12:16],'little')
exact = 16 + cs + 0x100
print('compressed len', len(packed), 'exact(16+cs+0x100)', exact, 'us+0x100', us+0x100)
assert len(packed) == exact, 'compressor output must be self-consistent'
assert cri.decompress(packed) == mod, 'roundtrip failed'

key = ('32btlchr','2karbod1.ccs')
stats = rc.rebuild_cpk('_data.cpk', CPK_OUT,
                       replacements={key: packed},
                       replacement_extract={key: len(mod)},
                       align=2048)
print('CPK stats', stats)
wi.rebuild_iso(CPK_OUT, 'game.iso', ISO_OUT)
print('wrote', ISO_OUT)

# verify read-back: FileSize exact, ExtractSize, decomp matches mod
cpk = open(CPK_OUT,'rb').read()
hm,hp,hd = rc._read_packet(cpk,0)
cols,ro,so,do,rl,nr = rc._utf_cols(hd)
row=8+ro
hmap={n:rc._read_row(hd,row,cols,8+so)[i] for i,(n,_,_) in enumerate(cols)}
CO=hmap['ContentOffset'];TO=hmap['TocOffset'];add=min(CO,min(TO,0x800))
tm,tp,td = rc._read_packet(cpk,TO)
tc,tro,tso_,tdo,trl,tnr = rc._utf_cols(td)
tsabs=8+tso_;trow=8+tro;ni={n:i for i,(n,_,_) in enumerate(tc)}
def co(n): return sum(tc[k][2] for k in range(ni[n]))
for r in range(tnr):
    rb=trow+r*trl
    fn=rc._read_string(td,tsabs,rc._rd_be(td,rb+co('FileName'),4))
    if fn=='2karbod1.ccs':
        fs=rc._rd_be(td,rb+co('FileSize'),4); es=rc._rd_be(td,rb+co('ExtractSize'),4)
        fo=rc._rd_be(td,rb+co('FileOffset'),8)+add
        comp=cpk[fo:fo+fs]
        c2=int.from_bytes(comp[12:16],'little')
        print('readback FileSize=%d ExtractSize=%d exact=%d MATCH=%s' % (fs,es,16+c2+0x100, fs==16+c2+0x100))
        print('decomp==mod:', cri.decompress(comp[:16+c2+0x100])==mod)
        break