"""SR Voiceover Roulette - 端到端测试

真实启动主程序，然后：
  1. 用 SendInput 按住 Y 超过长按阈值
  2. 枚举该进程的窗口，确认轮盘窗口真的出现了
  3. 断言轮盘的窗口样式含 LAYERED | TRANSPARENT | NOACTIVATE
     （这三条就是"画得出来、不挡鼠标、不抢焦点"的全部依据）
  4. 松开 Y，确认窗口消失
  5. 清理进程

注意：SendInput 只出现在测试脚本里，产品代码永远不模拟输入。

运行：python _tests/_t_e2e.py
"""

import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_NOACTIVATE = 0x08000000

VK_Y = 0x59
KEYEVENTF_KEYUP = 0x0002

FAILS: list[str] = []


def check(cond: bool, label: str, detail: str = "") -> None:
    mark = "PASS" if cond else "FAIL"
    print(f"  [{mark}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        FAILS.append(label)


# ---------------------------------------------------------------- SendInput

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _UNION(ctypes.Union):
    _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _UNION)]


def send_key(vk: int, up: bool) -> None:
    inp = INPUT()
    inp.type = 1  # INPUT_KEYBOARD
    inp.ki.wVk = vk
    inp.ki.wScan = user32.MapVirtualKeyW(vk, 0)
    inp.ki.dwFlags = KEYEVENTF_KEYUP if up else 0
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001


def send_move(dx: int, dy: int) -> None:
    """合成相对鼠标移动。

    Raw Input 在驱动层就能收到合成输入，所以这条路径足以验证
    "程序确实在旁听鼠标硬件位移"，不需要真的动手。
    """
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi.dx = dx
    inp.mi.dy = dy
    inp.mi.dwFlags = MOUSEEVENTF_MOVE
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def move_by(dx: int, dy: int, steps: int = 10) -> None:
    """拆成多步发送：一次性大位移在部分环境会被系统鼠标加速吃掉。"""
    sx, sy = dx // steps, dy // steps
    for _ in range(steps):
        send_move(sx, sy)


def hold_wheel(hold_sec: float = 0.45) -> None:
    send_key(VK_Y, up=False)
    time.sleep(hold_sec)


# ---------------------------------------------------------------- 窗口枚举

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

kernel32 = ctypes.windll.kernel32
TH32CS_SNAPPROCESS = 0x00000002


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [
        ("dwSize", wintypes.DWORD),
        ("cntUsage", wintypes.DWORD),
        ("th32ProcessID", wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
        ("th32ModuleID", wintypes.DWORD),
        ("cntThreads", wintypes.DWORD),
        ("th32ParentProcessID", wintypes.DWORD),
        ("pcPriClassBase", wintypes.LONG),
        ("dwFlags", wintypes.DWORD),
        ("szExeFile", ctypes.c_char * 260),
    ]


def all_processes() -> list[tuple[int, int]]:
    """返回 [(pid, parent_pid)]。"""
    snap = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap in (0, -1):
        return []
    entries: list[tuple[int, int]] = []
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32)
    ok = kernel32.Process32First(snap, ctypes.byref(pe))
    while ok:
        entries.append((pe.th32ProcessID, pe.th32ParentProcessID))
        ok = kernel32.Process32Next(snap, ctypes.byref(pe))
    kernel32.CloseHandle(snap)
    return entries


def descendants(root_pid: int) -> set[int]:
    """venv 的 Scripts\\python.exe 只是转发器，真正的 Qt 进程是它的子进程，
    所以必须按进程树收集，不能只认 Popen 拿到的那个 pid。"""
    tree = all_processes()
    result = {root_pid}
    changed = True
    while changed:
        changed = False
        for pid, ppid in tree:
            if ppid in result and pid not in result:
                result.add(pid)
                changed = True
    return result


def enum_windows_of_pid(pid: int) -> list[tuple[int, str, bool, int]]:
    found: list[tuple[int, str, bool, int]] = []

    def cb(hwnd, _lparam):
        wpid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(wpid))
        if wpid.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, buf, 256)
            visible = bool(user32.IsWindowVisible(hwnd))
            exstyle = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            found.append((hwnd, buf.value, visible, exstyle))
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found


def enum_windows_of_tree(root_pid: int) -> list[tuple[int, str, bool, int]]:
    pids = descendants(root_pid)
    out: list[tuple[int, str, bool, int]] = []
    for pid in pids:
        out.extend(enum_windows_of_pid(pid))
    return out


def wheel_windows(root_pid: int) -> list[tuple[int, str, bool, int]]:
    """轮盘窗口的特征：可见、带 WS_EX_LAYERED。"""
    return [
        (h, t, v, s) for (h, t, v, s) in enum_windows_of_tree(root_pid)
        if v and (s & WS_EX_LAYERED)
    ]


