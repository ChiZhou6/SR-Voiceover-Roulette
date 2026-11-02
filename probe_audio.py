"""SR Voiceover Roulette - 音频环境探针

用途：在动手写任何功能前，先确认本机音频设备现状。
只读，不装驱动、不改系统、不碰游戏。

运行：python probe_audio.py
"""

import sys
import platform

from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QMediaDevices

VIRTUAL_HINTS = (
    "cable", "voicemeeter", "virtual", "vb-audio", "vaio",
    "loopback", "stereo mix", "混音",
)


def is_virtual(desc: str) -> bool:
    low = desc.lower()
    return any(h in low for h in VIRTUAL_HINTS)


def main() -> int:
    app = QApplication(sys.argv)          # noqa: F841  QMediaDevices 需要 Qt 应用实例
    print("=" * 58)
    print("SR Voiceover Roulette - 音频环境检查")
    print("=" * 58)
    print(f"系统      : {platform.system()} {platform.release()} ({platform.version()})")

    outs = QMediaDevices.audioOutputs()
    ins = QMediaDevices.audioInputs()

    print(f"\n[输出设备] 共 {len(outs)} 个")
    for d in outs:
        tag = "  <虚拟>" if is_virtual(d.description()) else ""
        default = " (系统默认)" if d == QMediaDevices.defaultAudioOutput() else ""
        print(f"  - {d.description()}{default}{tag}")

    print(f"\n[输入设备] 共 {len(ins)} 个")
    for d in ins:
        tag = "  <虚拟>" if is_virtual(d.description()) else ""
        default = " (系统默认)" if d == QMediaDevices.defaultAudioInput() else ""
        print(f"  - {d.description()}{default}{tag}")

    virt_out = [d.description() for d in outs if is_virtual(d.description())]
    virt_in = [d.description() for d in ins if is_virtual(d.description())]

    print("\n" + "-" * 58)
    if virt_in:
        print("[结论] 已发现可用的虚拟麦克风输入：")
        for name in virt_in:
            print(f"        {name}")
        print("       -> 音频链路具备条件，可以开始做混音验证。")
    else:
        print("[结论] 没有找到虚拟麦克风输入设备。")
        print("       音效无法进入游戏语音，需要先安装虚拟声卡（推荐 VB-Cable）。")
        if virt_out:
            print("       注：检测到虚拟输出但无对应输入，可能是驱动未装完整。")

    print("\n[提示] 本脚本只读取设备列表，未启动任何音频流。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
