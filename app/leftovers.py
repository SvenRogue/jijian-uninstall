"""Bounded residual scan profiles. Candidate discovery is never deletion consent."""
from __future__ import annotations
import copy
import os
from pathlib import Path
from itertools import islice
from . import scanner
from .scanner import AppEntry, LeftoverItem

PROFILES = {
    'safe': ('安全', '只复查明确的安装位置；不包含用户数据与注册表。'),
    'standard': ('标准', '安装位置、精确匹配的应用数据、快捷方式与软件专用注册表。'),
    'advanced': ('深入', '在标准范围上检查厂商子目录中的精确应用名；不扫描整个磁盘或共享根。'),
}
MAX_VENDOR_CHILDREN = 1000
MAX_EXTRA_ITEMS = 100


def identity(item: LeftoverItem) -> tuple[str, str]:
    path = os.path.normcase(os.path.normpath(item.path))
    return item.kind, path


def scan_leftovers(entry: AppEntry, mode: str = 'standard') -> AppEntry:
    if mode not in PROFILES:
        raise ValueError('未知扫描模式')
    result = scanner.inventory(copy.deepcopy(entry))
    if mode == 'safe':
        result.leftovers = [i for i in result.leftovers if i.note == '安装目录']
    for item in result.leftovers:
        item.checked = False
        item.confidence = '明确位置' if item.note == '安装目录' else '名称匹配'
        item.basis = ('安装登记记录的位置；需人工确认归属' if item.note == '安装目录'
                      else '与应用名精确匹配；仅是候选，不代表全部内容可删除')
    if mode == 'advanced':
        seen = {identity(i) for i in result.leftovers}
        for item in _vendor_children(result):
            if identity(item) not in seen:
                result.leftovers.append(item)
                seen.add(identity(item))
    result.inventory_note = PROFILES[mode][1]
    return result


def _vendor_children(entry: AppEntry) -> list[LeftoverItem]:
    """Only one vendor level and exact product leaf names. No Documents."""
    wanted = {scanner._norm(n) for n in scanner._app_names(entry)}
    vendor_names = set()
    loc = scanner._derive_install_location(entry)
    if loc:
        parent = Path(loc).parent.name
        if parent.lower() not in ('program files', 'program files (x86)', 'programs', 'local', 'roaming'):
            vendor_names.add(parent)
    pub = entry.publisher.strip()
    if pub and pub.isascii() and pub.replace(' ', '').isalnum() and len(pub) <= 40:
        vendor_names.add(pub)
    roots = [os.environ.get('LOCALAPPDATA', ''), os.environ.get('APPDATA', ''),
             os.environ.get('ProgramData', r'C:\ProgramData')]
    out = []
    for root in roots:
        for vendor in sorted(vendor_names):
            if not root or not vendor or '/' in vendor or '\\' in vendor:
                continue
            base = Path(root)/vendor
            # A shared vendor node itself is never a candidate.
            if not base.is_dir() or base.is_symlink():
                continue
            try:
                entries = list(islice(base.iterdir(), MAX_VENDOR_CHILDREN))
            except OSError:
                continue
            for child in entries:
                if scanner._norm(child.name) not in wanted or not child.is_dir():
                    continue
                if not scanner.path_is_safe(str(child)):
                    continue
                item = LeftoverItem('dir', str(child), scanner._dir_size(str(child)),
                                    checked=False, note='厂商目录内的精确应用名')
                item.confidence = '需核对'
                item.basis = '只匹配厂商目录下的应用专用子目录；共享厂商目录不会被选中'
                out.append(item)
                if len(out) >= MAX_EXTRA_ITEMS:
                    return out
    return out
