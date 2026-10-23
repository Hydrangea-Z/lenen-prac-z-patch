# Len'En Prac Z-Patch

把《连缘无现里》(Le01)、《连缘蛇丛剑》(Le02)、《连缘灵烈传》(Le03) 改造成
**带 F12 覆盖菜单、判定点显示和 hint 标记系统**的练习器。

> An extended practice build for three Len'en Project games — an in-game **F12 overlay menu**,
> a **hitbox overlay**, a **speed control** and a **hint marker system** you can annotate yourself.

| 游戏 | 版本 |
|---|---|
| 连缘灵烈传 Reactivate majestical imperial (Le03) | **v0.12.6** |
| 连缘蛇丛剑 Earthen Miraculous Sword (Le02) | **v0.12.6** |
| 连缘无现里 Brilliant Imperishable (Le01) | **v0.5.6** |

改动历史见 [`CHANGELOG.md`](CHANGELOG.md)，三作的功能与偏移差异见 [`三作差异清单.md`](三作差异清单.md)。

---

## ⚠️ 本仓库不含游戏本体，也不含成品 exe

练习器是**在游戏 exe 上打补丁**得到的，所以这个仓库里**没有任何游戏二进制** ——
没有基底 exe、没有 `Le0Xprac.exe`、也没有汉化版的 exe。
你需要**自己的游戏副本**，然后用 `build.py` 一键生成。

补丁是针对**具体某个版本的 exe** 写的（补丁点是写死的 RVA，换一个版本就会打在错的地方），
所以 `build.py` 会先校验 SHA-256，对不上就直接报错、不会产出坏 exe。

| 游戏 | 基底 | SHA-256 |
|---|---|---|
| Le03 灵烈传 | **日文原版 v1.21a**（窗口标题以 `.ver 1.21a` 结尾） | `955cd8fe…2ca1426` |
| Le03 灵烈传 | 也接受汉化版 v1.20a | `87563980…40c44a` |
| Le02 蛇丛剑 | 中文汉化版 | `22bba60f…37cb8c9` |
| Le01 无现里 | 中文汉化版 | `59875299…44cf36` |

> Le03 的 1.21a 与 1.20a **只差 `.rdata` 里 16 字节的重定位**（链接器把后面的内容和指针
> 整体挪了 16 字节），代码逻辑完全一样，所以同一份补丁对两者都成立。
> 用 1.20a 构建时会有一条 `assert` 不匹配（那是两者唯一的字节差异），
> `build.py` 会自动改用 `--lenient` 放行并打印提示。
> 汉化版的**中文文本是外部文件**（`text_dat/`），不在 exe 里，所以换 exe 不影响语言。

---

## 构建

需要 **Python 3** 和一个 **32 位 MinGW-w64 工具链**（`g++` + `strip`，用于编译两个内嵌 DLL）：

```bash
pip install -r requirements.txt

python build.py le03 --game "D:/Games/Le03/Le03.exe"     # → build/Le03prac.exe
python build.py le02 --game "D:/Games/Le02/Le02.exe"     # → build/Le02prac.exe
python build.py le01 --game "D:/Games/Le01/Le01.exe"     # → build/Le01prac.exe
```

（`--game` 也可以直接给游戏文件夹；`--cxx` / `--strip` 可以指定工具链路径。）

生成的 exe **是单文件**：两个 DLL 已经嵌在里面，首次绘制时释放到 `%TEMP%` 加载，
所以游戏目录里不需要再放任何 `.dll` / `.ini`。放到游戏目录直接运行即可。

---

## 功能

### 判定点显示（hitbox overlay）

把每一颗子弹、每一道激光、Boss 体术的**真实判定范围**画出来。**只读**，不改任何碰撞数据。

- 渲染器是独立编译的 D3D11 程序（[`src/hitbox/`](src/hitbox)），直接画进游戏的场景纹理，
  所以跟游戏同帧、同缩放、同黑边 —— 不会出现「判定圈比弹幕慢一帧」。