def main() -> int:
    print("=" * 56)
    print("SR Voiceover Roulette 端到端测试")
    print("=" * 56)

    check(ctypes.sizeof(INPUT) == 40, "INPUT 结构体在 x64 上为 40 字节",
          f"实际 {ctypes.sizeof(INPUT)}")

    # 前置检查：若已有实例占着单实例锁，被测程序会直接弹提示框，
    # 后面的所有断言都会变成假失败。先把它揪出来。
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateMutexW.restype = ctypes.c_void_p
    _h = _k32.CreateMutexW(None, False, "Local\\SRVoiceoverRoulette")
    busy = ctypes.get_last_error() == 183
    _k32.CloseHandle(ctypes.c_void_p(_h))
    check(not busy, "测试前没有其他实例占用单实例锁",
          "请先关掉正在运行的 SR Voiceover Roulette（含旧 exe）再测")
    if busy:
        print("\n结果：环境不干净，测试中止")
        return 3

    log_path = ROOT / "_tests" / "_e2e_child.log"
    log_fh = open(log_path, "w", encoding="utf-8", errors="replace")  # noqa: SIM115

    def child_log() -> str:
        try:
            return log_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    from PySide6.QtMultimedia import QMediaDevices  # noqa: F401  仅为确认测试机装有音频后端

    print("\n启动主程序（子进程输出写入 _tests/_e2e_child.log）...")

    # ---- 配置隔离：用一份干净的测试配置跑子进程，测完还原 ----
    # 不隔离的话：用户真实配置里 open_settings_on_start=true 会让
    # 配置窗口在启动时弹出，轮询器进入暂停，整个 e2e 全部假失败；
    # mic_enabled=true 还会占用真实麦克风。
    cfg_path = ROOT / "config.json"
    cfg_backup = None
    try:
        if cfg_path.exists():
            cfg_backup = cfg_path.read_text(encoding="utf-8")
    except Exception:
        cfg_backup = None
    test_cfg = {
        "config_version": 3,
        "hotkey": "y",
        "open_settings_on_start": False,
        "mic_enabled": False,
        "autostart": False,
        "volume": 0.8,
    }
    try:
        cfg_path.write_text(
            json.dumps(test_cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass   # 写不了就用现状跑（可能假失败，但别把测试挡死）

    proc = subprocess.Popen(
        [PYTHON, str(ROOT / "sr_roulette.py")],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONUNBUFFERED": "1", "SR_DEBUG": "1"},
        stdout=log_fh,
        stderr=subprocess.STDOUT,
    )

    try:
        time.sleep(4.0)
        check(proc.poll() is None, "程序启动后保持运行", f"exit={proc.poll()}")

        text = child_log()
        check("[audio] 已装载" in text, "启动时完成音效解码",
              next((ln for ln in text.splitlines() if "已装载" in ln), "无日志"))
        check("RegisterRawInputDevices 失败" not in text, "Raw Input 注册成功")
        check("状态=ActiveState" in text, "音频输出已进入运行状态",
              next((ln for ln in text.splitlines() if "输出设备" in ln), "无日志"))

        before = wheel_windows(proc.pid)
        check(len(before) == 0, "未按热键时没有轮盘窗口", f"发现 {len(before)} 个")

        print("\n按住 Y（450ms）...")
        hold_wheel()
        during = wheel_windows(proc.pid)
        check(len(during) == 1, "长按后出现 1 个轮盘窗口", f"发现 {len(during)} 个")
        if not during:
            print(f"    调试：该进程树全部窗口 = {enum_windows_of_tree(proc.pid)}")

        if during:
            hwnd, _title, _vis, exstyle = during[0]
            check(bool(exstyle & WS_EX_LAYERED), "样式含 WS_EX_LAYERED（透明分层）")
            check(bool(exstyle & WS_EX_TRANSPARENT), "样式含 WS_EX_TRANSPARENT（鼠标穿透）")
            check(bool(exstyle & WS_EX_NOACTIVATE), "样式含 WS_EX_NOACTIVATE（不抢焦点）")

            rect = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            check(w == 408 and h == 408, "窗口尺寸符合 wheel_radius 配置", f"{w}x{h}")

            # 弹在屏幕正中：先把光标挪到远离中心的地方，确认轮盘不会跟着跑
            geo = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
            want_cx, want_cy = geo[0] // 2, geo[1] // 2
            got_cx = (rect.left + rect.right) // 2
            got_cy = (rect.top + rect.bottom) // 2
            check(abs(got_cx - want_cx) <= 2 and abs(got_cy - want_cy) <= 2,
                  "轮盘居中于屏幕", f"中心({got_cx},{got_cy}) 屏幕中心({want_cx},{want_cy})")

            fg = user32.GetForegroundWindow()
            check(fg != hwnd, "轮盘没有成为前台窗口（游戏焦点不被抢）")

        print("\n松开 Y ...")
        send_key(VK_Y, up=True)
        # 松手后有 200ms 的"闪出"动画，播完才真正 hide（实测 210ms）。
        # 但 up 事件的检测、动画收尾和这里的窗口枚举之间有几拍抖动，
        # 0.35 秒会随机误报成"没隐藏"（旧版代码也一样）。留足 2 秒再断言。
        time.sleep(2.0)
        after = wheel_windows(proc.pid)
        check(len(after) == 0, "松开后轮盘已隐藏", f"发现 {len(after)} 个")

        # ---- 核心新功能：Raw Input 驱动虚拟光标选择 ----
        # 5 个扇区、每个 72°，正上=0 正右=1 正下=2 正左=3。
        # 位移取大一些，让信号远大于环境里的真实鼠标微动。
        print("\n先做基线：长按 0.6 秒完全不移动，虚拟光标应留在中心不选中任何扇区")
        mark = len(child_log())
        hold_wheel(0.6)
        time.sleep(0.15)
        send_key(VK_Y, up=True)
        time.sleep(0.3)
        idle_selects = [ln for ln in child_log()[mark:].splitlines() if "[select]" in ln]
        check(not idle_selects, "静止时不会自己选中任何扇区",
              "; ".join(idle_selects[:3]) if idle_selects else "")

        print("\n验证鼠标方向 -> 扇区（每次重新长按，虚拟光标从中心起步）")
        # 扇区数取决于 sounds 里有多少个音效，不能写死编号，
        # 否则用户增删音效后测试会假失败。
        sys.path.insert(0, str(ROOT))
        import sr_roulette as sr  # noqa: E402

        # 子进程轮盘上的真实扇区数 = 它日志里"已装载 N 个音效"的 N。
        # 不能按目录文件数算：用户真实 sounds.json 的 order 可能只挑了一部分。
        import re  # noqa: E402

        m = re.search(r"已装载 (\d+) 个音效", child_log())
        n_slots = int(m.group(1)) if m else max(1, len(sr.SoundBank(8)))
        check(n_slots >= 2, "拿到子进程的扇区数", f"n_slots={n_slots}")
        step = 360.0 / n_slots
        print(f"    当前 {n_slots} 个音效，每扇区 {step:.1f}°")

        def expect_sector(angle_deg: float) -> int:
            """方向角 -> 扇区号。扇区 0 从正上方开始顺时针。"""
            return int(((90.0 - angle_deg) % 360.0) // step) % n_slots

        directions = [
            ((0, -900), 90.0, "向上"),
            ((900, 0), 0.0, "向右"),
            ((0, 900), -90.0, "向下"),
            ((-900, 0), 180.0, "向左"),
        ]
        for (dx, dy), angle, label in directions:
            want = expect_sector(angle)
            hold_wheel()
            move_by(dx, dy)
            time.sleep(0.3)
            send_key(VK_Y, up=True)
            time.sleep(0.3)
            log = child_log()
            got = log.count(f"[select] {want} ")
            check(got > 0, f"{label}移动 -> 选中扇区 {want}",
                  "未出现该扇区" if got == 0 else "")
            if got == 0:
                recent = [ln for ln in log.splitlines() if "[select]" in ln][-4:]
                print(f"    调试：最近的选中记录 = {recent}")

        log = child_log()
        plays = [ln for ln in log.splitlines() if "[play]" in ln]
        check(len(plays) >= 4, "每次松开都触发了播放", f"{len(plays)} 次播放记录")

        check(proc.poll() is None, "全程未崩溃")

    finally:
        try:
            log_fh.close()
        except Exception:
            pass
        # 转发器 + 子进程都要清掉，否则残留的 python 会继续占着托盘
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                capture_output=True, timeout=10,
            )
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        # 还原用户的真实配置（子进程启动时 save_config 会把测试配置写回盘上）
        try:
            if cfg_backup is not None:
                cfg_path.write_text(cfg_backup, encoding="utf-8")
            else:
                cfg_path.unlink(missing_ok=True)
        except Exception:
            pass

    print("\n" + "=" * 56)
    if FAILS:
        print(f"结果：{len(FAILS)} 项未通过")
        for f in FAILS:
            print(f"  - {f}")
        return 1
    print("结果：全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
