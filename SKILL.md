---
name: narutimate-accel3-psp-body-swap
description: PSP《火影忍者疾风传 究极觉醒3》(ULJS00236) 角色外观替换 —— 把来源角色 S 的 body 模型/贴图/调色板换到目标角色 T 身上，T 的骨架/动作/招式全部保留。方法：ccsLib 外科手术式替换 CCS 的 body Model/TEX/CLUT 块 + CRILAYLA 精确重压 + 重建 CPK + 写回 ISO。核心心法：CRILAYLA 文件的 FileSize 必须精确等于 16+cs+0x100（禁止补零），否则游戏拒绝载入（表现为"选角色进不了战斗"）。Also usable for debugging a same-style PSP CPK/CCS mod that shows no effect or hangs on entering battle.
whenToUse: 当用户在 PSP《究极觉醒3》(ULJS00236) 或同类"CRILAYLA 压缩的 CPK + CCS 模型"的 PSP 火影游戏里，要求"把 X 的模型/外观换到 Y 上""换个皮肤/衣服""保留 Y 的动作只换外观"，或排查这类 MOD 无效果/进战斗卡死/黑屏时使用。Use when swapping a character's body model/appearance in PSP Naruto Shippuden Ultimate Ninja Heroes 3 (a.k.a. 究极觉醒3) or any similar CCS-inside-CRILAYLA-CPK PSP title.
---

# PSP《火影忍者疾风传 究极觉醒3》角色外观替换（CCS 外科手术 + CRILAYLA 精确打包）

目标：让角色 **T（目标）** 显示角色 **S（来源）** 的外观（body 模型 + body 贴图 + 调色板），
**而动作/招式/骨架仍是 T 的**。

> **方向先确认（最容易搞反）**："把 A 的模型换到 B 上" ⇒ **目标 T = B，来源 S = A**。
> 本案：把天天的模型换到香磷上 ⇒ T=香磷(2kar)、S=天天(2tew)。
> 即：改的是**香磷**的 `2karbod1.ccs`，模型/贴图取自**天天** `2tewbod1.ccs`。

---

## 0. 环境与工具（先确认）

- 工作区（ROOM）：游戏目录，含 `game.iso`、`_data.cpk`（从 ISO 抽出的 CPK）、脚本。
- `game.iso` → `PSP_GAME/USRDIR/data.cpk` 在 **ISO 内偏移 123207680**（本作固定）。
- CPK 内文件用 **CRILAYLA** 压缩；CCS 版本 **0x123**（签名 `CCSF`）。
- CCS 库：`_ccs_lib/`（`readCCS` / `BinaryReader.write_struct`）。
- 脚本：`crilayla_official.py`（`compress`/`decompress`）、`_rebuild_cpk.py`
  （`rebuild_cpk(src,out,replacements,replacement_extract,align)`）、
  `_write_iso.py`（`rebuild_iso(cpk,iso_in,iso_out,cpk_iso_offset=123207680)`）。

**先验证映射再动手**：从 ISO 偏移 123207680 读 0x800 字节 → `decrypt_utf` → 应是 `CPK ` 头；
CPK 内 `('32btlchr','2karbod1.ccs')` 读出应 `CRILAYLA` + 解压得 `CCSF` 开头。

---

## 1. ★ 头号铁律：CRILAYLA 文件必须"精确长度、零补零"

**这是本类 mod "进不了战斗" 的 99% 真因，比换模本身重要得多。**

CRILAYLA 文件格式：
```
0x00  'CRILAYLA'                       (8B)
0x08  UncompressedSize = us (u32 LE)   (解压体长度 = 总解压长度 - 0x100)
0x0C  CompressedSize   = cs (u32 LE)
0x10  压缩位流 (cs 字节，倒序/ReverseStream 布局)
末尾  原始数据的前 0x100 字节 (0x100 B)
⇒ 文件总长恒等于  16 + cs + 0x100
```

- **遍历原版 CPK 的全部 CRILAYLA 文件可验证：`FileSize` 100% 精确等于 `16+cs+0x100`，
  没有一个补零的**（本作实测 1213/1213）。
- 改内容后重压，**压缩长度本来就会变**（自己的压缩器常比原厂更狠）。**绝不要为了
  "保持原 FileSize/ExtractSize 不变"而给压缩流补零** —— 那会让 `FileSize ≠ 16+cs+0x100`，
  文件自相矛盾，游戏判定非法 → **表现就是"选角色进不了战斗"（卡死/黑屏）**。
- 正确写法：
  ```
  packed      = crilayla.compress(new_ccs)      # 精确长度
  FileSize    = len(packed)                     # == 16+cs+0x100，不补零
  ExtractSize = len(new_ccs)                    # 解压后的真实长度（改模后通常会变小）
  ```
