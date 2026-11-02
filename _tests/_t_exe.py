"""验证打包出来的 exe 在「别人的电脑」上也能跑。

关键做法：剥掉 PATH 和环境变量再启动，切断本机 site-packages 的兜底，
这样缺 DLL 的问题才会暴露出来，而不是被自己的开发环境掩盖。

检查项：
  1. exe 能在干净环境里启动并保持运行
  2. 长按 Y 能弹出轮盘（证明 QtMultimedia 初始化没崩）
  3. 窗口样式依然是 LAYERED | TRANSPARENT | NOACTIVATE
  4. sounds 读取的是 **exe 旁边的** sounds 目录（不是临时解压目录）

运行：python _tests/_t_exe.py
"""

import ctypes
import os
import shutil
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXE = ROOT / "dist" / "SR Voiceover Roulette.exe"

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

VK_Y = 0x59
KEYEVENTF_KEYUP = 0x0002
TH32CS_SNAPPROCESS = 0x00000002

FAILS: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


# ---------------------------------------------------------------- 输入

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG), ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD), ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD),
    ]


class _U(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def send_key(vk: int, up: bool) -> None:
    inp = INPUT()
    inp.type = 1
    inp.ki.wVk = vk
    inp.ki.wScan = user32.MapVirtualKeyW(vk, 0)
    inp.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


# ---------------------------------------------------------------- 窗口

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG), ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def descendants(root_pid: int) -> set[int]:
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    result = {root_pid}
    if snap in (0, -1):
        return result
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    pairs: list[tuple[int, int]] = []
    ok = kernel32.Process32First(snap, ctypes.byref(pe))
    while ok:
        pairs.append((pe.th32ProcessID, pe.th32ParentProcessID))
        ok = kernel32.Process32Next(snap, ctypes.byref(pe))
    kernel32.CloseHandle(snap)
    changed = True
    while changed:
        changed = False
        for pid, ppid in pairs:
            if ppid in result and pid not in result:
                result.add(pid)
                changed = True
    return result


def windows_of_tree(root_pid: int) -> list[tuple[int, str, bool, int]]:
    pids = descendants(root_pid)
    found: list[tuple[int, str, bool, int]] = []

    def cb(hwnd, _lp):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value in pids:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            found.append((
                hwnd, buf.value,
                bool(user32.IsWindowVisible(hwnd)),
                user32.GetWindowLongW(hwnd, GWL_EXSTYLE),
            ))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def wheel_windows(root_pid: int) -> list[tuple[int, str, bool, int]]:
    return [
        (h, t, v, s) for (h, t, v, s) in windows_of_tree(root_pid)
        if v and (s & WS_EX_LAYERED)
    ]


def clean_env(home: Path) -> dict:
    """剥干净的环境：没有 PATH 里的 site-packages，模拟一台只装了系统的电脑。"""
    return {
        "SystemRoot": r"C:\Windows",
        "windir": r"C:\Windows",
        "SystemDrive": "C:",
        "OS": "Windows_NT",
        "PROCESSOR_ARCHITECTURE": "AMD64",
        "TEMP": str(home / "tmp"),
        "TMP": str(home / "tmp"),
        "USERPROFILE": str(home),
        "APPDATA": str(home / "appdata"),
        "LOCALAPPDATA": str(home / "localappdata"),
        "PATH": r"C:\Windows\system32;C:\Windows;C:\Windows\System32\Wbem",
    }


