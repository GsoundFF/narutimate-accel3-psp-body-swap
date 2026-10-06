# 案例复盘：天天 (2tew) 的模型换到香磷 (2kar) 身上

> 游戏：PSP《NARUTO -ナルト- 疾风伝 究极觉醒3》 ULJS00236（日版）
> 结果：**成功** —— 战斗里香磷显示为天天的模型/贴图，骨架/动作/招式仍是香磷的
> 产物：`game_mod2.iso`

---

## 1. 目标与产物

| 项 | 值 |
|---|---|
| 目标 T（保留动作的角色） | 香磷 `2kar` |
| 来源 S（提供外观的角色） | 天天 `2tew` |
| 被改文件 | CPK 内 `32btlchr/2karbod1.ccs` |
| 外观来源文件 | CPK 内 `32btlchr/2tewbod1.ccs` |
| ISO 内 `data.cpk` 偏移 | `123207680` |
| 最终产物 | `game_mod2.iso` |
| 关键中间产物 | `_out_2karbod1_mod.ccs`（634564 字节） |

---

## 2. 最终结论：真凶是「压缩流被补零」

**CRILAYLA 文件的 `FileSize` 必须精确等于 `16 + cs + 0x100`。**

验证方法：遍历原版 `data.cpk` 的全部 CRILAYLA 文件：

```
files with FileSize == exact CRILAYLA len : 1213
files with FileSize != exact (padding)    : 0
```

**1213/1213 全部精确，零补零。**

而我之前的做法是：
1. 用自己的压缩器重压 → 得到 399348 字节（**比原厂的 399636 更短**）；
2. 为了"保持原 FileSize = 399636 不变"，**补了 288 个零字节**；
3. 结果 `FileSize(399636) ≠ 16+cs+0x100(399348)` → **文件自相矛盾** → 游戏拒绝载入；
4. 症状：**选香磷进不了战斗**（卡死）。

修复：

```python
packed      = crilayla.compress(mod)   # 399308B（精确）
FileSize    = len(packed)              # = 16+cs+0x100
ExtractSize = len(mod)                 # 634564（改模后变小，正常）
```

修完**一次通过**。

---

## 3. 走过的弯路（重要：错误假设是怎么产生的）

### 3.1 最初的观察

| ISO | 2karbod1 内容 | 打包方式 | 结果 |
|---|---|---|---|
| `control` | **原版字节**（未重压） | 重建 CPK | ✅ 能进战斗 |
| `mod` / `black` / `flip` / `flipB` | 重压 + **补零** | 重建 CPK | ❌ 进不了战斗 |

### 3.2 错误假设：游戏对内容做 CRC 完整性校验

当时的推理是："内容一字不改、只是重新打包"的 `control` 能进，
而所有"改了内容"的版本都进不去 ⇒ 游戏在按内容做校验。

为了坐实，还专门做了一个 `flipB`（**内容与原版完全相同**、但把 CPK TOC 里的 CRC 字段清零）
——它也进不去，于是得出"**CRC 字段就是关卡**"的结论。

### 3.3 这个推理错在哪

`control` 用的是**原版未重压的压缩字节**（长度天然精确），
而 `flipB` **既重压了（补零）又改了 CRC 字段** —— **一次改了两个变量**。

所以 `flipB` 的失败其实来自"补零"，与 CRC 字段毫无关系。
**用带混淆变量的对照实验下因果结论，是本次最大的时间浪费。**

### 3.4 白花的功夫

在"CRC 校验"的错误前提下，尝试逆向 CPK TOC 的 CRC 字段：

- 标准 CRC-32 全目录（zlib / MPEG-2 / BZIP2 / POSIX / JAMCRC / CRC-32C / CRC-32K / Q / D / XFER …）—— 不匹配
- md5 / sha1 / sha256 各种截断与字节序 —— 不匹配
- FNV-1 / FNV-1a / Jenkins / djb2 / sdbm / MurmurHash3 / xxHash32 —— 不匹配
- 简单和式 / Fletcher / Adler —— 不匹配
- **GF(2) 差分 GCD**（判断是否为任意多项式 CRC：若为 CRC，则
  `Δm·x³² + Δc` 必有公因式）—— GCD = 1，**证明它不是多项式 CRC**

结论：那是游戏私有的、无公开资料的自定义哈希。
**但如果一开始就去核对"FileSize 是否等于 16+cs+0x100"这个不变量，
几秒钟就能找到真因。**

