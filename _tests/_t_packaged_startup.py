"""运行真正的 exe，检查 Qt、设置窗口、音频解码与绑定保存。"""

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


root = Path(__file__).resolve().parent.parent
exe = (Path(sys.argv[1]) if len(sys.argv) > 1 else
       root / 'dist' / 'SR Voiceover Roulette.exe').resolve()
with tempfile.TemporaryDirectory(prefix='sr-exe-check-') as folder:
    report = Path(folder) / 'result.json'
    environment = dict(os.environ, QT_QPA_PLATFORM='offscreen',
                       __COMPAT_LAYER='RunAsInvoker')
    result = subprocess.run([str(exe), '--check-startup', str(report)],
                            env=environment, cwd=folder, timeout=35,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert result.returncode == 0, f'exe 启动检查失败：{result.returncode}'
    data = json.loads(report.read_text(encoding='utf-8'))
    assert data['ok'], data
    print(json.dumps(data, ensure_ascii=False, indent=2))
