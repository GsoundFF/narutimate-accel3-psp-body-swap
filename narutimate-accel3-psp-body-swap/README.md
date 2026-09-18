# narutimate-accel3-psp-body-swap

> PSP《火影忍者疾风传 究极觉醒3》(ULJS00236) 角色外观替换技能 + 工具链
> Swap a character's **body model / texture / palette** onto another character while **keeping the target's skeleton, animations and moveset**.

[中文](#中文) | [English](#english) · [案例复盘](docs/CASE_STUDY.md) · [踩坑清单](docs/ccs_lib-lossless-fixes.md)

---

## 中文

### 这是什么

一个**技能（Skill）+ 工具链**，用于把**来源角色 S** 的外观（body 模型 / body 贴图 / 调色板）
换到**目标角色 T** 身上，而 **T 的骨架、动作、招式完全保留**。

已在真机验证的案例：**把「天天」(2tew) 的模型换到「香磷」(2kar) 身上** ——
战斗里香磷显示为天天的模型与贴图，但动作/招式仍是香磷自己的。产物 `game_mod2.iso`。

适用平台：PSP《NARUTO -ナルト- 疾风伝 究极觉醒3》（ULJS00236，日版），
以及结构相同的同类作品（**CRILAYLA 压缩的 CPK + CCSF 模型**）。

### 核心原理（两句话）

1. **外科手术式替换**：只在 T 的 `2XXXbod1.ccs` 里替换「外观相关块」
   （body Model 的 meshes、body 贴图、调色板），骨架/动画/名字表/Stream 全部保留 T 的。
2. **CRILAYLA 精确打包**：改完后重压，`FileSize` 必须**精确等于 `16+cs+0x100`**，
   **禁止补零**；`ExtractSize` 用改后 CCS 的真实长度。

### ⚠️ 头号铁律（本项目 99% 的"进不了战斗"都出在这）

CRILAYLA 文件布局固定为：

```
0x00  'CRILAYLA'                      (8B)
0x08  UncompressedSize = us  (u32 LE)   # 解压体长度 = 总解压长度 - 0x100
0x0C  CompressedSize   = cs  (u32 LE)
0x10  压缩位流 (cs 字节)
末尾  原始数据前 0x100 字节
⇒ 文件总长恒等于 16 + cs + 0x100
```

遍历原版 CPK 可验证：**全部 1213 个 CRILAYLA 文件的 `FileSize` 100% 精确等于 `16+cs+0x100`，
没有一个补零。**

如果你为了"保持原 FileSize 不变"而给压缩流补零 → `FileSize ≠ 16+cs+0x100` →
文件自相矛盾 → **游戏拒绝载入，表现就是"选角色进不了战斗"（卡死/黑屏）**。

```python
packed      = crilayla.compress(new_ccs)   # 精确长度
FileSize    = len(packed)                  # == 16+cs+0x100，绝不补零
ExtractSize = len(new_ccs)                 # 改模后通常会变小，这很正常
```

> 血泪教训：曾因补零误判为"游戏对内容做 CRC 完整性校验"，花了大量时间去逆向 CPK 的 CRC 字段
> （试遍 CRC32 全目录 / md5 / sha / FNV / Jenkins / Murmur / xxHash / GF(2) 差分 GCD 判定多项式 CRC
> —— 全部不是）。去掉补零后**一次成功**。详见 [案例复盘](docs/CASE_STUDY.md)。

### 仓库结构

```
.
├── SKILL.md                      # 技能本体（YAML frontmatter + 完整流程）
├── README.md
├── LICENSE
├── docs/
│   ├── CASE_STUDY.md             # 香磷←天天 完整复盘（含错误假设的纠正过程）
│   ├── ccs_lib-lossless-fixes.md # 让 ccsLib 做到"逐字节无损"的 7 处修改
│   └── _src_success_record.txt   # 原始成功记录（中文）
└── tools/
    ├── README.md                 # 各脚本说明
    ├── crilayla_official.py      # CRILAYLA 编解码（compress / decompress）
    ├── _rebuild_cpk.py           # CPK 重建（替换指定文件 + 重算 TOC/ETOC/头部）
    ├── _write_iso.py             # 把重建后的 CPK 写回 ISO 固定偏移
    ├── _list_iso.py              # 列出 ISO 目录项（定位 EBOOT / data.cpk）
    ├── _build_mod.py             # ★ 换模：读 T + S → 输出换好的 T CCS
    ├── _package_mod2.py          # ★ 打包：压缩 + 重建 CPK + 写 ISO（精确长度，不补零）
    ├── _rt.py                    # roundtrip 无损校验
    └── _diff.py                  # 二进制差异定位
```

### 安装为 Skill

把 `SKILL.md` 放到你的技能目录（目录名即技能名）：

- **DSH**：`~/.dsh/skills/narutimate-accel3-psp-body-swap/SKILL.md`
- **Claude Code 等**：对应的 `skills/` 目录，保持 `<skill-name>/SKILL.md` 结构

放好后，Agent 在遇到"把 X 的模型换到 Y 上""换角色外观""这类 MOD 无效果/进战斗卡死"时会自动匹配。

### 快速开始

前置：游戏 ISO、Python 3、以及从 ISO 里抽出的原版 `data.cpk`。

```bash
# 0) 准备依赖（见下节"依赖与授权"）
#    - CCS 读写库（Blender CCS Importer，需先按其说明安装）
#    - 按 docs/ccs_lib-lossless-fixes.md 修成逐字节无损

# 1) 无损自检（必做）：roundtrip(原T)==原字节 且 roundtrip(原S)==原字节
python tools/_rt.py <原T.ccs> _rt_T.ccs && python tools/_diff.py <原T.ccs> _rt_T.ccs
python tools/_rt.py <原S.ccs> _rt_S.ccs && python tools/_diff.py <原S.ccs> _rt_S.ccs

# 2) 换模（在 _build_mod.py 里改好 T/S 的路径与块名后运行）
python tools/_build_mod.py           # → _out_<T>bod1_mod.ccs

# 3) 打包（精确长度、不补零）
python tools/_package_mod2.py        # → game_mod.iso

# 4) 回读验证：FileSize == 16+cs+0x100 且 decompress(...) == 改后 CCS
```

### 测试协议（必须遵守，否则结论全错）

游戏在记忆棒维护**安装数据**：`<memstick>/PSP/SAVEDATA/ULJS00236DATA/`
（`DATA.CPK` + `DATA.BIN` + `PARAM.SFO`）。

- **换 ISO 测试前，先把 `ULJS00236DATA` 改名或删除**，让游戏从**当前加载的 ISO**
  重新安装。否则读到的是上一份安装数据，**连续测多个 ISO 会互相污染**。
- 启动后会弹日文提示「これからインストールを開始します…インストールを開始しますか？」
  → 选「**はい**」。
- **冷启动**模拟器（完全退出再开），不要读战斗中的即时存档。

### 排错速查

| 症状 | 首要怀疑 |
|---|---|
| 选角色**进不了战斗**（卡死/黑屏） | 被改文件的 `FileSize != 16+cs+0x100`（**补零了**） |
| **能进但外观没变** | 改错文件 / 选错角色看效果 / 方向搞反（T、S 弄反） |
| 模型塌成一团 | 两角色骨架 pos 映射不同却直接搬了顶点/lookupList |
| 某配色仍是原角色 | 还有别的 body/贴图/CLUT 副本未换（多套服装） |
| 冷启动也无效 | 安装数据没清理，游戏用了旧安装数据 |

**反模式**：为"保持原尺寸"补零 ✘ ／ 动 chunk 的 size 字段去"对齐" ✘ ／
带混淆变量下因果结论（对照实验一次只改一个变量）✘ ／ 只改 Model 漏改贴图或调色板 ✘

### 依赖与授权

本项目**只包含作者自己编写的脚本与文档**。以下第三方组件**未打包**，请自行获取并遵守其许可：

| 组件 | 用途 | 来源 / 许可 |
|---|---|---|
| **Blender CCS Importer** (`ccs_lib`) | CCS/CCSF 解析与写出 | 作者 Hydra (Al-Hydra) 等，**自有 License（Version 1.1）**；请从上游获取，勿直接搬运 |
| **Kuriimu2** `plugin_criware/CRILAYLA.cs` | `tools/crilayla_official.py` 是其 Python 移植 | Kuriimu2 项目，**GPL-3.0** |

> `tools/crilayla_official.py` 是 Kuriimu2 的衍生作品，受其上游许可约束。
> 若你需要纯 MIT 的仓库，请移除该文件并改用其他实现或直接调用上游。

本项目自身代码与文档采用 **MIT**（见 [LICENSE](LICENSE)）。

### 免责声明

仅供**个人学习、研究与单机娱乐**使用。请勿用于商业用途或在线对战。
请在遵守当地法律与游戏用户协议的前提下使用，并支持正版。

---

## English

### What it is

A **skill + toolchain** for swapping **character S's appearance** (body mesh / body texture /
palette) onto **character T**, **keeping T's skeleton, animations and moveset intact**.

