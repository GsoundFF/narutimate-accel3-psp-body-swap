# Build the Tenten-onto-Karin body mod using the (now lossless) ccsLib.
#
# Strategy (as designed/validated previously):
#   Base  = Karin 2karbod1.ccs  (keep ALL structure: skeleton OBJ_2kar00t0, animations,
#           accessories, materials/textures for non-body parts).
#   Replace ONLY:
#     (1) body Model chunk 'MDL_2kar00t0 body'  -> Tenten's body mesh data,
#         with materialIndex remapped to Karin's MAT_clut and lookupList = Tenten's.
#     (2) body texture 'TEX_2karbody' pixel data -> Tenten's 'TEX_2tewbody', AND
#         its CLUT palette -> Tenten's body CLUT palette.
import sys, os, copy, hashlib
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '_ccs_lib'))
from ccs_lib.ccs import readCCS
from ccs_lib.utils.PyBinaryReader.binary_reader import BinaryReader

KARIN = '_out_2kar_dec.ccs'
TENTEN = '_out_2tewbod1_dec.ccs'
OUT = '_out_2karbod1_mod.ccs'

def get_by_name(ccs, ctype, name):
    for c in ccs.sortedChunks.get(ctype, []):
        if c.name == name:
            return c
    return None

print('Reading Karin base...')
kar = readCCS(KARIN)
print('Reading Tenten source...')
tew = readCCS(TENTEN)

def verify(ccs, ctype, name):
    c = get_by_name(ccs, ctype, name)
    print(f'  {ctype} "{name}": ', 'found idx=%d' % c.index if c else 'MISSING!!!')
    return c

# ---- (1) body model swap ----
kar_model = verify(kar, 'Model', 'MDL_2kar00t0 body')
tew_model = verify(tew, 'Model', 'MDL_2tew00t0 body')
assert kar_model and tew_model, 'body model missing'

kar_mat = verify(kar, 'Material', 'MAT_clut')
tew_mat = verify(tew, 'Material', 'MAT_clut')

print(f'  kar body meshCount={kar_model.meshCount} vScale={kar_model.vertexScale}')
print(f'  tew body meshCount={tew_model.meshCount} vScale={tew_model.vertexScale}')
assert kar_model.meshCount == tew_model.meshCount, 'mesh counts differ'
assert tew_model.vertexScale == kar_model.vertexScale, 'vertex scale differs'
assert kar_model.modelType == tew_model.modelType, 'modelType differs'

# deep-copy Tenten's meshes so we don't mutate the source when remapping
kar_model.meshes = copy.deepcopy(tew_model.meshes)
# remap each mesh material index to Karin's MAT_clut
for m in kar_model.meshes:
    if hasattr(m, 'materialIndex'):
        m.materialIndex = kar_mat.index
# take Tenten's lookup list (bones used by Tenten's body skin)
kar_model.lookupList = list(tew_model.lookupList)
kar_model.lookupListCount = tew_model.lookupListCount
print(f'  replaced model: meshCount={len(kar_model.meshes)} lookupListCount={kar_model.lookupListCount}')

# ---- (2) body texture + CLUT swap ----
kar_tex = verify(kar, 'Texture', 'TEX_2karbody')
tew_tex = verify(tew, 'Texture', 'TEX_2tewbody')
assert kar_tex and tew_tex
print(f'  kar tex type=0x{kar_tex.textureType:02x} {kar_tex.width}x{kar_tex.height} clutIndex={kar_tex.clutIndex} dataLen={len(kar_tex.textureData)}')
print(f'  tew tex type=0x{tew_tex.textureType:02x} {tew_tex.width}x{tew_tex.height} clutIndex={tew_tex.clutIndex} dataLen={len(tew_tex.textureData)}')
assert kar_tex.textureType == tew_tex.textureType and kar_tex.width == tew_tex.width and kar_tex.height == tew_tex.height, \
    'body textures not same format/size'

# body texture data -> Tenten's
kar_tex.textureData = copy.deepcopy(tew_tex.textureData)
kar_tex.textureDataSize = tew_tex.textureDataSize

# CLUT palette -> Tenten's
kar_clut = kar.chunks.get(kar_tex.clutIndex)
tew_clut = tew.chunks.get(tew_tex.clutIndex)
assert kar_clut and tew_clut, 'clut missing'
print(f'  kar CLUT idx={kar_tex.clutIndex} colors={kar_clut.colorCount}')
print(f'  tew CLUT idx={tew_tex.clutIndex} colors={tew_clut.colorCount}')
assert kar_clut.colorCount == tew_clut.colorCount, 'clut color counts differ'
kar_clut.paletteData = copy.deepcopy(tew_clut.paletteData)
kar_clut.colorCount = tew_clut.colorCount

# ---- serialize ----
print('Serializing mod CCS...')
br = BinaryReader(encoding='cp932')
br.write_struct(kar, kar.version)
data = bytes(br.buffer())
with open(OUT, 'wb') as f:
    f.write(data)
print(f'Wrote {OUT}  size={len(data)} (0x{len(data):X})')

# ---- self verification ----
print('\n=== SELF CHECK ===')
back = readCCS(OUT)
print('  chunk counts:', {k: len(v) for k, v in back.sortedChunks.items() if v})
bm = get_by_name(back, 'Model', 'MDL_2kar00t0 body')
print('  mod body meshCount=%d lookupListCount=%d' % (bm.meshCount, bm.lookupListCount))
print('  tew orig meshCount=%d' % tew_model.meshCount)
print('  mod mesh vtx:', [m.vertexCount for m in bm.meshes])
print('  orig tew vtx:', [m.vertexCount for m in tew_model.meshes])
# texture md5 should equal Tenten's body texture md5
mod_tex = get_by_name(back, 'Texture', 'TEX_2karbody')
print('  mod TEX_2karbody data md5 =', hashlib.md5(mod_tex.textureData).hexdigest())
print('  tew TEX_2tewbody data md5 =', hashlib.md5(tew_tex.textureData).hexdigest())
print('  body texture md5 match:', hashlib.md5(mod_tex.textureData).hexdigest() == hashlib.md5(tew_tex.textureData).hexdigest())
# body model should NOT be MD5-equal to Tenten's body model (different index/name refs) but mesh vtx match
print('  mod meshvtx == tew meshvtx:', [m.vertexCount for m in bm.meshes] == [m.vertexCount for m in tew_model.meshes])
# material index remap check
print('  mod mesh matIndex all == %d (Karin MAT_clut):' % kar_mat.index, set(m.materialIndex for m in bm.meshes))