- **反模式**：给"保持原尺寸"的执念补零；拿"内容没改只是重打包"的对照 ISO 能进来
  反推"游戏在校验内容 CRC" —— 对照 ISO 用的是**原版未重压字节**（长度天然精确），
  根本不能作为"CRC 校验"的证据。**做对照实验必须一次只改一个变量。**

> 本案血泪：曾因补零而误判为"游戏对内容做 CRC 完整性校验"，浪费大量时间逆向 CPK 的
> CRC 字段（CRC32 全目录 / md5 / sha / FNV / Jenkins / Murmur / xxHash / GF(2) 差分 GCD
> 判断多项式 CRC —— 全部不是）。去掉补零后一次成功。

---

## 2. 文件角色分工

| 路径（CPK 内） | 作用 |
|---|---|
| `32btlchr/2XXXbod1.ccs` | **战斗模型**（进战斗看到的外观）—— 首要目标 |
| `32btlchr/2XXXcha0.ccs` / `cha1.ccs` | 招式特效件，一般不动 |
| `32btlchr/2XXXpct.ccs` | 其他（本次未动） |

`2kar`=香磷、`2tew`=天天（本作命名）。不确定代码时，把 body 贴图渲成 PNG 让人肉眼确认。

---

## 3. CCS 换模：只替换"外观相关块"

读入 **T（基底）** 与 **S（来源）** 两个 CCS，在 T 上替换：

**(1) body Model**
- T 的 `MDL_<T>00t0 body`（本案 idx 1710）；S 的 `MDL_<S>00t0 body`（idx 2273）
- `deepcopy` S 的 `meshes` 换给 T；两者应同为 DeformableMesh、meshCount 相同、
  `vertexScale` 相同
- 每个 mesh 的 `materialIndex` → 改成 **T 的** `MAT_clut` 编号（本案 2274→1711）
- `lookupList` / `lookupListCount` → 用 S 的（本案 20 项）

**(2) body 贴图**
- T 的 `TEX_<T>body`（idx 1712）`textureData` ← S 的 `TEX_<S>body`（idx 2275）
- 两者应同 `textureType`（本案 0x13=Indexed8）、同 宽高（128x256）、同数据长度
- 校验：`md5(改后纹理) == md5(来源纹理)`
- 写入注意：`textureData` 需为 **bytearray**（不要赋 `bytes`，写出器按可迭代展开）

**(3) 调色板 CLUT**
- T 的 body CLUT `paletteData` ← S 的 body CLUT（本案 1744 ← 2356，各 256 色）

**(4) 其余一律不动**：骨架（Object/Clump）、全部 Animation、Material、
名字表、Stream、其他 Model（脚/木/玉/眼镜等）保留 T 的。

### ★ 为什么跨骨架能直接搬顶点数据
顶点里的 boneID 是 **`Clump.boneIndices` 数组的下标（pos）**，不是骨名表编号。
香磷与天天的 **pos→骨名映射完全一致**（各 25 骨；pos0=trall根、pos3=pelvis、
pos13=head、pos23=r finger0、pos24=body…），所以 S 的顶点在 T 的骨架上语义相同
⇒ **顶点数据一个字节都不用改**，只改 materialIndex / lookupList / 贴图 / 调色板。
（若两角色骨架结构不同，则需按骨名重映射 lookupList —— 那是 Accel2 技能里的做法。）

### 自检标准（必做）
- 块数与结构 == T 原文件
- body mesh 顶点数 == S 的（本案 `[18,38,8,30,14,6,78,829,26,24,70,4,78,61,28,24,687]`）
- 纹理 md5 == S 的（本案 `56455bcf464ff043…`）
- 全部 mesh.materialIndex == T 的 MAT 编号
- 与 T 原文件的字节差异**只落在** body Model 区 + body 贴图/CLUT 区（用 `_diff.py` 看）

---

## 4. 前提工程：把 ccsLib 修成"逐字节无损"

有损读写器会让重写字节与原件有别，风险不可控。先做到
**roundtrip(原T)==原字节 且 roundtrip(原S)==原字节**（`_rt.py` + `_diff.py` 差异为 0）。
本作 ccsLib 需修的缺陷：
1. Animation 帧子块编号 off-by-one：原版是"下一帧"语义（写 `current_frame+1`）。`Anms.py`
2. 法线缩放：读 `1/127` 但写 `×64`（≈0.5 破坏）→ 读改 `1/64`。`ccsModel.py`
3. RigidMesh 颜色读取 `×2+clamp`、写出 `/2` → 改原样存取。`ccsModel.py`
4. CLUT 调色板 alpha 读取 `×2+clamp`、写出 `/2` → 改原样存取。`ccsClut.py`
5. 多权重法线写出永远取 slot0 → 改按 slot i 取。`ccsModel.py`
6. `objectFrame.__br_write__` 掩码误用十进制 → 改十六进制。`Anms.py`
7. 写入时**保留 chunk 原始 size 字段**（原 Model 1710 的 size 字段比内容多 0xFF 单位；
   游戏不按 size 字段走块，保留原值最稳）。`ccs.py`