- 半径取自**游戏自己的碰撞消费者**：子弹读 `[bullet+0x38]`、激光读两端点、
  Boss 读主副体各自的半径表；不按立绘大小猜。
- 三作的半径公式不同：Le03 是 `table[type] × bullet[+0x30]`，Le01/Le02 只用 `table[type]`。
- 坐标按「等比缩放 + 居中黑边」还原：`s = min(cw/640, ch/480)`，原点 `(32,16)`。

**开启条件**：`prac.cfg` 里 `devmode=1`（且带 code 行，见下），进入关卡后自动出现。

### 加速（Speed 行）

配套 DLL 只做一件事：把 `IDXGISwapChain::Present` 的 sync interval 置 0，
让游戏自己的限速常量（`K = 60000/fps`）真正生效。帧率仍由游戏算，**不影响录像帧号**。

- 60 以下需要 `devmode` 才允许（防止手滑把练习器调成幻灯片）。
- 帧率 > 60 时才关 vsync；60 及以下保持原样。

### F12 覆盖菜单

三作结构一致（灵烈传因为是双自机，多一行 `Lock P2`）：

| 行 | 作用 |
|---|---|
| `No Gameover` | 残机耗尽也不结束 |
| `Lock Power` / `Lock P1` / `Lock P2` | 锁住当前火力；灵烈传分主机 / 副机 |
| `Hint` | 显示你自己标注的 hint 标记（按 Z 进入设置面板） |
| `Lock Seed` / `Seed` | 锁住 RNG 种子、手动输入种子 |
| `Miss` | 只读，本次尝试**真正掉命**的次数 |
| `Speed` | 帧率（15–240，默认 60） |
| `Lock Bomb` | 锁住当前雷数 |
| `Auto Bomb` | 中弹瞬间自动放雷（有雷才触发） |
| `RBoost` | **仅灵烈传**：回放时 LCtrl / LShift 快进 / 慢放 |

菜单用方向键选行、左右改值；所有开关都记在游戏目录的 `prac.cfg` 里，下次启动保持；
删掉该文件即恢复出厂默认。

### 开发者模式

判定显示、60 以下的帧率、以及 `Lock Seed` / `Seed` 两行都归 `devmode` 管。
**只写 `devmode=1` 不够**，`prac.cfg` 里还必须有一行 `code: <口令>`：

```ini
devmode=1
code: <口令在补丁源码里>
```

口令就是 `work/Le0X-prac.cea` 里的 `CODE_STR`。这道门只防「好奇点开配置文件乱改」，
不防读源码的人 —— 仓库里本来就有源码。

### hint 标记系统

在游戏目录建一个 `hint\` 文件夹，放 `<关卡号>.txt`（或 `stage N`），
每行一条标记，6 个字段描述「在什么时间、什么位置、画什么」。

**完整格式说明（中英文各一份，含三作各关的 pattern 序号表）：**

- 中文 → [`hint使用说明.md`](hint使用说明.md)
- English → [`hint-manual-EN.md`](hint-manual-EN.md)

---

## 仓库结构

> 这是一个更大的开发工作区里的**精选子集**：只收录补丁源码、内嵌 DLL 的源码、构建工具和文档。
> 一次性调试脚本、历史版本、验收记录、以及游戏本体都没有放进来。
> `.gitignore` 是**白名单** —— 它列出来的就是全部会公开的东西，一眼能看完。

```
build.py                从你自己的游戏 exe 生成练习器（入口）
requirements.txt
LICENSE  README.md  CHANGELOG.md

work/Le03-prac.cea      ★ Le03 的补丁源码（F12 菜单 + 判定 + 加速 + 锁雷）
work/Le02-prac.cea      ★ Le02 的补丁源码
work/Le01-prac.cea      ★ Le01 的补丁源码

