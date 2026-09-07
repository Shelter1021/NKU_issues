"""
Lab2.py
2310422 谢小珂 RNN/LSTM 姓名分类实验入口文件

用法：
1. 快速检查能否运行：
   python Lab2.py --smoke-test --device cpu

2. 重新完整训练：
   python Lab2.py --epochs 50 --device auto
"""
from pathlib import Path
import runpy
import sys

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT / "name_rnn_lstm_experiment"
SCRIPT = PROJECT / "run_experiment.py"

if not SCRIPT.exists():
    raise FileNotFoundError(f"Cannot find experiment script: {SCRIPT}")

sys.argv = [str(SCRIPT)] + sys.argv[1:]
runpy.run_path(str(SCRIPT), run_name="__main__")
