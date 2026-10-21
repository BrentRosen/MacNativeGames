# Button icons row in the Options menu

[English](#english) | [中文](#chinese)

<a id="english"></a>
## English

System > Options gets a **Button icons** row below "Swap jump controls": **Switch**, **Xbox**, **PlayStation**, **Keyboard** or **Automatic**. It
picks the icons the game draws in its button prompts (A/B/X/Y, L/R, ZL/ZR, +/− and the d-pad). The game loads its icon font once, so a
change shows from the next start; the row's description says so in every language the game has. Xbox and PlayStation
icons follow the default face-button mapping by position (the right button is A); with `TOTK_FACE_BUTTONS=label` or
face buttons changed in `controls.txt` they no longer match.

Nothing of the game is in the repository. `build_app.py` makes the row from the player's own RomFS
(`games/totk/scripts/make_controls_option.py`, into `extracted/<version>/romfs-controls`), and the runtime serves it as
a RomFS overlay (`runtime/romfs.c`, `controls_init`). No game code is patched.

### How the menu works

Checked on 1.0.0 and 1.4.3 (code and data). 1.1.2 and 1.2.1 lie between them; the build makes the row for them too, and
if its checks refuse their data the app is built without it.

- **Rows are data.** `UI/OptionSetTable/OptionSetTable.game__ui__OptionSetTable.bgyml` in `Pack/Bootup.Nin_NX_NVN.pack`
  lists each row: `OptionType`, `ButtonType` (Toggle, Selection, Button, Separator) and the `ChoiceType` names. The
  screen (`UISystemOptionScreen`) clones one template row per type from the layout `SystemOption_00`, so the layout is
  unchanged.
- **A free option type.** `OptionType` is an enum in the code: None, IsUseAmiibo, IsCameraUpDownReverse,
  IsCameraRightLeftReverse, CameraRotateSpeed, IsUseGyro, IsChangeJumpButton, **IsControlStickUpDownReverse** (7),
  IsLockMiniMapUpper, … Type 7 is in no table, has no saved value and no text, and no code refers to it by hash. The row
  uses it.
- **Text.** `LayoutMsg/SystemOption_00.msbt` in each `Mals/*.sarc`: the name is `10NN`, the description `00NN`
  (NN = type − 1, here `1006` and `0006`), the choices `10NN_VV` in table order.
- **The value** is the member of the GameData struct `OptionData` named after the type: the screen hashes
  `OptionData` (murmur3, `0x834d9d9e`) and the member name. A Selection value is an Enum whose values are murmur3 hashes
  of the `ChoiceType` names, so the row reuses five existing names: `Normal`, `Pro`, `Dark`, `Slow`, `Fast` stand for Switch, Xbox,
  PlayStation, Keyboard, Automatic. The default is Automatic; existing saved choices keep their meanings. `GameData/GameDataList` gets the member and the Enum `OptionData.IsControlStickUpDownReverse`
  (`0xce2cee8e`) with `SaveFileIndex` 1, which is `option.sav`.
- **Saves.** `option.sav` is a 0x20-byte header (magic `0x01020304`, the GameData revision, the data offset at +8), a
  marker per save type, (hash, value) pairs and an end marker. The game reads it by hash (`main+0xa7c4b0` in 1.4.3): an
  entry its list lacks is skipped, a missing one keeps its default, an Enum value outside its list is ignored. Saves
  therefore load with and without the row. The list's `MetaData` holds the file's size and offsets; one Enum adds
  8 bytes (option.sav 880 → 888, its data offset 632 → 640, `AllDataSaveOffset`/`AllDataSaveSize` + 8). The script
  checks its size model against the original numbers before it changes them.
- **Memory budgets.** `System/Resource/ResourceSizeTable` sizes the game's buffers. The table's entry also budgets the
  objects built from it: 8,416 bytes for 16 rows in 1.4.3, and a 17th row's allocation fails (`main+0xed735c` returns
  null) unless it is raised. The script raises the entries of every file it changes by their growth, keeping the
  original allowance, and gives the table twice the average allowance of a row.
- **Icons.** The prompt icons are glyphs U+E040–U+E068 of `scft/External.bfotf` in `Font/Font.Nin_NX_NVN.bfarc`
  (`make_button_icons.py`). An archive is written for the Xbox, PlayStation and Keyboard styles. At start the runtime reads
  the row's value from `option.sav` (no save or no value: Automatic) and serves `icons-<style>` (nothing for Switch).
- **Choice names are plain text.** The choice box (`PaOptionBtnLevel_00`, font `NormalS_00`) draws with a different font
  stack per language: Nintendo's text font in most, the system's Chinese and Korean fonts in the others. None has room
  for extra icons, so the names are the consoles' names.