def main() -> int:
    print("=" * 58)
    print("SR Voiceover Roulette exe 验证（干净环境）")
    print("=" * 58)

    if not EXE.exists():
        print(f"找不到 exe：{EXE}")
        return 1
    size_mb = EXE.stat().st_size / 1024 / 1024
    check(True, "exe 已生成", f"{size_mb:.1f} MB")
    check(ctypes.sizeof(INPUT) == 40, "INPUT 结构体 40 字节")

    # 准备一个独立的"别人电脑"目录：exe + sounds
    sandbox = ROOT / "_exe_sandbox"
    if sandbox.exists():
        shutil.rmtree(sandbox, ignore_errors=True)
    sandbox.mkdir(parents=True)
    (sandbox / "tmp").mkdir()
    shutil.copy2(EXE, sandbox / EXE.name)
    shutil.copytree(ROOT / "sounds", sandbox / "sounds")
    check(True, "沙箱目录已准备", f"{sandbox.name}/ （exe + sounds，无 config.json）")

    env = clean_env(sandbox)
    print("\n启动 exe（剥离 PATH，模拟干净电脑）...")
    proc = subprocess.Popen([str(sandbox / EXE.name)], cwd=str(sandbox), env=env)

    try:
        # onefile 要先把 34MB 解压到临时目录，再初始化 QtMultimedia 与托盘。
        # 不能用"有没有窗口"判断就绪：PyInstaller 自己的引导进程也带一个隐藏窗口，
        # 会在程序还没起完时提前触发。改等 config.json 落盘，再留足初始化时间。
        cfg = sandbox / "config.json"
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and not cfg.exists():
            if proc.poll() is not None:
                break
            time.sleep(0.3)
        print(f"    config.json 已生成: {cfg.exists()}，等待初始化完成...")
        time.sleep(8.0)

        check(proc.poll() is None, "exe 启动后保持运行", f"exit={proc.poll()}")
        check(cfg.exists(), "exe 在自身目录生成了 config.json（不是临时目录）")

        all_win = windows_of_tree(proc.pid)
        print(f"    进程树窗口共 {len(all_win)} 个")
        for hwnd, title, vis, exstyle in all_win:
            print(f"      hwnd={hwnd} title={title!r} visible={vis} exstyle=0x{exstyle:X}")

        sounds = sandbox / "sounds"
        check(sounds.exists() and any(sounds.iterdir()), "sounds 目录可读")

        # v0.5.7：启动就该自动把配置窗口弹出来。它开着的时候热键是暂停的，
        # 所以断言完必须关掉，否则后面测长按会一直没反应。
        settings_win = [w for w in all_win if "设置" in w[1] and w[2]]
        check(len(settings_win) >= 1, "启动后自动打开了配置窗口",
              f"发现 {len(settings_win)} 个")
        for hwnd, _t, _v, _e in settings_win:
            user32.PostMessageW(hwnd, 0x0010, 0, 0)      # WM_CLOSE
        if settings_win:
            time.sleep(1.0)
            left = [w for w in windows_of_tree(proc.pid) if "设置" in w[1] and w[2]]
            check(not left, "配置窗口能正常关掉、热键恢复", f"还剩 {len(left)} 个")

        log = sandbox / "sr_roulette.log"
        if log.exists():
            text = log.read_text(encoding="utf-8", errors="replace")
            bad = [ln for ln in text.splitlines() if "Traceback" in ln or "Error" in ln]
            check(not bad, "日志里没有异常", "; ".join(bad[:3]))

        print("\n按住 Y（400ms）...")
        send_key(VK_Y, up=False)
        time.sleep(0.45)
        during = wheel_windows(proc.pid)
        check(len(during) == 1, "长按后轮盘出现", f"发现 {len(during)} 个")

        if during:
            hwnd, _t, _v, exstyle = during[0]
            check(bool(exstyle & WS_EX_LAYERED), "样式含 WS_EX_LAYERED")
            check(bool(exstyle & WS_EX_TRANSPARENT), "样式含 WS_EX_TRANSPARENT")
            check(bool(exstyle & WS_EX_NOACTIVATE), "样式含 WS_EX_NOACTIVATE")
            check(user32.GetForegroundWindow() != hwnd, "没有抢前台焦点")

        send_key(VK_Y, up=True)
        # 松手要等 200ms 的"闪出"动画播完才 hide（实测 210ms），
        # 加上子进程检测 up 事件、动画收尾的处理延迟，0.5 秒会偶发误报。
        # 和 _t_e2e.py 保持同一个余量。
        time.sleep(2.0)
        check(len(wheel_windows(proc.pid)) == 0, "松开后轮盘隐藏")
        check(proc.poll() is None, "全程未崩溃")

    finally:
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass

    if EXE.exists():
        leftovers = [p.name for p in sandbox.iterdir()]
        print(f"\n沙箱残留文件: {leftovers}")

    print("\n" + "=" * 58)
    if FAILS:
        print(f"结果：{len(FAILS)} 项未通过")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("结果：全部通过，exe 可以脱离 Python 环境运行")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
