# -*- coding: utf-8 -*-
"""Abaqus Codex Assistant 的核心程序包。"""

__version__ = "0.2.2a1"

# Windows 安装版把可选依赖放在当前用户的数据目录。源码安装和普通
# site-packages 安装不改变解释器的搜索路径。
try:
    from abaqus_codex.paths import activate_user_python_packages

    activate_user_python_packages()
except (OSError, RuntimeError):
    # 环境体检会给出可操作的诊断；包导入本身不应因可选目录异常而失败。
    pass
