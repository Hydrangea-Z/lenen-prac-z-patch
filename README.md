# Len'En Prac Z-Patch

把《连缘蛇丛剑》(Le02) 和《连缘灵烈传》(Le03) 改造成**带 F12 覆盖菜单和 hint 标记系统**的练习器。

> An extended practice build for two Len'en Project games — an in-game **F12 overlay menu**
> plus a **hint marker system** you can annotate yourself.

| 游戏 | 版本 |
|---|---|
| 连缘灵烈传 Reactivate majestical imperial (Le03) | **v0.5.11** |
| 连缘蛇丛剑 Earthen Miraculous Sword (Le02) | **v0.7.9** |

改动历史见 [`CHANGELOG.md`](CHANGELOG.md)。

---

## ⚠️ 本仓库不含游戏本体，也不含成品 exe

练习器是**在游戏 exe 上打补丁**得到的，所以这个仓库里**没有任何游戏二进制** ——
没有基底 exe、没有 `Le03prac.exe` / `Le02prac.exe`、也没有汉化版的 exe。
你需要**自己的游戏副本**，然后用 `build.py` 一键生成。

补丁是针对**中文汉化版**的 exe 写的（补丁点是写死的 RVA，换一个版本就会打在错的地方），
所以目前只支持汉化版。`build.py` 会先校验 SHA-256，对不上就直接报错、不会产出坏 exe。

```bash
pip install -r requirements.txt

python build.py le03 --game "D:/Games/Le03/Le03.exe"     # → build/Le03prac.exe
python build.py le02 --game "D:/Games/Le02/Le02.exe"     # → build/Le02prac.exe
```

（`--game` 也可以直接给游戏文件夹，脚本会自己找 `Le03.exe` / `Le02.exe`。）

生成的 exe 放到游戏目录里直接运行即可 —— 它加载的资源都在游戏自己的目录下。

---

## 功能

### F12 覆盖菜单（12 行）

```
No Gameover   Lock Power    Hint          Player +
Capture       Pattern       Hit           Lock Seed
Seed          Frame         Fix X         Fix Y
```

| 行 | 作用 |
|---|---|
| `No Gameover` | 残机耗尽也不结束，命中数会累加 |
| `Lock Power` | 锁住当前火力，弹幕测试时不变 |
| `Hint` | 显示你自己标注的 hint 标记 |
| `Player +` | 在自机判定点画一个十字（**自己开关，不受 Hint 影响**） |
| `Capture` | 按 Z 把当前 boss / 帧号追加到 `<关卡号>.txt` |
| `Pattern` | 只读，显示当前 boss 的 pattern 序号 |
| `Hit` | 只读，本次尝试的命中数 |
| `Lock Seed` | 锁住 RNG 种子（练随机弹用） |
| `Seed` | 种子值，可手动输入 |
| `Frame` | 起始帧（跳阶段用） |
| `Fix X` / `Fix Y` | 微调标记位置，让十字精确压在判定点上 |

菜单用方向键选行、左右改值。`Player +` 的开关状态会记在游戏目录的 `prac.cfg` 里，
下次启动保持。

### hint 标记系统

在游戏目录建一个 `hint\` 文件夹，放 `<关卡号>.txt`（或 `stage N`），
每行一条标记，6 个字段描述「在什么时间、什么位置、画什么」。可以标安全线、
弹幕起点、必须到达的位置等等，`Capture` 行就是用来采集这些坐标的。

**完整格式说明（中英文各一份，含两个游戏各关的 pattern 序号表）：**

- 中文 → [`hint使用说明.md`](hint使用说明.md)
- English → [`hint-manual-EN.md`](hint-manual-EN.md)

`.md` 游戏不会读，放在 `hint\` 里不影响。想在浏览器里看排版版，
可以用 `tools/md2html.py` 转成独立 HTML：

```bash
python tools/md2html.py hint使用说明.md hint使用说明.html "连缘练习器 hint 使用说明"
```

---

## 仓库结构

> 这是一个更大的开发工作区里的**精选子集**：只收录补丁源码、构建工具和文档。
> 一次性调试脚本、历史版本、验收记录、以及游戏本体都没有放进来。
> `.gitignore` 是**白名单** —— 它列出来的就是全部会公开的东西，一眼能看完。

```
build.py                从你自己的游戏 exe 生成练习器（入口）
requirements.txt
LICENSE  README.md  CHANGELOG.md