### Files

`extracted/<version>/romfs-controls/menu` holds the option table (in the Bootup pack), the GameData list, the size table
and every language's messages; `icons-xbox`, `icons-playstation` and `icons-keyboard` hold the font archive. Each folder
has a `manifest.tsv` the runtime checks at start, like every overlay. `TOTK_ROMFS_CONTROLS=0` leaves the row out.

Every document is rewritten with formats that give back the original bytes when nothing changes (BYML, MSBT, SARC in
`scripts/nx_formats.py`); the script stops otherwise. The game's settings parser does not accept shared BYML nodes where
its files have none, so the writer shares exactly what the original shares.

### Automatic and Controls pictures

Automatic uses the first extended controller reported by GameController at startup: DualSense/DualShock → PlayStation,
Nintendo/Joy-Con → Switch, Xbox and generic/MFi pads → Xbox, no extended controller → Keyboard. Hot-plugging is reflected
at the next launch. Manual styles override detection. Keyboard prompts match the built-in keyboard bindings.

`controller_pictures.py` draws original, flat Xbox and DualShock 4 diagrams with grey fills and dark outlines,
matching the game's Controls-screen illustration style. No product photos, third-party mod art or downloads are used.
It replaces the twelve controller and shadow textures in the player's `timg/__Combined.bntx`, inside the Common UI
archive. BC3 preserves the flat fills and transparency without changing any texture's storage size. All six controller
states use the selected diagram; Switch retains the game's original artwork.

The game's cream connector lines, endpoint dots and rounded diamonds remain visible. `PaSystemController_00.bflyt`
is reanchored to coordinates shared with each drawing, and the corresponding BFLAN transform keys are updated so
console, Pro and handheld animation states cannot restore Switch-specific endpoints. Panels and localized text move
together to keep the upper connector routes clear. For PlayStation, the complete d-pad and movement groups exchange
rows to follow the DualShock layout without crossed lines. Their horse-mode position and compensation curves exchange
together, preserving expansion and stable endpoints. Keyboard keeps its existing diagram without controller callouts.
Pictures and prompts use the same restart rule. Fixed-image tutorial prompts elsewhere retain their original artwork.

`pictures-<style>` holds the original-UI variant; `pictures-<style>-patched` composes with the sibling `romfs-patches`
archive. Each records its source archive hash in `source.tsv`. Runtime installs the composed picture archive only when
that source matches the UI already selected, preserving the capture timing fixes. If a custom UI overlay has no matching
variant, its artwork is retained and a log explains why; menu and font styles still work. To generate a matching custom
variant, pass `--base-ui <patched Common blarc.zs>` to `make_controls_option.py`. Build cache fingerprints include this
script and the default patched UI source. A mod replacing the selected picture archive disables the row for that launch.

### With player mods

A mod in `mods/<version>` that replaces any of these files (the option table's pack, the GameData list, a message
archive, the size table or the icon font) turns the row off for that start, and the log says so; the mod is loaded as
before. `make_button_icons.py` also writes the PlayStation style for a mod folder (`--style playstation`).

<a id="chinese"></a>
## 中文

“系统 > 选项”在“交换跳跃键”下面多一行 **按键图标**：**Switch**、**Xbox**、**PlayStation**、**键盘** 或 **自动**，决定游戏按键提示里画哪种
图标（A/B/X/Y、L/R、ZL/ZR、+/− 和十字键）。游戏只在启动时读一次图标字体，所以下次启动才生效；这一行的说明文字（游戏的每种语言）也写明了。Xbox 和 PlayStation 图标按默认的按位置映射
（右边的键是 A）；用了 `TOTK_FACE_BUTTONS=label` 或在 `controls.txt` 改了面键就对不上。

仓库不含任何游戏内容。`build_app.py` 用玩家自己的 RomFS 生成这一行（`games/totk/scripts/make_controls_option.py`，输出到
`extracted/<版本>/romfs-controls`），运行时作为 RomFS 覆盖层提供（`runtime/romfs.c` 的 `controls_init`）。不改任何游戏代码。

### 选项菜单的原理

在 1.0.0 和 1.4.3 上核对过（代码和数据）。1.1.2、1.2.1 介于两者之间；构建时同样生成，脚本的检查不通过就不带这一行打包。

- **行是数据。** `Pack/Bootup.Nin_NX_NVN.pack` 里的 `UI/OptionSetTable/OptionSetTable.game__ui__OptionSetTable.bgyml`
  列出每一行的 `OptionType`、`ButtonType`（Toggle、Selection、Button、Separator）和 `ChoiceType` 名字。界面
  （`UISystemOptionScreen`）按类型从布局 `SystemOption_00` 复制模板行，布局不用改。
