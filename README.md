# 极简卸载 · JiJian Uninstall

<p align="center"><img src="app/assets/jijian_128.png" width="96" alt="极简卸载图标"></p>

Windows 桌面卸载工具。先运行应用自己的卸载程序，再清理你明确勾选的残留项。
中文界面、应用搜索、原生图标、卸载预览、执行日志和安装包。

**当前版本：1.0.1-preview.1（预览版）。**

[下载安装版或便携版](https://github.com/SvenRogue/jijian-uninstall/releases) · [报告问题](https://github.com/SvenRogue/jijian-uninstall/issues)

## 使用

1. 从 Releases 下载安装程序，或下载便携 ZIP 后完整解压。便携版需要保留旁边的 `_internal` 目录。
2. 打开“极简卸载”，搜索并选择应用，等待残留清点完成。
3. 查看候选位置，**逐项勾选确认属于这个应用且愿意删除的残留**。候选项默认不勾选。
4. 可先用“演练”预览；确认后选择“卸载并清理”。卸载或删除不可撤销。
5. 官方卸载失败、取消、超时或无法确认完成时，额外清理停止。权限不足的项目保留并记入报告。

勾选控制的是本工具额外执行的清理；厂商官方卸载器可能自行删除安装文件、设置或数据，其行为由厂商决定。

## 功能与边界

- 读取 Windows 控制面板安装登记、PowerShell 返回的已注册 MSIX 应用及可用的 winget 索引。
- 仅按应用名称精确匹配 AppData 候选目录；不按发布者匹配共享目录，不扫描 Documents 作为待删残留。
- 不手动删除 WindowsApps；拒绝系统/共享根目录和重解析点。
- 保留取消勾选的选择；额外清理仅限操作开始时明确选中的计划。
- 区分演练、失败、部分完成和完成，避免把演练标成已卸载。
- 日志存放在 `%LOCALAPPDATA%\JiJianUninstall\logs`。日志含本地应用名称和路径，提交 issue 前请自行检查。
- 预览版禁用自动 SYSTEM 权限清理。需要权限时，可使用界面上的“以管理员重启”；不会绕过 UAC。

**不是所有应用都支持自动卸载。** 自定义安装包可能显示厂商交互窗口；启动器、后台服务、浏览器扩展及应用专有数据不保证能完整识别。商店扫描不可用时会缺少对应条目；不从残留文件夹推造包标识。

## 验证说明

开发阶段曾以“微信开发者工具 2.01.2510290”做真实卸载，安装登记、安装目录、约 405 MB 用户缓存和开始菜单条目均完成清理。该测试暴露出旧引擎问题，**不能作为任意应用均可安全卸载的证明**。

本次预览版针对取消勾选、官方卸载失败、命令解析、目录边界和 UI 后台线程补充隔离测试；测试不会卸载本机应用。公开发布不包含旧的真实卸载脚本或旧版 1.0.0 二进制。

二进制没有代码签名，Windows 可能显示未知发布者。下载后可与 Release 附带的 `SHA256SUMS.txt` 核对。

## 从源码运行 / 构建

环境：Windows 10/11 x64，Python 3.12，Inno Setup 6（仅构建安装包需要）。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py

# 隔离测试（不调用厂商卸载器）
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_release_*.py" -v

# EXE 输出到 dist；安装包输出到 installer
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean build.spec
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" setup.iss
```

开发依赖见 `requirements-dev.txt`。构建文件没有开发者电脑的固定路径。`--scan-only` 提供只读扫描诊断。

## 结构

- `app/scanner.py`：安装项扫描、候选位置和路径拒绝规则。
- `app/engine.py`：官方卸载、冻结清理计划和结果验证。
- `app/ui.py`、`app/theme.py`：PyQt5 桌面界面。
- `app/icon.py`、`app/icons.py`：原创程序图标生成、应用图标提取。
- `tests/test_release_*.py`：无破坏性回归测试。
- `build.spec`、`setup.iss`：EXE 与安装程序构建配置。

## 许可证

项目采用 GPL-3.0，参见 [LICENSE](LICENSE)。PyQt5 / Qt 等第三方组件保持各自许可证，参见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
