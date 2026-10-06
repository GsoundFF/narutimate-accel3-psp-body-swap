# 让 ccsLib 做到「逐字节无损」的 7 处修改

> 前置工程：**在读/写 CCS 之前，必须先证明读写器是无损的** ——
> `roundtrip(原T) == 原T 的字节` 且 `roundtrip(原S) == 原S 的字节`（差异必须为 0）。
> 否则即使换模逻辑写对了，重写出的字节也和原件有出入，问题无法定位。

依赖：**Blender CCS Importer**（`ccs_lib`，作者 Hydra / Al-Hydra 等，自有 License）。
本仓库不打包该库，请从上游获取，然后按下表修改。

验证用脚本：`tools/_rt.py`（roundtrip）+ `tools/_diff.py`（差异定位）。

---

## 0. 验收标准

```
python tools/_rt.py <原文件.ccs> _rt_out.ccs
python tools/_diff.py <原文件.ccs> _rt_out.ccs   # 期望：diff regions = 0，total diff bytes = 0
```

对**目标角色 T** 与**来源角色 S** 两个 CCS 都要通过。

---

## 1. `ccs_lib/Anms.py` — Animation 帧子块编号 off-by-one

原版 `Frame` 子块的编号是**「下一帧」语义**，应写 `current_frame + 1`；ccsLib 原本写的是
`current_frame`。

**改**：`anmChunkWriter` 里非最终 Frame 块，写出时用 `current_frame + 1`。

---

## 2. `ccs_lib/Anms.py` — `objectFrame.__br_write__` 掩码误用十进制

控制标志的位掩码被写成了十进制字面量，应按十六进制：

| 错误（十进制） | 正确（十六进制） |
|---|---|
| `10` | `0x10` |
| `20` | `0x20` |
| `40` | `0x40` |
| `80` | `0x80` |
| `100` | `0x100` |
| `200` | `0x200` |
| `400` | `0x400` |
| `800` | `0x800` |

（`0x2` / `0x4` / `0x8` 本就是十六进制等价值，无需改。）

```python
# 例：位置/旋转/缩放/透明度/has_model 的判定
if self.ctrlFlags & 0x10: ...
if self.ctrlFlags & 0x20: ...
# ...
```

---

## 3. `ccs_lib/ccsModel.py` — 法线缩放：读 `1/127` 而写 `×64`

法线的**写出**缩放是 `×64`（即 `1/64`），但**读取**用的是 `1/127`，比例 ≈ 0.5，
导致法线数据被"减半"破坏。

**改**：读取用 `1.0/64.0`：

- `RigidMesh.__br_read__` 中 normals 与 tangents/bitangents 的读取缩放 → `1.0/64.0`
- `DeformableMesh.__br_read__` 中 `normalScale` → `1.0/64.0`

---

## 4. `ccs_lib/ccsModel.py` — RigidMesh 颜色 `×2 + clamp` 的位损失

读取时把颜色 `×2` 并 `clamp` 到 255，写出时又 `/2` —— 会丢位。

**改**：读取**保留原始 uint8**（不要 `np.minimum(255, col*2)`），写出直接
`vcBuffer.write_uint8(v_col[0..3])`（不要 `round(v_col/2)`）。

---

## 5. `ccs_lib/ccsModel.py` — 多权重法线写出永远取 slot 0

多权重（`dc > 0`）网格写出法线时，所有权重槽都写成 slot 0 的法线。

**改**：按各自的槽位取 —— 用 `get_normals(self, v, i)`（`i` 为当前槽）而不是固定 slot 0。

---

## 6. `ccs_lib/ccsClut.py` — 调色板 alpha `×2 + clamp` 的位损失

CLUT 调色板读取时对 alpha `×2` 并 clamp，写出时 `/2` —— 同样会丢位。

**改**：
- 读取：`paletteData = palette.astype(np.uint8).tolist()`（去掉 `×2`/clamp）
- 写出：直接写 `p_color[0..3]`（去掉 `/2`）

---

## 7. `ccs_lib/ccs.py` — 写出时保留 chunk 的原始 `size` 字段

原文件里某些 chunk 的 `size` 字段与「内容长度」并不相等
（本作 **Model 1710** 的 size 字段比内容多算 `0xFF` 单位 = 1020 字节）。
**游戏并不按 size 字段遍历块**，所以最稳妥的做法是**原样保留读到的 size 字段**。

**改**：
1. `__br_read__` 的常规块循环里，读到 size 字段时保存：`chunkData.sizeField = rawSizeField`
2. `__br_write__` 写块大小时：

```python
content_units = chunk_buf.size() // 4

if chunk.type == "Texture" and chunk.textureType in {0x0, 0x13, 0x14}:
    br.write_uint32(content_units + 0x32)          # 纹理有固定附加量
elif chunk.type == "Texture" and chunk.textureType in {0x87, 0x88, 0x89}:
    br.write_uint32(content_units)
else:
    stored = getattr(chunk, 'sizeField', None)
    if stored is not None and stored >= content_units:
        br.write_uint32(stored)                    # 保留原值
    else:
        br.write_uint32(content_units)             # 兜底
```

---

## 附：另一个容易踩的坑（不属于 ccsLib）

`Texture.textureData` 写出时走的是「可迭代展开」分支：

```python
br.write_uint8(self.textureData)
```

- 若 `textureData` 是 **`bytes`** → 会被当成单个值展开失败
  （`struct.error: pack_into expected N items for packing (got 1)`）。
- 若 `textureData` 是 **`bytearray`**（读取 `read_bytes` 返回的就是 `bytearray` 切片）→ 正常。

**结论**：给 `textureData` 赋值时务必用 **`bytearray`**，不要赋 `bytes`。

---

## 修改完成后的自检清单

- [ ] `roundtrip(T) == T`（diff = 0）
- [ ] `roundtrip(S) == S`（diff = 0）
- [ ] 换模后再读回：mesh 顶点数 == S 的、纹理 md5 == S 的、
      全部 `mesh.materialIndex` == T 的 MAT 编号
- [ ] 与 T 原文件的字节差异**只落在** body Model 区 + 贴图/CLUT 区
