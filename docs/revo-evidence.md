# Revo Free 对照分析：证据、未知范围与独立设计

分析日期：2026-10-27。目标是借助 REA 分析官方发布物，为极简卸载的流程与恢复能力提供参考。本文区分官方说明、发布物中的资源、REA 原生分析和本项目的设计建议；不把产品宣传或字符串当作内部算法已经还原的证明。

## 样本来源与身份

样本来自 [Revo Free 官方产品页](https://www.revouninstaller.com/products/revo-uninstaller-free/)，页面明确链接 [官方便携 ZIP](https://revouninstaller.b-cdn.net/ruf272/RevoUninstaller_Portable.zip)。产品页当日显示 2.7.2。没有使用镜像、破解或第三方改包。

| 对象 | 身份 / SHA-256 |
| --- | --- |
| `RevoUninstaller_Portable.zip` | `a0a1a35fcba86dc6773b4d511a172ed7ab3f0082ac298074462b83d7ed2bd424` |
| ZIP 内 `x64/RevoUn.exe` | 22,093,112 bytes；文件/产品版本 `2.7.2.0`；`e7ff6d4d3f42028f83ee63b495e2c9d80a773045dd1891f2e617b0d433945879` |
| ZIP 内免费版帮助 PDF | 34 页；`f11a0150d87ef69a5509348e91f761358b0bd8c3bbefd8c8e7686b4dfb792dee` |

Windows `Get-AuthenticodeSignature` 对主 EXE 返回 **Valid**，签发主体是 **VS REVO GROUP OOD**。这是 Windows Authenticode 的补充证据，并非 REA `inspect-signature` 对 Windows 签名验证的结果。

样本、下载来源 JSON、原始 REA JSON 和提取的资料只保存在本机 `%TEMP%\jijian-revo-analysis`，不进入源码仓库。没有分发第三方 EXE、手册、翻译资源或私人安装列表截图。

此次没有运行 Revo 目标 EXE，也没有执行实际卸载、删除、系统还原点创建或恢复。Ghidra 分析进程会运行，但它读取的是固定哈希的样本，并不执行样本逻辑。下面的恢复流程证据因此属于静态分析或文档说明，不是恢复成功的实测。

## 工具与复现范围

使用已安装的 `rea-agents 6.1.0`。初始没有可用的 Ghidra/Hopper/IDA。随后用户明确授权安装缺失原生引擎及必要 Java，因此从官方 GitHub Release 下载了 REA 验证的 Ghidra 版本，而非不兼容的最新 12.2。

| 本地分析工具 | 来源 / 校验 |
| --- | --- |
| Ghidra 12.1.4 | [NSA 官方 Release](https://github.com/NationalSecurityAgency/ghidra/releases/tag/Ghidra_12.1.4_build)；569,649,598 bytes；SHA-256 `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`，与官方 API asset digest 相同 |
| Temurin JDK 21.0.9+10 Windows x64 ZIP | [Adoptium 官方 Release](https://github.com/adoptium/temurin21-binaries/releases/tag/jdk-21.0.9%2B10)；204,962,060 bytes；SHA-256 `1c67df516e9795c0b09f5714bfe151da2e3cc988082042f5bbb60d75e4e63fb5`，与官方 API asset digest 相同 |

Ghidra 仅解压到 `E:\Tools\Ghidra\ghidra_12.1.4_PUBLIC`，JDK 仅解压到 `E:\Tools\Java\jdk-21.0.9+10`。没有改系统 PATH、安装 MCP 配置或重启 Harness。分析时只设置当前进程环境变量。

关键命令（从官方 ZIP 解压后的同一文件开始）：

```powershell
$d = Join-Path $env:TEMP 'jijian-revo-analysis'
$x = Join-Path $d 'sample\RevoUninstaller_Portable\x64\RevoUn.exe'
rea-agents inspect-artifact $x --format json --full-output
rea-agents inspect-binary-layout $x --format json --full-output
rea-agents inspect-signature $x --format json --full-output
Get-FileHash $x -Algorithm SHA256
Get-AuthenticodeSignature $x

$env:GHIDRA_INSTALL_DIR = 'E:\Tools\Ghidra\ghidra_12.1.4_PUBLIC'
$env:JAVA_HOME = 'E:\Tools\Java\jdk-21.0.9+10'
$env:PATH = "$env:JAVA_HOME\bin;$env:PATH"
rea-agents analyze $x --provider ghidra --snapshot "$d\revo-x64-snapshot.json" --format json --full-output
```

### 独立 REA 检查的实际结果

| 实际调用 / 原始 JSON 文件 | 观察 | 不可据此断言 |
| --- | --- | --- |
| `inspect-artifact` → `rea-artifact.json` | 成功生成 PE 发布物身份、长度与 SHA-256；Evidence ID `ev_76c85396fd7adf52579c1e1b3ffd1f4d39f098dffb0a545ae0428e91daa41011` | 架构字段是 null，不能冒称此命令恢复了 x64 代码或扫描算法 |
| `inspect-binary-layout` → `rea-layout.json` | 返回 `capability_unavailable`，当前独立 layout provider 是 Linux x64 的 `pwntools-elf` | JSON 外层 `ok:true` 不代表 PE layout 成功；不能把这次调用算作有效 PE 段分析 |
| 初始 `inspect-signature` → `rea-signature.json` | 在尚未设置引擎时返回 `provider_unavailable`，CLI 帮助定位为 Mach-O/app 签名工具 | 不能声称 REA 此调用验证了 Windows Authenticode |
| 原生 UI 观察探测 → `rea-native-ui-probe.json`、`rea-native-ui-capability.json` | 无有效 UI 捕获。安装版本的 `NativeUiObservation` 实现只接受已运行 Mach-O 目标和准确 PID/window ID | 没有 REA Windows UI 截图或实际点击流程证据；不声称观察了清理或恢复的运行结果 |

REA Windows Ghidra P0 只接受受支持的本地 native PE application；数据库变更、DLL/托管分析等有独立限制。Ghidra 反编译结果是推断的伪代码，不是原始源码。

### 已完成的 Ghidra 原生分析

这部分是实际 native PE 分析，不能和上面的独立 ELF-only layout 失败混为一谈。

| 实际结果 | REA 原始证据 |
| --- | --- |
| 主程序确认 `pe / x86_64`，上游分析配置为 Ghidra `12.1.4`，默认自动分析完成后返回；耗时 280.087 秒 | `rea-native-overview.json`；Evidence ID `ev_47c3da2e5264f5ea74ee0ef9a561e1acbf16a3575ef271b9e60c3d8463b00f0e` |
| 主程序 Ghidra 视图有 10 个 memory segments（包括 Headers 和分析器生成的 `tdb`，不能说成 10 个 PE 原始节）；36,139 个 procedure 项，10,965 个已定义字符串 | 同上。procedure 项包含分析器识别的函数、外部函数/跳板，不等于原始源码函数数目 |
| `.text` 地址 `[0x140001000, 0x1406ad000)`，6,995,968 bytes；`.rsrc` 地址 `[0x1409ae000, 0x141523c00)`，12,016,640 bytes | 同上；范围终点是 exclusive，不据资源段大小推断匹配数据库 |
| 同包 `x64/RevoSrp.exe` 的独立 Ghidra 分析成功，`pe / x86_64`，1,452 个 procedure 项、619 个已定义字符串，耗时 29.710 秒 | `rea-srp-overview.json`；Evidence ID `ev_bf08242be507c32b54b49b548ec18fa57d7353cbf7799fe67dcf6db7ad44650d`；样本 SHA-256 `10c7163dcde61ae176d68130b2665be75f61aede5638b84734648f93563b36c8` |

仅有 native overview 不能证明已经还原扫描算法、模式分支或恢复逻辑。下文对 Safe/Moderate/Advanced 的流程解释仍以官方手册和发布物资源为依据。

一次临时 REA stdio 会话读取了当前实际 `tools/list` 架构，再对同一固定哈希 PE 调用 `open_binary`、`search_procedures`、`search_strings` 和 `close_binary`；没有改 Harness 的 MCP 注册。相关证据如下：

| 原生查询命中 | 证据与解释 |
| --- | --- |
| `ADVAPI32.DLL::RegDeleteKeyExW` (`EXTERNAL:0x28`)、`RegEnumKeyExW` (`EXTERNAL:0x35`)、`RegDeleteKeyW` (`EXTERNAL:0x38`)、`RegDeleteValueW` (`EXTERNAL:0x4b`) | `main-native-procedures.json`；Evidence ID `ev_b9d6c452c4ad3b68b485545ac03e0894957e596a188e2f8659e009ae24211d5d`。这证明 Ghidra 识别到相关导入符号，不能单凭导入确认何时执行、扫描规则或删除目标所有权 |
| `SHELL32.DLL::SHFileOperationW` (`EXTERNAL:0x2f5`)、`KERNEL32.DLL::CreateProcessW` (`EXTERNAL:0x10f`)、`SHELL32.DLL::ShellExecuteExW` (`EXTERNAL:0x2f0`) | 同上。`EXTERNAL` 地址是分析器的外部地址空间，不能当作原始文件偏移或直接执行地址；只根据 API 名也无法证明某次操作进入回收站 |
| `Uninstaller\\RegExclude` 位于 `0x1407d3d70` | `main-native-strings.json`；Evidence ID `ev_45244dc7b5617c7a331d9e40f430e37ddf6c06ce4790fc65c07093fc53334df8`。这是映射到 PE 数据的设置名，与手册排除规则说明相符，不是私有排除表已经恢复 |
| 还原点辅助程序命令模板位于 `0x140814a60`，包含 `RevoSrp.exe -SRP -t=1 -name=` | 同上。证明主程序含独立帮助程序的命令模板，但不证明它在某次运行被调用或还原点创建成功 |
| Safe / Moderate / Advanced 及回收站说明也在 Ghidra 已定义字符串中 | 同上；与独立语言资源吻合。字符串仍不能证明对应算法的实际实现 |

原始查询形状（`search_procedures` 返回字段为 `value/address`，不是 `name/address`）：

```json
{"name":"search_procedures","arguments":{"pattern":"SHFileOperation|RegDelete|RegEnum|SRSetRestore|ShellExecute|CreateProcess","mode":"regex","case_sensitive":false}}
```

主程序函数调用点的第一版临时客户端误按 `name` 字段读取结果，所以没有执行其计划中的调用者/函数请求。此错误已保留在原始记录中；不能把已跳过的函数请求声称成成功的反编译结果。为控制总分析时间，不重新导入主程序追求私有扫描规则。

## 可验证的工作流

下表的手册指官方 ZIP 内附带的 Free 用户指南，页码为 PDF 页码；资源指同包 `lang/english.ini` 的数值 ID。完整提取文件仅存 TEMP。

| 功能 / 主张 | 官方文档证据 | 发布物资源证据 | 结论与未知范围 |
| --- | --- | --- | --- |
| 厂商卸载后再扫描 | 产品页 Uninstaller 段、手册 p8：内置卸载器结束后用户点 Scan | 4224、4240 指明等待厂商卸载结束；4223/4225 区分运行卸载器与卸载后扫描 | 确认用户可理解的分阶段流程；未证明内部进程等待/退出码处理算法 |
| 扫描模式 | 手册 p8：Safe、Moderate、Advanced，速度与范围递进 | 4235–4237 同名描述；4234 还有仅运行内置卸载器 | Free 手册描述三档扫描深度；p31 的 only built-in 是单独选项，不能据共享资源断言当前界面有四个同级单选框 |
| Safe 的具体匹配规则 | 手册只说扫描可安全删除的注册表和磁盘残留 | 4235 同样是自然语言说明 | 具体词法、相似度、关联评分、路径集合均未知；本项目的“精确产品名”是自己的规则 |
| 注册表树与删除对象 | 手册 p9：粗体是候选删除节点，非粗体祖先是上下文；即便 Select All，也仅删勾选的粗体对象 | 4244/4246：注册表结果与“只删除勾选粗体项及其子项”说明 | 上下文父节点必须和可删除候选分开，不能把展示树祖先自动升级为删除目标 |
| 文件结果独立审阅 | 手册 p11：注册表阶段后 Next，随后文件/文件夹，可看数量与导出 | 4247、4258/4259：文件结果和两阶段分别跳过的确认 | 未实测删除；文档确认可以审阅后保留全部结果 |
| 多版本/共享安装目录风险 | 手册 p10 明确警告 Advanced 可能包含另一个版本或同套件组件 | 128：“同一位置安装，可能找到双方残留，仔细检查” | 扫描命中不是所有权证明；拒绝删除厂商共享根目录仍必要 |
| 系统还原点 | 手册 p8、p10、p31：Windows 功能启用时请求创建 | 1206、4261–4265 覆盖创建中、失败、已关闭、完成 | 还原点可用性和创建成功必须分别报告；不能承诺恢复全部用户文件 |
| 文件恢复 | 手册 p11、p32：残留默认进回收站，可以从回收站恢复 | 1207、4255：回收站选项与确认 | 这不等于 Free 自带全量事务隔离区；没有执行真实回收站/恢复测试 |
| 排除规则 | 手册 p10、p32：排除注册表键和文件夹，可包含子键 | 排除相关资源存在 | 可设计可审计拒绝列表；不用复制 Revo 私有默认规则库 |
| Backup Manager / Custom Restore | 官方产品页区分 Free / Pro；Free 手册未将其列作常规模块 | 17820、17839 等共享语言资源中有名称 | 共享字符串可能包含 Pro 资源，不能以此宣称 Free 提供该模块；本项目恢复中心是独立实现 |

手册 p8 允许用户在厂商卸载报错后自行继续。极简卸载采用更严格的规则：失败、取消或未确认完成时停止额外清理；这属于本项目自己的安全设计。

## 面向极简卸载的独立设计建议与本轮边界

下面区分当前实现范围和后续建议，不代表所有参考能力已经实现，更不代表采用 Revo 的私有扫描规则。

1. 把“官方卸载”和“扫描/审阅残留”显式分开。只有官方卸载已确认完成后，扫描按钮才进入下一阶段；尚未核实、取消与失败分别报告。
2. 三档模式是本项目自定义规则。本轮安全档只清点已知安装位置；深入档仅在已知厂商目录下寻找**精确产品名子目录**，不把厂商目录本身列作删除目标。没有实现注册表子键枚举或扫描时间预算，不能宣称已有深度/节点/时间预算。将来若扩展枚举，应另行设置这些预算并验证边界；这仅是建议。
3. 结果树的父项只作上下文。实际候选显示命中理由、路径、类型、大小和风险，默认不勾选；“全选”也只能作用于候选，绝不能包含上下文祖先。
4. 仅对最终勾选计划做清理。可恢复文件进入本项目隔离区。**本轮注册表只导出备份，不删除注册表键**：普通“导出后删除”之间存在非原子竞态，导出成功并不能证明稍后删除时内容未发生变化。没有可靠机制消除该竞态前，不应通过“已备份”推导“可以安全删除”。
5. 恢复中心显示每次操作及对象状态，恢复时重新检查原路径、目标冲突、文件/目录边界和重解析点。恢复不覆盖后来产生的新数据。若操作中断导致隔离内容未按原记录完成校验，恢复中心会把它标为“待确认”，并要求用户明确同意后重新核验当前内容再恢复；程序不会自动接受变更后的内容。系统还原点可作为后续辅助设计，但不替代隔离/导出，也不当作厂商卸载的可逆保证；本次分析没有实测创建还原点。
6. 保留跳过、保留、失败、部分完成、等待重启与已恢复等独立状态。文件进入隔离区不应立即宣称释放了永久磁盘空间。

这些建议由公开工作流和安全需求推导，不包含 Revo 的源代码、专有图标、匹配数据库或还原算法。不得把本项目称为 Revo 引擎、算法复刻或经 Revo 验证。