work/Le03-prac.cea      ★ Le03 的补丁源码
work/Le02-prac.cea      ★ Le02 的补丁源码（由生成脚本产出）
work/Le03-layout.json   补丁里每个变量在内存里的地址
work/Le02-layout.json

tools/cea.py            ★ 核心：汇编 .cea 并给 exe 打补丁
tools/verify_le02.py    Le02 构建的结构校验（build.py 会自动调用）
tools/make_le02_cea.py  从上游源码生成 Le02 的 .cea
tools/patnames.py       提取各关 pattern 名称与编号（写 hint 用）
tools/md2html.py        把 .md 文档转成可离线阅读的独立 HTML

hint使用说明.md           hint 格式说明书（中文）
hint-manual-EN.md         the same manual in English
种子bug分析.md            RNG 种子 bug 的定位与修复
desync分析.md             rep 回放兼容性的排查过程
```

两份分析报告里出现的 `out/`、`baseline/`、`work/_*.py` 等路径属于开发工作区、
不在本仓库内；名字保留原样，方便对照。

---

## 从源码构建（开发用）

```bash
# Le03：基底必须是汉化版 Le03.exe
python tools/cea.py work/Le03-prac.cea <你的 Le03.exe> out/Le03prac.exe \
       --cave-size 0x8000 --json work/Le03-layout.json --lenient

# Le02
python tools/cea.py work/Le02-prac.cea <你的 Le02.exe> out/Le02prac.exe \
       --cave-size 0x8000 --json work/Le02-layout.json --lenient
python tools/verify_le02.py out/Le02prac.exe <你的 Le02.exe>    # 必须 PASS
```

- 基底 SHA-256：Le03 `87563980…40c44a`、Le02 `22bba60f…37cb8c9`
- `--cave-size 0x8000` 必须写（补丁代码和数据塞在一个新增的 section 里）
- `--lenient` 必须加：汉化版 `.rdata` 比原版大 16 字节，会触发一条无害的 `assert()` 告警
- `tools/make_le02_cea.py` 是从上游源码生成 `work/Le02-prac.cea` 的脚本；
  仓库里已经放好了生成结果，所以只构建的话不需要跑它
  （重新生成需要上游作者 BAN 的原始 `.cea`，那个文件不在本仓库里）

---

## 两个游戏的实现差异

- **Le03** 的覆盖层画进游戏的 D3D11 backbuffer；**Le02** 用游戏自己的 `box()`
  画在 640×480 逻辑空间里，所以那边所有尺寸都按**逻辑单位**算。
- Le02 的窗口是 pillarbox（2560×1600 下缩放 3.33×、水平居中偏移 213px）。
- 两个游戏的 F12 菜单都是 12 行，顺序略有不同（见说明书的菜单速查一节）。
- **两个游戏的 pattern 序号表不能互相套用**（比如第 2 关 Le03 有 midboss、Le02 没有）。

---

## 致谢 / Credits

- **游戏本体**：连缘系列 © JynX / トリック・ノンドラン。本仓库不分发游戏本体。
- **上游练习器**：本项目的起点是 **BAN** 先生的 `leprac02` / `leprac03`
  （原生菜单里的 practice 模式、pattern 跳转等）。Le02 的补丁源码是以上游源码为基础生成的。
  仓库里**没有**放入上游的原始源码文件，因为那不是我们的东西。
- **汉化版**：补丁针对中文汉化版的 exe，感谢汉化组。
- 早期移植工作还参考了 Priw8 的 `prac.cea`，以及 leprac / Oscar / RosePenguin100
  在关卡与 pattern 方面的整理。

## 授权 / License

本仓库里**我们自己写的**补丁源码与工具以 MIT 授权发布，见 [`LICENSE`](LICENSE) ——
可以自由使用、修改、转载，保留出处即可。

游戏本体、汉化补丁、上游练习器源码**不在**该授权范围内，它们各自的权利归各自作者所有。
