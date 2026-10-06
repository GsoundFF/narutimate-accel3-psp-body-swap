# tools/ —— 脚本说明

这些脚本是**可运行的模板**，用于复现"外科手术式换模 + CRILAYLA 精确打包"的流水线。
其中 `_build_mod.py` / `_package_mod2.py` 含本案例的具体文件名与块索引，
**换游戏/换角色时需要按注释修改**。

依赖：Python 3.8+、`numpy`（CCS 库需要）、以及从上游获取的 **Blender CCS Importer**（`ccs_lib`）。

---

## ★ 核心流水线

### `_build_mod.py` —— 换模

读入**目标 T** 与**来源 S** 两个 CCS，在 T 上只替换外观相关块，输出换好的 T CCS。

```bash
python _build_mod.py            # → _out_2karbod1_mod.ccs
```

做了什么（对应 SKILL.md 第 3 节）：

1. T 的 body Model 的 `meshes` ← `deepcopy(S 的 body meshes)`，
   每个 mesh 的 `materialIndex` → T 的 `MAT_clut` 编号
2. `lookupList` / `lookupListCount` ← S 的
3. T 的 body 贴图 `textureData` ← S 的（**赋 `bytearray`，不要赋 `bytes`**）
4. T 的 body CLUT `paletteData` ← S 的
5. 骨架/动画/其余块全部保持 T 的

**运行后会自检**：mesh 顶点数、纹理 md5、materialIndex、lookupList、以及
`materialIndex` 是否全部指向 T 的 MAT。

> 修改点：文件路径常量 `KARIN` / `TENTEN` / `OUT`，以及按名字查找的块名
> （`MDL_2kar00t0 body` / `MDL_2tew00t0 body` / `TEX_2karbody` / `TEX_2tewbody`）。

---

### `_package_mod2.py` —— 压缩 + 重建 CPK + 写 ISO ★成功版★

```bash
python _package_mod2.py         # → game_mod2.iso
```

**关键点：`FileSize` 精确等于 `16+cs+0x100`，绝不补零。**

```python
mod    = open('_out_2karbod1_mod.ccs','rb').read()
packed = crilayla.compress(mod)
assert len(packed) == 16 + int.from_bytes(packed[12:16],'little') + 0x100
assert crilayla.decompress(packed) == mod

key = ('32btlchr','2karbod1.ccs')
rebuild_cpk('_data.cpk', '_out_data_mod2.cpk',
            replacements={key: packed},           # 不补零
            replacement_extract={key: len(mod)},  # ExtractSize = 真实解压长度
            align=2048)
rebuild_iso('_out_data_mod2.cpk', 'game.iso', 'game_mod2.iso',
            cpk_iso_offset=123207680)
```

**运行后会回读验证**：`FileSize == 16+cs+0x100` 且 `decompress(...) == mod`。

> 修改点：`MOD` / `CPK_OUT` / `ISO_OUT` / `key` / `cpk_iso_offset`。

---

## 工具与校验

### `crilayla_official.py` —— CRILAYLA 编解码

```python
import crilayla_official as cri
packed = cri.compress(data)      # data → CRILAYLA 文件字节（精确长度）
data   = cri.decompress(packed)  # CRILAYLA 文件字节 → 原始数据
```

文件布局：`'CRILAYLA'`(8) + `UncompressedSize`(u32) + `CompressedSize`(u32)
+ 压缩位流 + 原始前 `0x100` 字节 ⇒ 总长 `16 + cs + 0x100`。

> ⚠️ 本文件是 **Kuriimu2** `plugin_criware/CRILAYLA.cs` 的 Python 移植，
> 受其上游 **GPL-3.0** 约束（见仓库根 `LICENSE` 的第三方声明）。

---

### `_rebuild_cpk.py` —— CPK 重建

```python
import _rebuild_cpk as rc
stats = rc.rebuild_cpk(src_cpk, out_cpk,
                       replacements={(dir, file): bytes, ...},
                       replacement_extract={(dir, file): int, ...},
                       align=2048)
```

做了什么：按物理顺序重排内容区、按 `align` 对齐、更新每个文件的 `FileOffset`、
把 ETOC 移到内容之后、修补主头（`ContentSize` / `EtocOffset` / `EtocSize`），
并用原有 XOR 密钥流重新加密 `@UTF` 包。**只改数值字段，不重编码表结构。**

同时导出若干解析辅助（`decrypt_utf` / `_read_packet` / `_utf_cols` /
`_read_row` / `_read_string` / `_rd_be`），可用于读 TOC、查文件大小与 CRC 字段。

---

### `_write_iso.py` —— 写回 ISO

```python
from _write_iso import rebuild_iso
rebuild_iso(cpk_path, 'game.iso', 'game_mod.iso', cpk_iso_offset=123207680)
```

把重建后的 CPK 覆盖写入 ISO 的固定偏移（本作 `data.cpk` 在 `123207680`）。
**不重建 ISO 文件系统**，只替换该区域的字节，因此长度必须一致。

---

### `_list_iso.py` —— 列出 ISO 目录

```bash
python _list_iso.py game.iso
```

解析 UDF/PVD 与目录记录，打印每个文件的 `size / LBA / 绝对偏移 / 路径`。
用于定位 `PSP_GAME/SYSDIR/EBOOT.BIN`、`PSP_GAME/USRDIR/data.cpk` 等。

---

### `_rt.py` —— roundtrip 无损校验

```bash
python _rt.py <源.ccs> <输出.ccs>
```

`readCCS(src)` 后用同一版本写回 `<输出>`。配合 `_diff.py` 验证读写器是否**逐字节无损**。
**这是动手前的第一道验收门。**

---

### `_diff.py` —— 二进制差异定位

```bash
python _diff.py A.bin B.bin [max_regions]
```

按"间隔 ≤ 8 字节合并"聚合成连续差异区间，报告：区间数、总差异字节数、
按 64K 分块的分布、以及每个区间前 24 字节的十六进制对比。

用于确认：
- roundtrip 是否**零差异**；
- 换模后的字节差异是否**只落在**预期的区域（body Model 区 + 贴图/CLUT 区）。

---

## 典型使用顺序

```bash
# 1) 验收门：读写器无损
python _rt.py <原T.ccs> _rt_T.ccs && python _diff.py <原T.ccs> _rt_T.ccs
python _rt.py <原S.ccs> _rt_S.ccs && python _diff.py <原S.ccs> _rt_S.ccs

# 2) 换模（自检 mesh/纹理/material）
python _build_mod.py

# 3) 打包（精确长度，不补零）+ 回读验证
python _package_mod2.py

# 4) 差异确认：改后 CCS 相对原 T 的差异只落在预期区域
python _diff.py <原T.ccs> _out_<T>bod1_mod.ccs
```

---

## 脚本命名惯例

```
_build_mod.py          换模构建（T + S → _out_<T>bod1_mod.ccs）
_package_mod2.py       压缩+重建CPK+写ISO（FileSize 精确不补零）★
_rt.py / _diff.py      roundtrip 无损校验 / 二进制差异定位
crilayla_official.py   CRILAYLA compress/decompress
_rebuild_cpk.py        CPK 重建
_write_iso.py          ISO 写回
_list_iso.py           ISO 目录列举
```