- **空闲的选项类型。** `OptionType` 是代码里的枚举，第 7 项 **IsControlStickUpDownReverse** 不在任何表里，没有存档值、没有
  文字，也没有代码按哈希引用它。这一行用它。
- **文字。** 各 `Mals/*.sarc` 里的 `LayoutMsg/SystemOption_00.msbt`：名字 `10NN`、说明 `00NN`（NN = 类型 − 1，即 `1006`、
  `0006`），选项 `10NN_VV`。
- **值** 存在 GameData 结构 `OptionData` 里以类型命名的成员：界面对 `OptionData`（murmur3 `0x834d9d9e`）和成员名求哈希。
  Selection 的值是 Enum，取值是 `ChoiceType` 名字的 murmur3，所以借用五个现有名字：`Normal`、`Pro`、`Dark`、`Slow`、`Fast` 分别代表
  Switch、Xbox、PlayStation、键盘、自动（默认）。`GameData/GameDataList` 增加这个成员和 Enum `OptionData.IsControlStickUpDownReverse`
  （`0xce2cee8e`），`SaveFileIndex` 1 即 `option.sav`。
- **存档。** `option.sav` 是 0x20 字节的头（魔数 `0x01020304`、GameData 版本号、+8 处的数据偏移）、每种类型一个标记、
  （哈希，值）对和结束标记。游戏按哈希读取（1.4.3 的 `main+0xa7c4b0`）：列表里没有的条目跳过，缺的条目保持默认，不在取值
  列表里的 Enum 值忽略。所以有没有这一行，存档都能读。列表的 `MetaData` 记着文件大小和偏移，多一个 Enum 就多 8 字节
  （option.sav 880 → 888，数据偏移 632 → 640，`AllDataSaveOffset`/`AllDataSaveSize` + 8）。脚本先用原始数字核对大小模型，
  再修改。
- **内存预算。** `System/Resource/ResourceSizeTable` 决定游戏的缓冲区大小。选项表那一项还包括由它生成的对象：1.4.3 里
  16 行共 8,416 字节，不加大的话第 17 行分配失败（`main+0xed735c` 返回空指针）。脚本把改动过的每个文件按增长量加大，
  保留原有余量，并给选项表加一行平均预算的两倍。
- **图标。** 提示图标是 `Font/Font.Nin_NX_NVN.bfarc` 里 `scft/External.bfotf` 的 U+E040–U+E068 字形
  （`make_button_icons.py`）。为 Xbox、PlayStation 和键盘风格各写一个字体包。启动时运行时从 `option.sav` 读这一行的值（没有存档或
  没有值：自动），提供 `icons-<风格>`（Switch 不需要）。
- **选项名是纯文字。** 选项框（`PaOptionBtnLevel_00`，字体 `NormalS_00`）在不同语言用不同的字体组合：多数语言是任天堂的
  正文字体，中文和韩文是系统字体，都放不下额外的图标，所以选项名就是主机名。

### 文件

`extracted/<版本>/romfs-controls/menu`：选项表（在 Bootup 包里）、GameData 列表、大小表和各语言文字；`icons-xbox`、
`icons-playstation`、`icons-keyboard`：字体包。每个目录都有运行时启动时核对的 `manifest.tsv`。`TOTK_ROMFS_CONTROLS=0` 不加载
这一行。

所有文件都用“不改内容就逐字节还原”的格式重写（`scripts/nx_formats.py` 的 BYML、MSBT、SARC），否则脚本停止。游戏的设置
解析器不接受原文件里没有的共享 BYML 节点，所以写出时只共享原文件共享的部分。

自动模式（默认）在启动时检测第一个手柄：DualSense/DualShock 显示 PlayStation，任天堂手柄显示 Switch，Xbox 或通用手柄显示 Xbox，没有手柄显示键盘。手动选择优先，重新启动后生效。控制说明画面也会使用相应的手柄或键盘图片（Xbox 和 DualShock 4 使用与游戏界面一致的扁平灰色示意图，并保留准确连接的引导线）；已有存档的选择保持不变。自定义 UI 覆盖层没有匹配的图片版本时保留其原有图片，日志会说明原因。

### 和玩家模组一起用

`mods/<版本>` 里的模组如果替换了其中任何文件（选项表所在的包、GameData 列表、文字包、大小表或图标字体），这次启动就不加载
这一行，日志里写明原因；模组照常加载。`make_button_icons.py` 也能给模组目录生成 PlayStation 风格（`--style playstation`）。
