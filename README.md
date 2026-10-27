# 极简卸载 · JiJian Uninstall

<p align="center"><img src="app/assets/jijian_128.png" width="96" alt="极简卸载图标"></p>

Windows 桌面卸载工具，采用原生窗口控件与简洁侧边栏，支持浅色与深色外观。运行厂商卸载程序，随后重新扫描并审阅可能的残留；文件移入恢复区，注册表仅导出备份。

**开发版本：1.3.1-preview.1。** 预览版仍有功能和安全边界，处理重要数据前请先备份。

## 使用

1. 安装或完整解压便携版，打开“极简卸载”并选择应用。主界面清点只供参考。
2. “演练”只显示官方卸载命令和后续步骤。选择“卸载向导”，选择安全、标准或深入扫描范围。
3. 启动厂商卸载器并在其窗口完成操作。取消、失败、要求重启或无法确认完成时，不进入额外清理。
4. 卸载成功后重新扫描。逐项检查完整路径和匹配依据：**所有候选默认不勾选**，仅勾选确认属于该应用的内容。可以保留全部。
5. 选中的普通文件和目录会移入恢复区；注册表仅导出备份，**原注册表键保持不变**。打开“恢复中心”逐项恢复；文件原位置已有内容时不会覆盖。

厂商卸载器可能自行删除设置或数据，恢复中心不能撤销厂商的操作。恢复区仍占用磁盘空间，不等于释放空间；卸载本程序也不会删除恢复区。

## 扫描与安全边界

- 安全：只复查安装登记明确指向的目录。标准：加上精确应用名的应用数据、快捷方式和注册表候选。深入：加上厂商目录下名称精确匹配的应用子目录；不会把厂商共享根本身列为候选。
- 名称相似不等于归属；尤其是共享目录、多个版本和应用套件，请逐项核对。
- 不自动 SYSTEM 提权或修改 ACL，不手动删除 WindowsApps；拒绝受保护根目录及重解析点。
- 隔离区位于 `%LOCALAPPDATA%\JiJianUninstall\recovery`，目前仅支持同一磁盘移动，单项最多 2 GiB、1 万节点及 64 层；超过限制、跨磁盘或权限不足时保留原项。
- 注册表导入是显式操作，会写回此前备份的值，可能改变现有设置。隔离区记录带完整性检查，但不能抵御同时控制记录和密钥的攻击者。
- 日志位于 `%LOCALAPPDATA%\JiJianUninstall\logs`，含本地应用和路径；分享前请检查。
- 自动扫描不保证覆盖所有应用、数据或商店包。二进制未代码签名。

扫描模式和审阅流程参考 Revo Uninstaller Free 的公开手册与官方文件分析；实现独立，匹配规则不是 Revo 内部算法。见 `docs/revo-evidence.md`。

## 构建与测试

需要 Windows 10/11 x64、Python 3.12，以及构建安装包所需的 Inno Setup 6。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m unittest tests.test_release_engine tests.test_release_scanner tests.test_recovery tests.test_session tests.test_workflow tests.test_wizard tests.test_ui_theme -v
.\.venv\Scripts\python.exe collect_licenses.py
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean build.spec
& "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe" setup.iss
```

`--scan-only` 提供只读扫描诊断。测试使用临时文件和模拟注册表，不卸载本机应用。源码 `app/workflow.py` 负责两阶段流程，`app/recovery.py` 保存和恢复隔离数据。

## 许可证

GPL-3.0，参见 [LICENSE](LICENSE)。第三方依赖许可见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
