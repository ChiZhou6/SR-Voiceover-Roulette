# -*- mode: python ; coding: utf-8 -*-
"""SR Voiceover Roulette —— 打包配置

重要：口琴谱那份 spec 把 QtMultimedia / avcodec / avformat 全部排除了，
这里绝对不能照抄，否则 exe 打包出来能弹轮盘但完全没声音。
本程序必需保留的运行时：
    QtCore / QtGui / QtWidgets / QtMultimedia / QtNetwork
    avcodec-61 / avformat-61 / avutil-59 / swresample-5 / swscale-8
    plugins\\multimedia\\ffmpegmediaplugin.dll
    libcrypto-3-x64 / libssl-3-x64（QtNetwork 依赖）

用：python -m PyInstaller --noconfirm --distpath dist --workpath build SVRoulette.spec
"""
import os

ICON = os.path.join(SPECPATH, "icon.ico")

EXCLUDES = [
    # QML / Quick 系列（纯 QWidget 绘制用不到）
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtQuickControls2", "PySide6.QtMultimediaWidgets",
    # Web
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebView", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    # 3D
    "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.Qt3DInput", "PySide6.Qt3DLogic",
    # 其他用不到的大件
    "PySide6.QtSpatialAudio", "PySide6.QtNetworkAuth",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtDBus",
    "PySide6.QtPrintSupport", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtDesigner", "PySide6.QtUiTools", "PySide6.QtHelp",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus",
    "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtRemoteObjects", "PySide6.QtStateMachine", "PySide6.QtScxml",
    "PySide6.QtSensors", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtTextToSpeech", "PySide6.QtConcurrent", "PySide6.QtHttpServer",
    "PySide6.QtGraphs", "PySide6.QtVirtualKeyboard",
    "tkinter",
]

# 按小写子串匹配的二进制 / 数据黑名单
# ⚠️ 绝对不能删：qt6core / qt6gui / qt6widgets / qt6multimedia / qt6network
#    avcodec / avformat / avutil / swresample / swscale / plugins\multimedia
#    python313.dll / platforms\qwindows.dll / shiboken6.*
DROP = [
    "opengl32sw.dll",
    "qt6quick", "qt6qml", "qt6qmlmodels", "qt6qmlworkerscript",
    "qt6pdf", "qt6opengl", "qt6openglwidgets",
    "qt6svg", "qt6sql", "qt6test", "qt6xml", "qt6dbus", "qt6print",
    "qt6websockets", "qt6webchannel", "qt6webview", "qt6webengine",
    "qt6charts", "qt6datavisualization",
    "qt63d", "qt6sensors", "qt6positioning", "qt6location", "qt6texttospeech",
    "qt6concurrent", "qt6httpserver", "qt6graphs", "qt6remoteobjects",
    "qt6statemachine", "qt6designer", "qt6help", "qt6uitools",
    "qt6serialport", "qt6serialbus", "qt6bluetooth", "qt6nfc",
    "qt6spatialaudio", "qt6virtualkeyboard", "qt6scxml",
    "qt6labswavefrontmesh", "qt6labssettings", "qt6labssharedimage",
    "qt6labscalendar", "qt6shadertools", "qt6networkauth", "qt6qmlnetwork",
    # 只给 QML 视频输出用的 multimedia 扩展，保留核心 qt6multimedia 不动
    "qt6multimediaquick", "qt6multimediawidgets",
    # 对应的 PySide6 扩展
    "pyside6\\qtquick", "pyside6\\qtqml", "pyside6\\qtpdf", "pyside6\\qtsvg",
    "pyside6\\qtsql", "pyside6\\qttest", "pyside6\\qtxml", "pyside6\\qtdbus",
    "pyside6\\qtprintsupport", "pyside6\\qtcharts", "pyside6\\qt3d",
    "pyside6\\qtwebengine", "pyside6\\qtconcurrent", "pyside6\\qtuitools",
    "pyside6\\qtscxml", "pyside6\\qttexttospeech", "pyside6\\qtbluetooth",
    "pyside6\\qtpositioning", "pyside6\\qtsensors",
    "pyside6\\qtmultimediawidgets", "pyside6\\qtnetworkauth", "pyside6\\qtopengl",
    # 用不到的插件（保留 qwindows / qmodernwindowsstyle / qico / qjpeg）
    "plugins\\sqldrivers", "plugins\\tls", "plugins\\networkinformation",
    "plugins\\platforms\\qdirect2d", "plugins\\platforms\\qminimal",
    "plugins\\platforms\\qwebgl",
    "plugins\\imageformats\\qpdf", "plugins\\imageformats\\qsvg",
    "plugins\\imageformats\\qtga", "plugins\\imageformats\\qtiff",
    "plugins\\imageformats\\qwbmp", "plugins\\imageformats\\qwebp",
    "plugins\\imageformats\\qicns", "plugins\\imageformats\\qgif",
    "plugins\\generic", "plugins\\iconengines",
    "pyside6\\translations", "translations\\qt",
]


def _keep(name: str) -> bool:
    low = name.lower().replace("/", "\\")
    return not any(s in low for s in DROP)


a = Analysis(
    ["sr_roulette.py"],
    pathex=[],
    binaries=[],
    datas=[],
    # settings_window 是在函数里延迟导入的（避免和主模块循环依赖），
    # 显式列出来免得静态分析漏掉
    hiddenimports=[
        "PySide6.QtMultimedia", "PySide6.QtNetwork",
        "settings_window", "sounds_config", "theme",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

_before = len(a.binaries)
a.binaries = [b for b in a.binaries if _keep(b[0])]
a.datas = [d for d in a.datas if _keep(d[0])]
print(f"[瘦身] binaries {_before} -> {len(a.binaries)} ; datas -> {len(a.datas)}")

# 打包后自检：这几个文件少一个，exe 就会没声音
REQUIRED = [
    "qt6multimedia", "qt6network", "avcodec", "avformat", "avutil",
    "swresample", "swscale", "ffmpegmediaplugin",
]
kept = " ".join(b[0].lower() for b in a.binaries)
missing = [r for r in REQUIRED if r not in kept]
if missing:
    print(f"[警告] 以下音频相关文件没有进包，exe 将无法播放音效: {missing}")
else:
    print("[自检] 音频链路所需文件齐全")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SR Voiceover Roulette",
    icon=ICON if os.path.exists(ICON) else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # 不开 UPX：压缩过的 exe 更容易被杀软误报
    console=False,          # 不弹黑框
    # 需要管理员权限：游戏/语音软件常以管理员身份跑，普通权限的进程在它们面前
    # 读键、抢焦点、拿设备都会被 UIPI 挡一道。写进清单后双击就会弹 UAC 提权。
    uac_admin=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
