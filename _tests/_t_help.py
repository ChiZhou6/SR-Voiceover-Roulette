"""说明页测试：4 个折叠分区、展开后不切字、链接正确、标签页已注册。"""
import os
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PySide6.QtWidgets import QApplication, QLabel, QPushButton

import sounds_config as sc
import sr_roulette as sr

RATE = 48000
app = QApplication.instance() or QApplication([])
FAILS = []


def check(ok, what, detail=""):
    print(("PASS  " if ok else "FAIL  ") + what + (f"   [{detail}]" if detail and not ok else ""))
    if not ok:
        FAILS.append(what)


def write_wav(path, seconds, freq=440.0):
    n = int(seconds * RATE)
    t = np.arange(n) / RATE
    x = (0.4 * np.sin(2 * np.pi * freq * t) * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(x.tobytes())


import settings_window as sw

# ---- 1. 页面结构 ----
page = sw.HelpPage()
page.resize(440, 720)
page.show()
app.processEvents()
check(len(page.sections) == 4, "有 4 个折叠分区", str(len(page.sections)))
titles = [s.title for s in page.sections]
check(titles == ["一、安全声明", "二、开发者说明", "三、详细使用教程", "四、常见问题"],
      "四个分区标题与顺序正确", str(titles))
check(all(not s.body.isVisibleTo(page) for s in page.sections[:3]),
      "前三节默认收起")
check(page.sections[3].body.isVisibleTo(page), "「四、常见问题」默认展开（遇到问题第一眼就能看到）")
check(page.sections[3].hot is True, "「四、常见问题」带主题色标记")
check(page.sections[0].head.text().startswith("▶"), "收起时是 ▶",
      page.sections[0].head.text())
check(page.sections[3].head.text().startswith("▼"), "常见问题默认是 ▼",
      page.sections[3].head.text())

heads = [l.text() for l in page.findChildren(QLabel)]
check(any("迟昼" in t and "缪缪缪尔赛思" in t for t in heads), "顶部写明了作者与 B 站账号")
check(any("仅供娱乐，安全性请使用者自行判断" in t for t in heads),
      "顶部写明了仅供娱乐 / 自行判断")
btns = [b.text() for b in page.findChildren(QPushButton)]
check("全部展开" not in btns and "全部收起" not in btns, "顶部两个按钮已删掉", str(btns[:5]))

# ---- 2. 展开 ----
for sec in page.sections:
    sec.set_expanded(True)
app.processEvents()
check(all(s.body.isVisibleTo(page) for s in page.sections), "全部展开后 4 个内容区都可见")
check(page.sections[0].head.text().startswith("▼"), "展开后是 ▼",
      page.sections[0].head.text())

# 文字没被切：每段实际高度 >= 按宽度算出来的需要高度
clipped = []
for sec in page.sections:
    for lab in sec._labels:
        if not lab.isVisibleTo(page):
            continue
        need = lab.minimumHeight()
        if lab.height() + 1 < need:
            clipped.append((sec.title, lab.text()[:14], lab.height(), need))
check(not clipped, "展开后没有文字被切掉", str(clipped[:3]))

# ---- 3. 内容要点 ----
def all_text(sec):
    return "\n".join(l.text() for l in sec._labels)


t1 = all_text(page.sections[0])
check("缪缪缪尔赛思" not in t1, "安全声明里没有混进作者名")
check("不联网、不注入、不模拟按键" in t1, "安全声明写明了不联网/不注入/不模拟按键")
check("HKEY_CURRENT_USER" in t1, "安全声明如实交代了注册表那一项")
check("sr_roulette.log" in t1, "安全声明列了日志文件")
check("它做了什么（可自行核对）" in t1, "有「它做了什么」小节")
check("Raw Input" in t1 and "不拦截、不屏蔽、不转发、不模拟" in t1,
      "写清了只读按键、不拦截不模拟")
check("不写系统目录" in t1 and "不装驱动" in t1, "写清了不写系统目录/不装驱动")
check("它写了哪些文件（可自行核对）" in t1, "文件小节标题正确")
check("必要提醒" in t1, "有「必要提醒」小节")
check("和游戏官方没有任何关系" in t1, "提醒了与游戏官方无关")
check("风险由你判断并承担" in t1, "提醒了风险自担")
check("误导对手" in t1, "提醒了竞技对局里用音效的问题")
# 三段顺序：做了什么 -> 写了哪些文件 -> 必要提醒
i_did = t1.index("它做了什么")
i_file = t1.index("它写了哪些文件")
i_warn = t1.index("必要提醒")
check(i_did < i_file < i_warn, "小节顺序：做了什么 → 写了哪些文件 → 必要提醒",
      f"{i_did}/{i_file}/{i_warn}")

t2 = all_text(page.sections[1])
check("迟昼" in t2 and "缪缪缪尔赛思" in t2, "开发者署名与 B 站账号正确")
check("AI" in t2, "写明了 AI 项目")

t3 = all_text(page.sections[2])
check("5｜调每个音效" in t3, "教程第 5 节标题改成「调每个音效」")
check("5｜调每个人的声音" not in t3, "没有残留旧标题")
check("VB-CABLE" in t3, "教程提到 VB-CABLE")

t4 = all_text(page.sections[3])
check(t4.count("Q") >= 10, "常见问题至少 10 条", str(t4.count("Q")))

# ---- 4. 链接 ----
links = []
for sec in page.sections:
    for w in sec.findChildren(object):
        pass
urls = [l.text() for l in page.findChildren(QLabel) if "href" in l.text()]
check(any("vb-audio.com/Cable" in u for u in urls), "VB-CABLE 链接存在", str(urls[:2]))
check(any(l.openExternalLinks() for l in page.findChildren(QLabel) if "href" in l.text()),
      "链接可点开（openExternalLinks）")

# ---- 5. 全部收起后能再展开（反复横跳不退化）----
for sec in page.sections:
    sec.set_expanded(False)
app.processEvents()
check(all(not s.body.isVisibleTo(page) for s in page.sections), "全部收起生效")
for _ in range(3):
    for sec in page.sections:
        sec.set_expanded(True)
        sec.set_expanded(False)
page.sections[2].head.click()
app.processEvents()
check(page.sections[2].body.isVisibleTo(page), "反复切换后单独点开仍然正常")

# 收起来再展开，高度必须重新量（不然第二次展开文字会被压扁）
page.sections[2].set_expanded(False)
app.processEvents()
page.sections[2].set_expanded(True)
app.processEvents()
bad = [lab.text()[:12] for lab in page.sections[2]._labels
       if lab.isVisibleTo(page) and lab.height() + 1 < lab.minimumHeight()]
check(not bad, "收起再展开后文字高度仍然正确", str(bad[:3]))

# ---- 6. 标签页注册 ----
tmp = Path(tempfile.mkdtemp())
snd = tmp / "sounds"
snd.mkdir()
write_wav(snd / "01 测试.wav", 0.6)
sr.SOUNDS_DIR = snd
cfg = sc.SoundsConfig(tmp / "sounds.json")
cfg.load()
cfg.sync([p.name for p in snd.iterdir()])
bank = sr.SoundBank(8, scfg=cfg)
win = sw.SettingsWindow(dict(sr.DEFAULT_CONFIG), cfg, bank, None)
names = [win.tabs.tabText(i) for i in range(win.tabs.count())]
check(names == ["音效库", "快捷键", "轮盘", "麦克风", "说明"],
      "标签页顺序：说明排在最后", str(names))
check(win.tabs.widget(4) is win.page_help, "第 5 个标签就是说明页")
win.close()

print()
if FAILS:
    print(f"失败 {len(FAILS)} 项：")
    for f in FAILS:
        print("  -", f)
    sys.exit(1)
print("全部通过")
