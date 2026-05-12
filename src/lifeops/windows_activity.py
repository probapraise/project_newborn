from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from datetime import datetime, timezone
from pathlib import Path

from .app_scope import STEAM_PROCESSES, classify_monitored_process
from .browser_activity import extract_domain_from_text
from .models import ActivitySnapshot

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TH32CS_SNAPPROCESS = 0x00000002
INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
STEAM_LAUNCHED_PROCESS_NAME = "steam-launched-app"


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", wintypes.WCHAR * 260),
    ]


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _clean_title(value: str) -> str:
    return " ".join(value.split())


def _load_user32() -> ctypes.WinDLL:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    return user32


def _load_kernel32() -> ctypes.WinDLL:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    return kernel32


def _get_window_text(user32: ctypes.WinDLL, hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length <= 0:
        return ""
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return _clean_title(buffer.value)


def _get_window_pid(user32: ctypes.WinDLL, hwnd: int) -> int | None:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return int(pid.value) if pid.value else None


def _process_name_from_pid(kernel32: ctypes.WinDLL, pid: int) -> str | None:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        size = wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        if not kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return Path(buffer.value).name.lower()
    finally:
        kernel32.CloseHandle(handle)


def _process_parent_table(kernel32: ctypes.WinDLL) -> dict[int, tuple[str, int]]:
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == INVALID_HANDLE_VALUE:
        return {}
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        table: dict[int, tuple[str, int]] = {}
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return table
        while True:
            table[int(entry.th32ProcessID)] = (entry.szExeFile.lower(), int(entry.th32ParentProcessID))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                return table
    finally:
        kernel32.CloseHandle(snapshot)


def _has_steam_ancestor(kernel32: ctypes.WinDLL, pid: int) -> bool:
    table = _process_parent_table(kernel32)
    seen: set[int] = set()
    current = pid
    for _ in range(12):
        item = table.get(current)
        if item is None:
            return False
        _, parent = item
        if parent in seen or parent == 0:
            return False
        seen.add(parent)
        parent_item = table.get(parent)
        if parent_item is None:
            return False
        parent_name, _ = parent_item
        if parent_name in STEAM_PROCESSES:
            return True
        current = parent
    return False


def get_foreground_activity() -> ActivitySnapshot | None:
    if sys.platform != "win32":
        return None

    user32 = _load_user32()
    kernel32 = _load_kernel32()
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None

    pid = _get_window_pid(user32, hwnd)
    if pid is None:
        return None

    process_name = _process_name_from_pid(kernel32, pid)
    if not process_name:
        return None

    classification = classify_monitored_process(process_name)
    stored_process_name = process_name
    if classification == "ignored" and _has_steam_ancestor(kernel32, pid):
        classification = "steam"
        stored_process_name = STEAM_LAUNCHED_PROCESS_NAME

    if classification == "ignored":
        return ActivitySnapshot(
            timestamp=_utc_timestamp(),
            process_name=stored_process_name,
            classification="ignored",
        )

    title = _get_window_text(user32, hwnd)
    domain = extract_domain_from_text(title) if classification == "chrome" else None
    return ActivitySnapshot(
        timestamp=_utc_timestamp(),
        process_name=stored_process_name,
        window_title=title,
        domain=domain,
        classification=classification,
    )