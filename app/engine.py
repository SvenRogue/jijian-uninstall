"""Conservative prerelease engine: reviewed snapshot only; no SYSTEM fallback."""
from __future__ import annotations
import copy
import ctypes
import json
import ntpath
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from . import reg, scanner
from .scanner import AppEntry, LeftoverItem, human_size
IS_WIN = sys.platform == 'win32'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if IS_WIN else 0
LOG_DIR = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'JiJianUninstall' / 'logs'

@dataclass
class Report:
    app_name: str = ''
    started: str = ''
    finished: str = ''
    dry_run: bool = False
    official_ok: bool = False
    official_detail: str = ''
    killed: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    removed_bytes: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    retained: list[str] = field(default_factory=list)
    log_path: str = ''
    @property
    def clean(self):
        return (not self.dry_run and self.official_ok and not self.remaining
                and not self.failed and not self.retained)

def _split_command(raw):
    raw = os.path.expandvars(raw.strip())
    if not raw or any(c in raw for c in '\r\n\x00'):
        raise ValueError('无效的卸载命令')
    if not raw.startswith('"'):
        m = re.match(r'(.+?\.exe)(?=\s|$)', raw, re.I)
        if m:
            raw = '"' + m.group(1) + '"' + raw[m.end():]
    if IS_WIN:
        shell = ctypes.WinDLL('shell32', use_last_error=True)
        shell.CommandLineToArgvW.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_int)]
        shell.CommandLineToArgvW.restype = ctypes.POINTER(ctypes.c_wchar_p)
        n = ctypes.c_int()
        ptr = shell.CommandLineToArgvW(raw, ctypes.byref(n))
        if not ptr:
            raise ValueError('无法解析卸载命令')
        try:
            return [ptr[i] for i in range(n.value)]
        finally:
            kernel = ctypes.WinDLL('kernel32', use_last_error=True)
            kernel.LocalFree.argtypes = [ctypes.c_void_p]
            kernel.LocalFree(ctypes.cast(ptr, ctypes.c_void_p))
    import shlex
    return [s.strip('"') for s in shlex.split(raw, posix=False)]

def _safe_path(path):
    if not path or any(c in path for c in '\x00\r\n&|<>^%!*?'):
        return False
    p = ntpath.normcase(ntpath.normpath(path))
    if not ntpath.isabs(p) or p.startswith('\\\\'):
        return False
    drive, tail = ntpath.splitdrive(p)
    if tail in ('', '\\', '/') or ':' in tail:
        return False
    for root in (r'C:\Windows', r'C:\Program Files\WindowsApps'):
        n = ntpath.normcase(root)
        if p == n or p.startswith(n + '\\'):
            return False
    roots = [r'C:\Program Files', r'C:\Program Files (x86)', r'C:\ProgramData', r'C:\Users']
    roots += [os.environ.get(k, '') for k in ('USERPROFILE','APPDATA','LOCALAPPDATA','PUBLIC')]
    if p in {ntpath.normcase(ntpath.normpath(r)) for r in roots if r}:
        return False
    shared = {'tencent','microsoft','google','adobe','common files','programs','packages',
              'desktop','documents','downloads','appdata','local','roaming','locallow',
              'start menu','startup','software','users'}
    if ntpath.basename(p).lower() in shared:
        return False
    cur = Path(os.path.abspath(path))
    for part in (cur, *cur.parents):
        try:
            st = part.lstat()
            if part.is_symlink() or getattr(st, 'st_file_attributes', 0) & 0x400:
                return False
        except FileNotFoundError:
            pass
        except OSError:
            return False
    guard = getattr(scanner, 'path_is_safe', None)
    return bool(guard(path)) if guard else True

def _safe_key(path):
    parts = path.replace('/', '\\').strip('\\').split('\\')
    if len(parts) < 3 or parts[0].upper() not in ('HKCU','HKLM') or parts[1].lower() != 'software':
        return False
    if any(c in path for c in '\x00\r\n&|<>^%!*?'):
        return False
    shared = {'microsoft','tencent','google','adobe','wow6432node','classes','policies','uninstall','run','runonce'}
    if parts[-1].lower() in shared or parts[2].lower() in ('classes','policies'):
        return False
    if len(parts) == 3:
        return True
    if len(parts) == 4 and parts[2].lower() == 'wow6432node':
        return True
    return '\\'.join(parts[:-1]).lower() in {
        r'hkcu\software\microsoft\windows\currentversion\uninstall',
        r'hklm\software\microsoft\windows\currentversion\uninstall',
        r'hklm\software\wow6432node\microsoft\windows\currentversion\uninstall'}

