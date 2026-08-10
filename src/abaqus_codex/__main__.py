# -*- coding: utf-8 -*-
"""允许使用 python -m abaqus_codex 启动程序。"""

import sys

from abaqus_codex.cli import main


if __name__ == "__main__":
    sys.exit(main())
