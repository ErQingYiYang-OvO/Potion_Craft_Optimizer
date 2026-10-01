# Potion Craft Optimizer

Potion Craft 2.0.2 数据提取、酿药模拟、配方优化与花园生产优化项目。

## 文档入口

- [六类优化目标与实施计划](docs/PLAN.md)
- [酿药机制核对与校准进展](docs/BREWING_AUDIT.md)
- [实验台使用说明](playground/README.md)

当前远端先同步项目文档、界面预览与操作重放示例；引擎、界面源码和提取数据仍在本地项目中。下面的运行命令用于本地完整项目，仅下载当前远端文档不能启动实验台。

所有项目文件位于 `E:\VSCode\VSEnvironment\Potion_Craft_Project`。游戏安装文件按只读方式访问。用户已撤回启动或交互游戏本体的授权，后续仅通过代码、资源及外部资料核对机制。

| 目录 | 内容 |
|---|---|
| `docs/` | 六类优化目标的 [实施计划](docs/PLAN.md) 与 [机制核对记录](docs/BREWING_AUDIT.md) |
| `data/` | 本机 2.0.2 提取的药材、地图、碰撞体、盐和参数 |
| `reference/decompiled/` | 本机游戏脚本 DLL 的反编译结果 |
| `engine/` | GUI 与后续优化器共用的酿药引擎 |
| `optimizer/` | P1/P2 搜索、盐计价、回放校验、容错采样与报告生成 |
| `result/` | 六类问题的可读结果、汇总表与 GUI 操作文件 |
| `playground/` | 浏览器实验台与本地服务 |
| `tools/` | 提取工具、数据校验及其依赖、反编译工具 |
| `tests/` | 操作组合与路径状态回归验证 |

在主目录运行 `python playground/serve.py`，打开 <http://127.0.0.1:8765/>。界面操作通过本地 API 调用 `engine/`，可部分搅拌、倒液、旋转、继续加药、收集药效和导出状态。运行 `python -m unittest discover -s tests -v` 验证操作组合，运行 `python tools/validate_data.py` 核对提取数据。

### 中文界面与原版图标

左侧各功能可独立折叠，浏览器会记住展开状态。药材选择器支持中文搜索、方向键和回车选择，每个选项显示原版药材图片与基础价值。58 种药材、41 种药效的名称取自本机游戏 `LocalizationData` 的 `zh` 列；地图药效圈显示原版对应图标，放大可查看中文名称。状态与操作记录也显示中文，导出文件继续保留稳定的内部标识供引擎重放。

显示资源清单在 `data/ui_manifest.json`，图片在 `playground/assets/`。使用原生 Python 3.13 运行 `tools/extract_ui_assets.py <Potion Craft_Data目录>` 可重新提取；该工具只读取游戏文件。药效图片按照游戏 `Icon.GetSprite` 的纹理、默认颜色、轮廓和划痕层合成。

![中文药材选择器、折叠操作栏与地图药效图标](docs/gui-chinese-icons.png)

引擎仍处于计划 M0 校准阶段，P1/P2 候选搜索已同步开展：普通路径操作、晶体三阶段传送、贤者之盐批次作用、力场修正、矩形越界失败、风箱/倒液冷却、漩涡螺旋移动与传送已接入。支持操作文件导入重放和漩涡观察场景。优化器依赖环境中 107 项回归检查通过，包括逐个核对 99 个漩涡的落点与路径平移、盐计价、拒绝错误配方声明及零药材起点不变。目标/动画朝向已分别入状态，GUI 支持保留日/月盐动画；Unity 帧时序、实际盐粒抵达与输入重叠仍需精确校准，详见机制核对记录。求解器禁用贤者之盐，当前候选与证明范围见结果页面。

## P1 / P2 求解与结果

具体算法和执行目标见 [算法说明](docs/P1_P2_ALGORITHM.md)，结果入口见 [六类结果](result/README.md)。本地服务运行时，可打开 <http://127.0.0.1:8765/result/index.html>，按目标与盐模式筛选配方，点击“载入实验台”从合法起点重放。

搜索需要 NumPy；依赖版本记录在 `optimizer/requirements.txt`。当前计算使用带 NumPy 2.3.5 的本机 Python 运行环境。结果报告与 GUI 服务只依赖标准库。

```text
python -m optimizer.search --objectives P1 P2 --nodes 800 --alternatives 6
python -m optimizer.salt_search --nodes 700 --alternatives 5
python -m optimizer.verify
python -m optimizer.report
python -m optimizer.robustness --effects Healing
```

粗搜索、末段优化及最终回放分开执行。结果明确区分尚未找到、当前最好候选、达到资源下界和实际游戏验证；当前尚未完成全覆盖、完整动作搜索或全局最优证明。禁止用搜索预算耗尽推断目标不可行。