---

## 5. 打包流水线（可直接照抄）

```python
# 5.1 换模 → _out_<T>bod1_mod.ccs
#     读 T、读 S，按第 3 节替换，br.write_struct(ccs, ccs.version) 写出
#     自检：mesh 顶点数 / 纹理 md5 / materialIndex / lookupList

# 5.2 压缩 + 重建 CPK + 写 ISO —— 关键：FileSize 精确、不补零
import crilayla_official as cri, _rebuild_cpk as rc, _write_iso as wi
mod = open('_out_<T>bod1_mod.ccs','rb').read()          # 如 634564B
packed = cri.compress(mod)
assert len(packed) == 16 + int.from_bytes(packed[12:16],'little') + 0x100
assert cri.decompress(packed) == mod
key = ('32btlchr','2<bod1>.ccs')                        # 如 ('32btlchr','2karbod1.ccs')
rc.rebuild_cpk('_data.cpk', '_out_data_mod.cpk',
               replacements={key: packed},              # 注意：packed 不补零
               replacement_extract={key: len(mod)},     # ExtractSize = 真实解压长度
               align=2048)
wi.rebuild_iso('_out_data_mod.cpk', 'game.iso', 'game_mod.iso', cpk_iso_offset=123207680)

# 5.3 回读验证（必做）：从新 ISO 里读该文件，
#     FileSize == 16+cs+0x100 且 decompress(...) == mod
```

---

## 6. 测试协议（不遵守就会得出错误结论）

- 游戏在记忆棒维护安装数据：`<memstick>/PSP/SAVEDATA/ULJS00236DATA/`
  （含 `DATA.CPK` 301418032B + `DATA.BIN` 1040B + `PARAM.SFO`）。
- **换 ISO 测试前必须把 `ULJS00236DATA` 改名/删除**，让游戏从**当前加载的 ISO**
  重新安装数据；否则读到上一份安装数据，结论全错。
  （本案因"连续测多个 ISO 不清理"导致第二个 ISO 未生效、结果被污染，白绕弯路。）
- 启动后出现日文提示「これからインストールを開始します…インストールを開始しますか？」
  → 选「**はい**」。
- **冷启动**模拟器（完全退出再开），不要读战斗中的即时存档。
- 记忆棒路径示例（PPSSPP）：`<PPSSPP目录>\memstick\PSP\SAVEDATA\`。

---

## 7. 排错速查

| 症状 | 首要怀疑 |
|---|---|
| 选角色**进不了战斗**（卡死/黑屏） | CPK 里被改文件 `FileSize != 16+cs+0x100`（补零了 / 压缩流自相矛盾） |
| **能进但外观没变** | 改错文件（不是该画面的渲染源）/ 选错角色看效果 / 方向搞反 |
| 模型塌成一团 | 骨架 pos 映射不同却直接搬了顶点或 lookupList |
| 某些配色仍是原角色 | 还有别的 body/贴图/CLUT 副本没换（多套服装） |
| 冷启动也无效 | 安装数据没清理，游戏用了旧安装数据 |

**反模式**：
- ✘ 为"保持原 FileSize/ExtractSize"而补零。
- ✘ 为"对齐"去动 chunk 的 size 字段。
- ✘ 用带混淆变量的对照 ISO 下因果结论（如"同时换压缩流又改 CRC 字段"）。
- ✘ 只改 Model 漏改贴图/CLUT（或反之）。

---

## 8. 工作区脚本命名惯例

```
_build_mod.py            换模构建（T + S → _out_<T>bod1_mod.ccs）
_package_mod2.py         压缩+重建CPK+写ISO（FileSize 精确不补零）★成功版
_rt.py / _diff.py        roundtrip 无损校验 / 二进制差异定位
crilayla_official.py     CRILAYLA compress/decompress
_rebuild_cpk.py          CPK 重建（replacements / replacement_extract）
_write_iso.py            ISO 写回（cpk_iso_offset=123207680）
_ccs_lib/ccs_lib/        CCS 读写库（须先修为逐字节无损）
```

---

## 9. 心法

**先证明"编码器无损"，再证明"打包格式自洽"，最后才是换模本身。**
本案卡最久的不是换模，而是打包时多补的 288 个零字节。