src/hitbox/             判定渲染器（D3D11，编译成 DLL 后嵌进 exe）
  Le01hitbox.cpp  Le02hitbox.cpp  Le03hitbox.cpp  _hbblend.h
src/speed/Le03speed.cpp 加速 DLL（三作共用，只关 vsync）

tools/cea.py            ★ 核心：汇编 .cea 并给 exe 打补丁（支持 incbin/res）
tools/make_text_writable.py  把 .text 设为可写（补丁每帧要写进去）
tools/verify_build.py   构建后的结构校验（build.py 会自动调用）
tools/patnames.py       提取各关 pattern 名称与编号（写 hint 用）
tools/md2html.py        把 .md 文档转成可离线阅读的独立 HTML

hint使用说明.md / hint-manual-EN.md   hint 格式说明书（中 / 英）
种子bug分析.md / desync分析.md        两份排查记录
版本历史.md / 三作差异清单.md          版本与三作差异
```

---

## 从源码构建（开发用）

`build.py` 做四件事，等价于：

```bash
# 1. 编译 + strip 两个内嵌 DLL（32 位）
g++ -m32 -std=c++11 -O2 -shared -static-libgcc -static-libstdc++ \
    src/hitbox/Le03hitbox.cpp -o out/Le03hitbox-v11.dll -Wl,--kill-at -luuid
strip -s out/Le03hitbox-v11.dll -o out/Le03hitbox-v11.stripped.dll

g++ ... src/speed/Le03speed.cpp -o out/Le03speed.dll ...
strip -s out/Le03speed.dll -o out/Le03speed.stripped.dll

# 2. 汇编补丁（.cea 里的 incbin 会读上一步的 stripped DLL）
python tools/cea.py work/Le03-prac.cea <你的 Le03.exe> build/Le03prac.exe \
       --cave-size 0x40000 --json build/Le03prac-layout.json

# 3. .text 必须可写
python tools/make_text_writable.py build/Le03prac.exe

# 4. 结构校验
python tools/verify_build.py build/Le03prac.exe <你的 Le03.exe> --game le03
```

- `--cave-size 0x40000`：补丁代码、两个 DLL 的字节、以及各种缓冲都塞在一个新增的 section 里。
- `--lenient`：只有 1.20a 基底才需要（见上表）。
- 布局：加速 DLL 在 `cave+0x11000`，判定 DLL 在 `cave+0x15000`，其余代码/数据在 0x10000 以下。

---

## 三作的实现差异

- **Le03** 的覆盖层画进游戏的 D3D11 backbuffer；**Le02** 用游戏自己的 `box()` 画在 640×480
  逻辑空间里，所以那边所有尺寸都按**逻辑单位**算；**Le01** 与 Le02 同源但偏移不同。
- Le02 的窗口是 pillarbox（2560×1600 下缩放 3.33×、水平居中偏移 213px）。
- 三作的判定半径公式不同（见上）；**pattern 序号表也不能互相套用**。
- 灵烈传多 `Lock P2` / `RBoost` 两行，且 `Lock Bomb` 只作用于 1P。

---

## 致谢 / Credits

- **游戏本体**：连缘系列 © JynX / トリック・ノンドラン。本仓库不分发游戏本体。
- **上游练习器**：本项目的起点是 **BAN** 先生的 `leprac02` / `leprac03`
  （原生菜单里的 practice 模式、pattern 跳转等）。仓库里**没有**放入上游的原始源码文件。
- **汉化版**：补丁针对中文汉化版的 exe，感谢汉化组。
- 早期移植工作还参考了 Priw8 的 `prac.cea`，以及 leprac / Oscar / RosePenguin100
  在关卡与 pattern 方面的整理。

## 授权 / License

本仓库里**我们自己写的**补丁源码、DLL 源码与工具以 MIT 授权发布，见 [`LICENSE`](LICENSE) ——
可以自由使用、修改、转载，保留出处即可。

游戏本体、汉化补丁、上游练习器源码**不在**该授权范围内，它们各自的权利归各自作者所有。
