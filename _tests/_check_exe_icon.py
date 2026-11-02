"""从 exe 资源里把图标抠出来，确认嵌进去的到底是新图标还是旧图标。

用 ExtractIconExW 取 HICON，再用 GetDIBits 读像素，
不依赖任何第三方库，也不需要管理员权限。
"""

import ctypes
import sys
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

shell32 = ctypes.WinDLL("shell32", use_last_error=True)
user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

# 64 位下句柄是 8 字节，不声明 argtypes 会被截断成 int 然后 OverflowError
shell32.ExtractIconExW.argtypes = [
    wintypes.LPCWSTR, ctypes.c_int,
    ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.HICON), wintypes.UINT,
]
shell32.ExtractIconExW.restype = wintypes.UINT
user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.c_void_p]
user32.GetIconInfo.restype = wintypes.BOOL
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.GetObjectW.argtypes = [wintypes.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
gdi32.GetObjectW.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [
    wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
    ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", ctypes.c_void_p),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", BITMAPINFOHEADER), ("bmiColors", wintypes.DWORD * 3)]


def icon_pixels(hicon):
    """返回 (宽, 高, 像素函数)。像素顺序 BGRA，行从下往上。"""
    ii = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(ii)):
        raise OSError("GetIconInfo 失败")

    bmp = BITMAP()
    gdi32.GetObjectW(ii.hbmColor, ctypes.sizeof(BITMAP), ctypes.byref(bmp))
    w, h = bmp.bmWidth, bmp.bmHeight

    bmi = BITMAPINFO()
    bmi.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.bmiHeader.biWidth = w
    bmi.bmiHeader.biHeight = -h  # 负数 = 从上到下存
    bmi.bmiHeader.biPlanes = 1
    bmi.bmiHeader.biBitCount = 32
    bmi.bmiHeader.biCompression = 0  # BI_RGB

    buf = ctypes.create_string_buffer(w * h * 4)
    hdc = user32.GetDC(None)
    got = gdi32.GetDIBits(hdc, ii.hbmColor, 0, h, buf, ctypes.byref(bmi), 0)
    user32.ReleaseDC(None, hdc)
    if got == 0:
        raise OSError("GetDIBits 失败")
    return w, h, buf


def dominant(w, h, buf) -> tuple[int, int, int, int]:
    """统计不透明像素里出现最多的颜色。"""
    counts: dict[tuple[int, int, int], int] = {}
    raw = buf.raw
    for i in range(0, len(raw), 4):
        b, g, r, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
        if a > 200:
            key = (r, g, b)
            counts[key] = counts.get(key, 0) + 1
    if not counts:
        return (0, 0, 0, 0)
    color = max(counts, key=lambda k: counts[k])
    return (*color, counts[color])


def main() -> int:
    exe = ROOT / "SR Voiceover Roulette_发布版" / "SR Voiceover Roulette.exe"
    if not exe.exists():
        print(f"找不到 {exe}")
        return 1

    big = (wintypes.HICON * 1)()
    small = (wintypes.HICON * 1)()
    n = shell32.ExtractIconExW(str(exe), 0, big, small, 1)
    print(f"ExtractIconEx 返回 {n} 个图标")
    if n == 0 or not big[0]:
        print("exe 里没有图标资源")
        return 1

    w, h, buf = icon_pixels(big[0])
    r, g, b, cnt = dominant(w, h, buf)
    print(f"图标尺寸 {w}x{h}")
    print(f"主色 RGB = ({r}, {g}, {b})  覆盖 {cnt} 个不透明像素")
    is_green = g > r + 40 and g > b + 20
    is_orange = r > 200 and g < 180
    print("判定：", "绿色（新图标）" if is_green else ("橙色（旧图标）" if is_orange else "无法判定"))

    user32.DestroyIcon(big[0])
    if small[0]:
        user32.DestroyIcon(small[0])

    # 顺便把几种尺寸都导出来看看
    total = shell32.ExtractIconExW(str(exe), -1, None, None, 0)
    print(f"exe 共含 {total} 个图标条目")
    return 0 if is_green else 2


if __name__ == "__main__":
    raise SystemExit(main())