Verified case: **Tenten's (2tew) model onto Karin (2kar)** in
*Naruto Shippuden: Ultimate Ninja Heroes 3* (PSP, ULJS00236) — Karin renders with Tenten's
model and texture while keeping her own moves. Output: `game_mod2.iso`.

### The one rule that matters

Every CRILAYLA file's length is **exactly `16 + cs + 0x100`**. All 1213 original files in the
shipped `data.cpk` satisfy this with **zero padding**.

If you pad the recompressed stream to "preserve the original FileSize", the file becomes
self-inconsistent and **the game refuses to load it — the classic "can't enter battle" hang**.

```python
FileSize    = len(crilayla.compress(new_ccs))   # == 16+cs+0x100, never pad
ExtractSize = len(new_ccs)                      # real decompressed size
```

### Test protocol

Before testing any rebuilt ISO, **rename/delete `<memstick>/PSP/SAVEDATA/ULJS00236DATA`** so the
game reinstalls from the currently loaded ISO — otherwise you are testing stale install data
(and consecutive ISO tests contaminate each other). Answer **はい** at the Japanese install
prompt, and **cold-start** the emulator.

### License

MIT for this project's own code and docs; third-party dependencies (Blender CCS Importer,
Kuriimu2's CRILAYLA) are **not** bundled and remain under their own licenses.