class Uninstaller:
    def __init__(self, log, progress=None):
        self._log = log
        self._progress = progress or (lambda v: None)
        self._removed_bytes = 0
        self._deferred = []
        self._report = Report()
    def log(self, msg, level='info'):
        self._log({'ok':'✓ ', 'warn':'! ', 'err':'✗ '}.get(level,'  ') + msg)
    @staticmethod
    def is_admin():
        try:
            return IS_WIN and bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False
    @staticmethod
    def relaunch_elevated(script_args=None):
        if not IS_WIN:
            return False
        args = list(script_args or [])
        if not getattr(sys, 'frozen', False):
            args.insert(0, str(Path(__file__).resolve().parent.parent / 'main.py'))
        return ctypes.windll.shell32.ShellExecuteW(None, 'runas', sys.executable,
                    subprocess.list2cmdline(args), None, 1) > 32
    def run(self, entry, do_registry=True, do_appdata=True, do_shortcuts=True, dry_run=False):
        self._removed_bytes = 0
        self._deferred = []
        rep = self._report = Report(app_name=entry.name, dry_run=dry_run,
                                    started=datetime.now().isoformat(timespec='seconds'))
        # No reinventory: cleanup can only touch the reviewed, checked snapshot.
        entry = copy.deepcopy(entry)
        enabled = {'key':do_registry, 'dir':do_appdata, 'appxdata':do_appdata, 'file':do_shortcuts}
        selected = [i for i in entry.leftovers if i.checked and enabled.get(i.kind, False)]
        self.log(f"{'演练' if dry_run else '开始处理'}：{entry.name}")
        try:
            cmd = self._official_command(entry)
            self.log(f"{'[演练] ' if dry_run else ''}官方卸载：{subprocess.list2cmdline(cmd)}")
            if dry_run:
                rep.official_detail = '仅预览，未执行卸载或清理'
                for item in selected:
                    safe = _safe_key(item.path) if item.kind == 'key' else _safe_path(item.path)
                    self.log(f"[演练] {'计划清理' if safe else '拒绝不安全位置'}：{item.path}")
                return self._finish(rep)
            self._progress(10)
            rep.official_ok, rep.official_detail = self._run_official(entry)
            if not rep.official_ok:
                rep.failed.append(('official', rep.official_detail))
                self.log('官方卸载失败或未能确认；已停止后续清理。', 'err')
                return self._finish(rep)
            snapshot = type('Snapshot', (), {'leftovers':selected})()
            self._remove_registry(snapshot)
            self._remove_shortcuts(snapshot)
            self._remove_dirs(snapshot)
            for item in entry.leftovers:
                if self._exists(item):
                    if item.checked and enabled.get(item.kind, False):
                        rep.remaining.append(item.path)
                    else:
                        rep.retained.append(item.path)
        except Exception as exc:
            rep.failed.append(('engine', f'{type(exc).__name__}: {exc}'))
            self.log(str(exc), 'err')
        return self._finish(rep)
    def _finish(self, rep):
        rep.finished = datetime.now().isoformat(timespec='seconds')
        rep.removed_bytes = self._removed_bytes
        rep.log_path = self._save_report(rep)
        self._progress(100)
        return rep
    @staticmethod
    def _exists(item):
        return reg.exists(item.path) if item.kind == 'key' else os.path.lexists(item.path)
    def _official_command(self, entry):
        if entry.uninstall_string or entry.uninstall_type == 'appx':
            return self._official_command_native(entry)
        if entry.winget_id and re.fullmatch(r'[A-Za-z0-9_.-]+', entry.winget_id):
            return [scanner._winget_exe(),'uninstall','--id',entry.winget_id,
                    '--exact','--silent','--disable-interactivity']
        raise ValueError('没有可用的官方卸载命令')
    def _official_command_native(self, entry):
        if entry.uninstall_type == 'appx':
            fam = getattr(entry, '_pkg_family', '')
            if not re.fullmatch(r'[A-Za-z0-9.\-]+_[A-Za-z0-9]+', fam):
                raise ValueError('无效的 MSIX 包系列标识')
            ps = ("$ErrorActionPreference='Stop'; "
                  f"$p=@(Get-AppxPackage | Where-Object {{$_.PackageFamilyName -eq '{fam}'}}); "
                  "if (!$p.Count) { throw 'Package not found' }; "
                  "$p | ForEach-Object { Remove-AppxPackage -Package $_.PackageFullName -ErrorAction Stop }; "
                  f"if (Get-AppxPackage | Where-Object {{$_.PackageFamilyName -eq '{fam}'}}) "
                  "{ throw 'Package still registered' }")
            return [scanner._powershell(),'-NoProfile','-NonInteractive','-Command',ps]
        cmd = _split_command(entry.quiet_uninstall_string or entry.uninstall_string)
        exe = ntpath.basename(cmd[0]).lower()
        if exe in {'cmd.exe','cmd','powershell','powershell.exe','pwsh','pwsh.exe',
                   'wscript.exe','cscript.exe','rundll32.exe','mshta.exe'} or not exe.endswith('.exe'):
            raise ValueError('预发布版只执行直接 EXE 卸载命令')
        if entry.uninstall_type == 'msiexec':
            args = [re.sub(r'^/i(?=\{|$)', '/X', s, flags=re.I) for s in cmd[1:]]
            args = [s for s in args if s.lower() not in ('/qb','/qn','/quiet','/passive')]
            return [cmd[0], *args, '/qn', '/norestart']
        if entry.quiet_uninstall_string:
            return cmd
        if entry.uninstall_type == 'nsis':
            return [*cmd, '/S']
        if entry.uninstall_type == 'inno':
            return [*cmd, '/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART']
        return cmd
    def _run_official(self, entry):
        try:
            r = subprocess.run(self._official_command(entry), capture_output=True,
                               creationflags=NO_WINDOW, timeout=600, shell=False)
            if r.returncode not in (0,1641,3010):
                return False, f'卸载器返回 {r.returncode}'
            if r.returncode in (1641,3010):
                return False, '卸载器要求重启；重启前不执行额外清理'
            if entry.uninstall_type == 'appx':
                return True, 'MSIX 已卸载并验证包登记消失'
            arp = getattr(entry, '_arp_key', '')
            if arp:
                if reg.exists(arp):
                    return False, '卸载器返回成功，但卸载登记仍存在'
                return True, '卸载登记已移除'
            loc = entry.install_location
            if loc and _safe_path(loc) and not os.path.exists(loc):
                return True, '安装目录已移除'
            return False, '卸载器已退出，但没有足够证据确认卸载成功'
        except Exception as exc:
            return False, f'{type(exc).__name__}: {exc}'
    def _remove_registry(self, entry):
        for item in entry.leftovers:
            if item.kind != 'key' or not item.checked or not self._exists(item):
                continue
            if not _safe_key(item.path):
                self._defer(item.path, '拒绝宽泛或共享注册表项')
            elif reg.delete_tree_deep(item.path):
                self._report.removed.append(item.path)
                item.fixed = True
            else:
                self._defer(item.path, '权限不足；未尝试 SYSTEM 提权')
    def _remove_shortcuts(self, entry):
        for item in entry.leftovers:
            if item.kind != 'file' or not item.checked or not self._exists(item):
                continue
            if not item.path.lower().endswith(('.lnk','.url')):
                self._defer(item.path, '仅允许删除快捷方式')
            elif self._delete([item.path]):
                self._report.removed.append(item.path)
                item.fixed = True
            else:
                self._defer(item.path, '快捷方式删除失败')
    def _remove_dirs(self, entry):
        for item in entry.leftovers:
            if item.kind not in ('dir','appxdata') or not item.checked or not self._exists(item):
                continue
            if not _safe_path(item.path):
                self._defer(item.path, '拒绝宽泛、共享或重解析路径')
            elif self._delete([item.path]):
                self._removed_bytes += item.size
                item.fixed = True
                self._report.removed.append(item.path)
            else:
                self._defer(item.path, '权限不足或文件占用；未尝试 SYSTEM 提权')
    def _delete(self, paths):
        for path in paths:
            if not _safe_path(path):
                return False
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                elif os.path.lexists(path):
                    os.unlink(path)
            except OSError:
                return False
        return all(not os.path.lexists(p) for p in paths)
    def _defer(self, path, reason):
        self._deferred.append((path, reason))
        self._report.failed.append((path, reason))
        self.log(f'保留 {path}：{reason}', 'warn')
    def _sweep_protected(self):
        """SYSTEM tasks and ACL changes are disabled for public prerelease."""
        return None
    def _save_report(self, rep):
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            safe = re.sub(r'[\\/:*?"<>|]', '_', rep.app_name)[:40]
            p = LOG_DIR / f'{datetime.now():%Y%m%d_%H%M%S_%f}_{safe}.json'
            p.write_text(json.dumps(asdict(rep),ensure_ascii=False,indent=2),encoding='utf-8')
            return str(p)
        except OSError as exc:
            self.log(f'报告保存失败：{exc}', 'warn')
            return ''
