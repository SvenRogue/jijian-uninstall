"""Application discovery: reads the Windows Add/Remove Programs registry,
MSIX/Store packages, and winget. Produces a normalized AppEntry list and
inventories the leftovers that each app leaves behind.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

IS_WIN = sys.platform == "win32"

from . import reg as regmod

UNINSTALL_ROOTS = [
    (r"HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "machine"),
    (r"HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall", "machine"),
    (r"HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall", "user"),
]


def _run(args: list[str], timeout: int = 90) -> str:
    flags = 0
    if IS_WIN:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        p = subprocess.run(
            args,
            capture_output=True,
            timeout=timeout,
            creationflags=flags,
        )
        raw = p.stdout or b""
        for enc in ("utf-8", "mbcs", "gbk", "latin-1"):
            try:
                return raw.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", "replace")
    except Exception:
        return ""


def _reg_strings(key: str) -> dict[str, str]:
    return regmod.values(key)


def _list_subkeys(root: str) -> list[str]:
    return regmod.subkeys(root)


def _parse_size(s: str) -> int:
    try:
        return int(float(s.replace(",", "").strip()))
    except Exception:
        return 0


def _strip_quotes(s: str) -> str:
    s = (s or "").strip()
    if s.startswith('"'):
        end = s.find('"', 1)
        if end > 0:
            return s[1:end]
    return s.split(" ")[0] if " " in s and not s.lower().endswith(".exe") else s


# ------------------------------------------------------------------ model
@dataclass
class LeftoverItem:
    kind: str          # dir | key | file | service | appxdata
    path: str
    size: int = 0
    exists: bool = True
    note: str = ""
    checked: bool = True
    fixed: bool = False   # True when deletion succeeded
    confidence: str = "需核对"
    basis: str = "名称和路径仅供人工核对"
    selectable: bool = True

    @property
    def label(self) -> str:
        return Path(self.path.rstrip("\\")).name or self.path


@dataclass
class AppEntry:
    name: str
    version: str = ""
    publisher: str = ""
    install_location: str = ""
    uninstall_string: str = ""
    quiet_uninstall_string: str = ""
    install_date: str = ""
    size: int = 0
    scope: str = "machine"      # machine | user | store
    source: str = "arp"         # arp | store | winget
    winget_id: str = ""
    uninstall_type: str = "custom"   # nsis | inno | msiexec | winget | appx | custom
    display_icon: str = ""
    uid: str = ""
    score: int = 0
    score_parts: list[str] = field(default_factory=list)
    leftovers: list[LeftoverItem] = field(default_factory=list)
    inventory_note: str = ""

    def __post_init__(self):
        if not self.uid:
            h = hashlib.sha1(f"{self.name}|{self.publisher}|{self.version}".encode("utf-8", "ignore"))
            self.uid = h.hexdigest()[:16]

    @property
    def total_leftover(self) -> int:
        return sum(i.size for i in self.leftovers if i.exists)

    @property
    def selected_leftover(self) -> list[LeftoverItem]:
        return [i for i in self.leftovers if i.exists and i.checked and not i.fixed]


# ------------------------------------------------------------- helpers
def _human_size(n: int) -> str:
    if n <= 0:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:,.1f} {unit}" if unit != "B" else f"{n:.0f} B"
        n /= 1024.0
    return f"{n:.1f} GB"


def human_size(n: int) -> str:
    return _human_size(n)


def _dir_size(path: str, limit: int = 250_000) -> int:
    total = 0
    count = 0
    try:
        for root, dirs, files in os.walk(path, onerror=lambda e: None):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
                count += 1
                if count > limit:
                    return total
    except Exception:
        pass
    return total


# --------------------------------------------------------- uninstall type
def classify_uninstaller(entry: AppEntry) -> str:
    if entry.source == "store":
        return "appx"
    us = (entry.uninstall_string or "").strip()
    low = us.lower()
    if not us:
        return "winget" if entry.winget_id else "custom"
    if "msiexec" in low:
        return "msiexec"
    exe = _strip_quotes(us)
    # probe the uninstaller binary for the installer engine family
    if exe and os.path.isfile(exe):
        try:
            with open(exe, "rb") as fh:
                head = fh.read(2_000_000)
            if b"Nullsoft" in head or b"NSIS" in head:
                return "nsis"
            if b"Inno Setup" in head or b"innounp" in head.lower():
                return "inno"
        except OSError:
            pass
    if entry.winget_id:
        return "winget"
    return "custom"


# ---------------------------------------------------------- inventory
_DEFAULT_SKIP = {"microsoft", "windows", "nvidia", "realtek", "intel", "amd", "common files"}


def _norm(s: str) -> str:
    return re.sub(r"[\s_\-\.]+", "", (s or "").lower())


# generic words that must never drive a directory match on their own
_GENERIC = {
    "programfiles", "programdata", "appdata", "local", "roaming", "cache",
    "data", "user", "users", "tools", "tool", "client", "app", "apps", "desktop",
    "version", "common", "shared", "temp", "config", "logs", "bin", "packages",
    "programs", "microsoft", "windows", "system", "software",
}


def _app_names(entry: AppEntry) -> set[str]:
    """Only product identity is evidence. A publisher is never an app folder."""
    base = entry.name.strip()
    for sep in ("  ", " (", " v", " 版本 ", " Version "):
        base = base.split(sep)[0]
    base = re.sub(r"\s*\d+(\.\d+)+.*$", "", base).strip()
    names = {base}
    loc = (entry.install_location or "").strip().strip('"')
    if loc and path_is_safe(loc):
        names.add(Path(loc).name)
    return {n for n in names if len(_norm(n)) >= 3 and _norm(n) not in _GENERIC}


def path_is_safe(path: str) -> bool:
    """Reject OS/shared roots and any reparse point in a candidate's ancestry.

    This is a refusal guard, not proof that a folder belongs to an application.
    Execution still requires the user's frozen, explicitly selected plan.
    """
    if not path or not os.path.isabs(path):
        return False
    absolute = os.path.abspath(path)
    resolved = os.path.realpath(absolute)
    norm = lambda p: os.path.normcase(os.path.normpath(p))
    home = os.environ.get("USERPROFILE", str(Path.home()))
    roots = [os.path.abspath(os.sep), home, os.path.dirname(home),
             os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", ""),
             os.environ.get("ProgramData", r"C:\ProgramData"),
             os.environ.get("ProgramFiles", r"C:\Program Files"),
             os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
             os.environ.get("TEMP", "")]
    roots += [os.path.join(home, n) for n in ("Desktop", "Documents", "Downloads", "Pictures", "AppData")]
    roots += [os.path.join(home, "AppData", "LocalLow"),
              os.path.join(os.environ.get("LOCALAPPDATA", home), "Programs"),
              os.path.join(os.environ.get("LOCALAPPDATA", home), "Packages")]
    if norm(resolved) in {norm(r) for r in roots if r}:
        return False
    if norm(os.path.dirname(resolved)) == norm(resolved):
        return False
    system = os.environ.get("SystemRoot", r"C:\Windows")
    forbidden = [system]
    for root in roots:
        if root and Path(root).name.lower() in ("program files", "program files (x86)"):
            forbidden += [os.path.join(root, n) for n in ("WindowsApps", "Common Files")]
    for root in forbidden:
        try:
            if os.path.commonpath([norm(resolved), norm(root)]) == norm(root):
                return False
        except ValueError:
            continue
    shared = {"tencent", "mozilla", "microsoft", "google", "apple", "adobe", "nvidia", "intel", "amd"}
    if Path(absolute).name.lower() in shared:
        return False
    cursor = Path(absolute)
    for node in (cursor, *cursor.parents):
        try:
            st = node.lstat()
            if node.is_symlink() or (getattr(st, "st_file_attributes", 0) & 0x400):
                return False
        except FileNotFoundError:
            continue
        except OSError:
            return False
    return norm(absolute) == norm(resolved)


def _candidate_dirs(entry: AppEntry) -> list[str]:
    """Exact application-name matches in app data only, never Documents/vendors."""
    wanted = {_norm(n) for n in _app_names(entry)}
    roots = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("APPDATA", ""),
             os.path.join(os.environ.get("USERPROFILE", str(Path.home())), "AppData", "LocalLow"),
             os.environ.get("ProgramData", r"C:\ProgramData")]
    found = []
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            children = os.listdir(root)
        except OSError:
            continue
        for name in children:
            full = os.path.join(root, name)
            if _norm(name) in wanted and os.path.isdir(full) and path_is_safe(full):
                found.append(full)
    return list(dict.fromkeys(found))


def _candidate_keys(entry: AppEntry) -> list[str]:
    keys = []
    for n in _app_names(entry):
        if "\\" in n or "/" in n or n.lower() in _GENERIC:
            continue
        for base in (r"HKCU\Software", r"HKLM\SOFTWARE\WOW6432Node", r"HKLM\SOFTWARE"):
            keys.append(f"{base}\\{n}")
    return keys


def _derive_install_location(entry: AppEntry) -> str:
    """Use explicit ARP location or an app-named uninstaller parent only."""
    loc = (entry.install_location or "").strip().strip('"')
    if loc:
        return loc if path_is_safe(loc) else ""
    names = {_norm(n) for n in _app_names(entry)}
    for raw in (entry.uninstall_string, entry.quiet_uninstall_string):
        exe = _strip_quotes(raw or "")
        parent = os.path.dirname(exe)
        if (exe and os.path.isfile(exe) and parent and path_is_safe(parent)
                and _norm(Path(parent).name) in names):
            return parent
    return ""


def inventory(entry: AppEntry) -> AppEntry:
    """Build the leftover list for one app."""
    items: list[LeftoverItem] = []
    seen: set[str] = set()

    # 1. MSIX package data
    if entry.source == "store" and entry.install_location:
        pass
    pkg_family = getattr(entry, "_pkg_family", "")
    if pkg_family:
        p = Path(os.environ.get("LOCALAPPDATA", "")) / "Packages" / pkg_family
        if p.is_dir() and path_is_safe(str(p)):
            items.append(LeftoverItem("appxdata", str(p), _dir_size(str(p)),
                                      checked=False, note="Store 应用数据 / 设置 / 缓存"))
            seen.add(str(p).lower())

    # 2. install directory itself
    loc = _derive_install_location(entry)
    if entry.source != "store" and loc and os.path.isdir(loc) and path_is_safe(loc):
        lk = os.path.normpath(loc).lower()
        if lk not in {os.path.normpath(s).lower() for s in seen}:
            items.append(LeftoverItem("dir", loc, _dir_size(loc), checked=False, note="安装目录"))
            seen.add(lk)

    # 3. app data dirs
    for d in _candidate_dirs(entry):
        key = d.lower().rstrip("\\")
        if key in seen or any(key == s.rstrip("\\") for s in seen):
            continue
        items.append(LeftoverItem("dir", d, _dir_size(d), checked=False, note="用户数据 / 缓存"))
        seen.add(key)

    # 4. registry keys
    for k in _candidate_keys(entry):
        if _reg_exists(k):
            items.append(LeftoverItem("key", k, 0, checked=False, note="软件注册表"))
            seen.add(k.lower())

    # 5. uninstall registration key
    uk = getattr(entry, "_arp_key", "")
    if uk and _reg_exists(uk):
        items.append(LeftoverItem("key", uk, 0, checked=False,
                                  note="控制面板卸载登记（官方卸载后应自动消失）"))

    # 6. shortcuts
    for s in _shortcut_paths(entry):
        items.append(LeftoverItem("file", s, 0, checked=False, note="快捷方式"))

    entry.leftovers = items
    return entry


def _reg_exists(key: str) -> bool:
    return regmod.exists(key)


def _shortcut_paths(entry: AppEntry) -> list[str]:
    """Only shortcuts that live in a folder named after the app, or that carry
    the exact app name — never every .lnk containing a shared word."""
    out = []
    roots = [
        os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
        os.path.join(os.environ.get("USERPROFILE", ""), "Desktop"),
        r"C:\Users\Public\Desktop",
    ]
    base = entry.name or ""
    for sep in ("  ", " (", " v", " 版本 "):
        base = base.split(sep)[0]
    base = base.strip()
    nb = _norm(base)
    if len(nb) < 3:
        return out
    for root in roots:
        if not os.path.isdir(root):
            continue
        try:
            for r, dirs, files in os.walk(root):
                depth = r[len(root):].count(os.sep)
                if depth >= 2:
                    dirs.clear()
                for fn in files:
                    stem = os.path.splitext(fn)[0]
                    if not fn.lower().endswith((".lnk", ".url")):
                        continue
                    ns = _norm(stem)
                    in_named_folder = _norm(Path(r).name) == nb
                    if (in_named_folder or ns == nb) and path_is_safe(os.path.join(r, fn)):
                        out.append(os.path.join(r, fn))
        except OSError:
            pass
    return out


# ------------------------------------------------------------- scan
_SKIP_NAME = (
    "update for ", "security update", "hotfix", "kb2", "kb3", "kb4", "kb5",
)
_SKIP_SYS = (
    "microsoft visual c++", "windows sdk", "windows driver", "microsoft .net",
    "microsoft edge update", "microsoft vc redistributable", "windows software development kit",
)


def _should_skip(name: str, system_component: bool) -> bool:
    n = (name or "").strip().lower()
    if not n:
        return True
    if system_component:
        return True
    if any(n.startswith(s) for s in _SKIP_NAME):
        return True
    if any(s in n for s in _SKIP_SYS):
        return True
    return False


def scan_arp() -> list[AppEntry]:
    apps: list[AppEntry] = []
    seen: set[str] = set()
    for root, scope in UNINSTALL_ROOTS:
        for fullkey in _list_subkeys(root):
            vals = _reg_strings(fullkey)
            name = vals.get("DisplayName", "").strip()
            if not name:
                continue
            system_component = str(vals.get("SystemComponent", "0")).strip() == "1"
            if _should_skip(name, system_component):
                continue
            parent = vals.get("ParentKeyName", "").strip()
            if parent:
                continue
            release = vals.get("ReleaseType", "").lower()
            if release in ("update", "hotfix", "security update"):
                continue
            uninst = vals.get("UninstallString", "").strip()
            quiet = vals.get("QuietUninstallString", "").strip()
            if not uninst and not quiet:
                continue
            loc = vals.get("InstallLocation", "").strip().strip('"')
            key_path = fullkey
            e = AppEntry(
                name=name,
                version=vals.get("DisplayVersion", "").strip(),
                publisher=vals.get("Publisher", "").strip(),
                install_location=loc,
                uninstall_string=uninst,
                quiet_uninstall_string=quiet,
                install_date=vals.get("InstallDate", "").strip(),
                size=_parse_size(vals.get("EstimatedSize", "0")),
                scope=scope,
                source="arp",
                display_icon=vals.get("DisplayIcon", "").strip(),
                uid="arp:" + hashlib.sha1(fullkey.encode("utf-8", "ignore")).hexdigest()[:16],
            )
            e._arp_key = key_path          # type: ignore[attr-defined]
            if e.name.lower() in seen:
                continue
            seen.add(e.name.lower())
            apps.append(e)
    return apps


def _powershell() -> str:
    """Absolute powershell.exe: a frozen process may not inherit a usable PATH."""
    cand = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"),
                        "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    return cand if os.path.isfile(cand) else "powershell"


_APPX_PS = (
    "Get-AppxPackage | Where-Object { -not $_.IsFramework -and -not $_.NonRemovable } | "
    "ForEach-Object { $_.Name + [char]9 + $_.PackageFamilyName + [char]9 + "
    "$_.Version + [char]9 + $_.PublisherDisplayName + [char]9 + $_.InstallLocation }"
)


def _parse_store_lines(out: str) -> list[AppEntry]:
    apps: list[AppEntry] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.startswith(("Name", "Get-AppxPackage", "Active code page")):
            continue
        parts = line.split("\t")
        if len(parts) < 5:
            continue
        name, family, version, publisher, loc = parts[:5]
        if not family or _is_junk_pkg(name, family, publisher):
            continue
        e = AppEntry(
            name=_pretty_pkg_name(name),
            version=str(version),
            publisher=publisher,
            install_location=loc,
            scope="store",
            source="store",
            uninstall_type="appx",
            uid="store:" + family,
        )
        e._pkg_family = family        # type: ignore[attr-defined]
        e._pkg_full = name            # type: ignore[attr-defined]
        apps.append(e)
    return apps


def scan_store() -> list[AppEntry]:
    """Use registered packages only; never synthesize identities from data folders."""
    apps = _scan_store_powershell()
    _diag(f"store(powershell)={len(apps)}")
    return apps


def _scan_store_powershell() -> list[AppEntry]:
    ps = _powershell()
    attempts = [
        ([ps, "-NoProfile", "-NonInteractive", "-Command", _APPX_PS],
         subprocess.CREATE_NO_WINDOW if IS_WIN else 0),
        ([ps, "-NoProfile", "-NonInteractive", "-Command", _APPX_PS], 0),
    ]
    for args, flags in attempts:
        try:
            r = subprocess.run(args, capture_output=True, timeout=180,
                               creationflags=flags)
        except Exception as e:
            _diag(f"store attempt failed: {type(e).__name__}: {e}")
            continue
        out = _decode(r.stdout)
        _diag(f"store attempt flags={flags} rc={r.returncode} chars={len(out)}")
        apps = _parse_store_lines(out)
        if apps:
            return apps
    return []


def _decode(raw: bytes) -> str:
    for enc in ("utf-8", "mbcs", "gbk", "latin-1"):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", "replace")


_PKG_SUFFIXES = ("app", "application", "desktop", "beta", "preview", "pre", "client", "win")

# MSIX packages that are OS plumbing, not user apps
_PKG_SKIP = (
    "windows.", "winappruntime", "vclibs", "net. native", "directx", "xbox",
    "applicationcompatibility", "shell", "runtime", "ddlm", "widgetsplatform",
    "speech", "language", "voice", "font", "codec", "heif", "webp", "av1",
    "legacymedia", "store purchase", "photosplugin", "servicesencryption",
    "nvidia", "bandizip", "expansion", "stream", "teamsworld",
)


def _pretty_pkg_name(name: str) -> str:
    """'Microsoft.WindowsCalculator' -> 'Windows Calculator'"""
    import re
    raw = name
    bits = [p for p in name.split(".") if p]
    # drop packaging suffix and any publisher-hash / numeric-noise segments
    while len(bits) > 1 and bits[-1].lower() in _PKG_SUFFIXES:
        bits.pop()
    cleaned: list[str] = []
    for i, b in enumerate(bits):
        # 16-hex publisher hashes and bare numbers carry no meaning
        if i > 0 and (re.fullmatch(r"[0-9A-Fa-f]{6,}", b) or re.fullmatch(r"\d+", b)):
            continue
        cleaned.append(b)
    bits = cleaned or bits
    # drop the leading publisher name unless it IS the product
    if len(bits) > 1 and bits[0].lower() in (
            "microsoft", "google", "meta", "apple", "tencent", "amazon", "nvidia",
            "realtek", "intel", "asus", "hp", "dell", "lenovo"):
        bits = bits[1:]
    words: list[str] = []
    for b in bits:
        for w in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z0-9]*|[a-z0-9]+", b):
            words.append(w)
    label = " ".join(words).strip()
    if not label or re.fullmatch(r"[0-9A-Fa-f ]{6,}", label.replace(" ", "")):
        label = raw.split(".")[-1]
    return label or raw


def _is_junk_pkg(name: str, family: str, publisher: str = "") -> bool:
    n = (name or "").lower()
    f = (family or "").lower()
    if any(k in n for k in _PKG_SKIP) or any(k in f for k in _PKG_SKIP):
        return True
    # framework / driver plumbing publishes as these
    pub = (publisher or "").lower()
    if any(k in pub for k in ("corporation ii", "micro star", "oem")):
        return True
    tail = n.split("_")[0].split(".")[-1]
    if len(tail) >= 8 and all(c in "0123456789abcdef" for c in tail):
        return True
    return False


def _winget_exe() -> str:
    """Absolute winget.exe: a frozen process may not inherit a usable PATH."""
    local = os.environ.get("LOCALAPPDATA", "")
    cand = os.path.join(local, "Microsoft", "WindowsApps", "winget.exe")
    if os.path.isfile(cand):
        return cand
    try:
        import shutil
        found = shutil.which("winget")
        if found:
            return found
    except Exception:
        pass
    return "winget"


def scan_winget() -> dict[str, str]:
    """name(lower) -> winget id"""
    out = _run([_winget_exe(), "list", "--accept-source-agreements",
                "--disable-interactivity"], timeout=180)
    _diag(f"winget raw chars={len(out)}")
    mapping: dict[str, str] = {}
    for line in out.splitlines():
        line = line.rstrip()
        if not line or line.startswith("Name") or line.startswith("-") or "No installed" in line:
            continue
        parts = line.split("  ")
        parts = [p.strip() for p in parts if p.strip()]
        if len(parts) < 2:
            continue
        mapping[parts[0].lower()] = parts[1]
    return mapping


def _diag(msg: str) -> None:
    """Append a line to the diagnostics log (helps debug the frozen build)."""
    try:
        d = Path(os.environ.get("LOCALAPPDATA") or str(Path.home())) / "JiJianUninstall"
        d.mkdir(parents=True, exist_ok=True)
        with open(d / "scan_debug.log", "a", encoding="utf-8") as fh:
            fh.write(f"[{__import__('datetime').datetime.now():%H:%M:%S}] {msg}\n")
    except Exception as e:
        try:
            with open(os.path.join(os.environ.get("TEMP", "."), "jijian_diag_fail.txt"),
                      "a", encoding="utf-8") as fh:
                fh.write(f"{type(e).__name__}: {e}\n")
        except Exception:
            pass


def scan_all(progress=None) -> list[AppEntry]:
    def _note(msg):
        """Report progress without ever letting a closed stdout kill the scan."""
        if progress:
            try:
                progress(msg)
            except Exception:
                pass

    _note("读取控制面板安装列表…")
    try:
        apps = scan_arp()
        _diag(f"arp={len(apps)}")
    except Exception as e:
        _diag(f"arp FAILED {type(e).__name__}: {e}")
        apps = []
    _note("读取 Windows 应用商店应用…")
    try:
        st = scan_store()
        _diag(f"store={len(st)}")
        apps += st
    except Exception as e:
        _diag(f"store FAILED {type(e).__name__}: {e}")
    _note("读取 winget 索引…")
    try:
        wg = scan_winget()
        _diag(f"winget={len(wg)}")
    except Exception as e:
        _diag(f"winget FAILED {type(e).__name__}: {e}")
        wg = {}
    for a in apps:
        wid = wg.get(a.name.lower())
        if wid:
            a.winget_id = wid
    for a in apps:
        try:
            a.uninstall_type = classify_uninstaller(a)
        except Exception:
            a.uninstall_type = "custom"
        try:
            a.score, a.score_parts = _score(a)
        except Exception:
            a.score, a.score_parts = 0, []
    apps.sort(key=lambda x: (-x.score, x.name.lower()))
    _diag(f"total={len(apps)}")
    return apps


def _score(a: AppEntry) -> tuple[int, list[str]]:
    """How much residue is predictable for this app (higher = better target)."""
    s = 0
    parts = []
    loc = (a.install_location or "").strip().strip('"')
    if loc and os.path.isdir(loc):
        s += 40
        parts.append("安装目录已知")
    elif a.uninstall_type in ("nsis", "inno", "msiexec"):
        s += 20
        parts.append("标准安装包")
    if a.uninstall_type == "nsis" or a.uninstall_type == "inno":
        s += 10
        parts.append("支持静默卸载")
    if a.winget_id:
        s += 15
        parts.append("winget 可管")
    if a.source == "store":
        s += 10
        parts.append("Store 应用")
    if a.publisher:
        s += 5
    return s, parts