---

## 4. 换模本身（这部分一直是正确的）

在香磷 `2karbod1.ccs` 上只替换"外观相关块"：

| 步骤 | 内容 |
|---|---|
| (1) body Model | 香磷 `MDL_2kar00t0 body`(idx 1710) 的 `meshes` ← 天天 `MDL_2tew00t0 body`(idx 2273)<br>每个 mesh 的 `materialIndex` 由 2274 → **1711**（香磷 `MAT_clut`）<br>`lookupList` ← 天天的（20 项） |
| (2) body 贴图 | 香磷 `TEX_2karbody`(idx 1712) 的 `textureData` ← 天天 `TEX_2tewbody`(idx 2275) |
| (3) 调色板 | 香磷 body CLUT(1744) 的 `paletteData` ← 天天 body CLUT(2356) |
| (4) 其余 | 骨架、动画、Material、名字表、Stream、其他 Model **全部保留香磷的** |

两者 body 均为 `DeformableMesh`、17 个 mesh、`vertexScale = 256.0`，
贴图同为 Indexed8(`0x13`) 128×256。

### 为什么跨骨架能直接搬顶点数据

顶点里的 boneID 是 **`Clump.boneIndices` 数组的下标（pos 号）**，不是骨名表编号。
香磷与天天的 **pos → 骨名映射完全一致**（各 25 骨；`pos0=trall`根、`pos3=pelvis`、
`pos13=head`、`pos23=r finger0`、`pos24=body`…），
所以来源的顶点在目标骨架上语义相同 ⇒ **顶点数据一个字节都不用改**。

> 若两角色骨架结构不同，则必须按骨名重映射 `lookupList`
> （并注意左右同名骨要按"第 N 个同名骨"配对，否则模型会塌成一团）。

### 自检结果

```
body mesh 顶点数 == 天天 [18,38,8,30,14,6,78,829,26,24,70,4,78,61,28,24,687]   ✔
TEX_2karbody md5 == 56455bcf464ff043…（== 天天 body 贴图）                      ✔
全部 mesh.materialIndex == 1711（香磷 MAT_clut）                                ✔
与香磷原文件的字节差异只落在 body Model 区 + 贴图/CLUT 区                        ✔
块数 3211，结构与香磷一致                                                        ✔
```

---

## 5. 前提工程：ccsLib 必须逐字节无损

先把读写器修到 `roundtrip(原香磷) == 原字节` 且 `roundtrip(原天天) == 原字节`，
才敢信任后续任何字节级结论。共 7 处修改，详见
[ccs_lib-lossless-fixes.md](ccs_lib-lossless-fixes.md)。

其中与"写出字节"最相关的一条：写出时**保留 chunk 的原始 size 字段**
（原 Model 1710 的 size 字段比内容多算 `0xFF` 单位 = 1020 字节；游戏不按 size 字段遍历块）。

---

## 6. 测试协议（不遵守就会得出错误结论）

游戏在记忆棒维护**安装数据**：
`<memstick>/PSP/SAVEDATA/ULJS00236DATA/`
（`DATA.CPK` 301418032B + `DATA.BIN` 1040B + `PARAM.SFO`）。

1. **换 ISO 测试前，必须把 `ULJS00236DATA` 改名或删除**，
   让游戏从**当前加载的 ISO** 重新安装数据；
2. 启动后弹日文提示
   「これからインストールを開始します…インストールを開始しますか？」→ 选「**はい**」；
3. **冷启动**模拟器（完全退出再开），不要读战斗中的即时存档。

> 本次因为"连续测多个 ISO 之间不清理安装数据"，
> 导致后一个 ISO 实际没有生效（游戏仍在用前一份安装数据），
> **测试结果被污染**，进一步误导了判断。

---

## 7. 三条通用心法

1. **先证明编码器无损 → 再证明打包格式自洽 → 最后才是换模本身。**
   本次卡最久的不是换模，而是打包时多补的 288 个零字节。
2. **对照实验一次只改一个变量。**
   `flipB` 同时改了压缩流和 CRC 字段，结论因此完全错误。
3. **优先核对不变量。** 与其去逆向一个未知哈希，不如先验证
   "原版所有文件是否都满足 `FileSize == 16+cs+0x100`" —— 一条遍历就能定位真因。
