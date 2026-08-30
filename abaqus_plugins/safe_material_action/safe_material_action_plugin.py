# -*- coding: utf-8 -*-
"""在 Abaqus/CAE 2021 GUI 主事件循环中转发固定安全动作。"""

import io
import json
import os
import re
import time

from abaqusConstants import ALL
from abaqusGui import FXMAPFUNC, FXObject, SEL_COMMAND, SEL_TIMEOUT, getAFXApp, sendCommand


STATUS_SCHEMA = "abaqus-codex-safe-action-status/1"
REQUEST_ID_PATTERN = re.compile(r"^cmd_(aca_[0-9a-f]{20})\.json$")
POLL_MILLISECONDS = 250


def _home():
    """返回固定本地协议目录。"""

    base = os.environ.get("LOCALAPPDATA", "").strip() or os.path.expanduser("~")
    return os.path.join(base, "AbaqusCodexAssistant", "safe_actions")


def _ensure(path):
    """兼容 Python 2.7 地创建固定目录。"""

    if os.path.isdir(path):
        return
    try:
        os.makedirs(path)
    except OSError:
        if not os.path.isdir(path):
            raise


def _write_status():
    """写入短期心跳，让桌面端在发请求前确认 GUI 在线。"""

    home = _home()
    _ensure(home)
    path = os.path.join(home, "status.json")
    temporary = path + ".tmp"
    value = {
        "schema": STATUS_SCHEMA,
        "version": "0.2.1",
        "abaqus_release": "2021",
        "status": "running",
        "timestamp": time.time(),
        "pid": os.getpid(),
        "message": "safe material action event loop",
    }
    encoded = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    if not isinstance(encoded, bytes):
        encoded = encoded.encode("ascii")
    with io.open(temporary, "wb") as stream:
        stream.write(encoded)
        stream.flush()
    try:
        os.rename(temporary, path)
    except OSError:
        # Windows 的 rename 不覆盖；状态文件不含用户数据，可先替换旧心跳。
        try:
            os.remove(path)
        except OSError:
            pass
        os.rename(temporary, path)


def _claim_one():
    """优先领取已确认写请求，其次领取只读材料请求。"""

    home = _home()
    processing = os.path.join(home, "processing")
    _ensure(processing)
    for folder_name in ("approved", "requests"):
        folder = os.path.join(home, folder_name)
        if not os.path.isdir(folder):
            continue
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            continue
        for name in names:
            match = REQUEST_ID_PATTERN.match(name)
            if match is None:
                continue
            source = os.path.join(folder, name)
            destination = os.path.join(processing, name)
            try:
                os.rename(source, destination)
            except OSError:
                continue
            return match.group(1)
    return None


class SafeActionPump(FXObject):
    """使用 FOX 定时器在 GUI 主线程中处理一个待办请求。"""

    ID_TIMEOUT = 1001
    ID_MANUAL = 1002

    def __init__(self):
        FXObject.__init__(self)
        # Abaqus/FOX 的 Python 绑定在实例上登记回调，兼容 2021。
        # 传入未绑定类方法；若传 self.onTimeout，FOX 2021 会额外多传一个 self。
        FXMAPFUNC(self, SEL_TIMEOUT, self.ID_TIMEOUT, SafeActionPump.onTimeout)
        FXMAPFUNC(self, SEL_COMMAND, self.ID_MANUAL, SafeActionPump.onManual)
        self._schedule()

    def _schedule(self):
        """安排下一次短轮询；没有阻塞等待。"""

        getAFXApp().addTimeout(POLL_MILLISECONDS, self, self.ID_TIMEOUT)

    def _process_one(self):
        """只把安全请求 ID 写进固定 Kernel 函数调用。"""

        _write_status()
        request_id = _claim_one()
        if request_id is None:
            return False
        plugin_directory = os.path.dirname(os.path.abspath(__file__))
        command = (
            "import sys\n"
            "_aca_plugin_directory = %r\n"
            "if _aca_plugin_directory not in sys.path: "
            "sys.path.insert(0, _aca_plugin_directory)\n"
            "import safe_material_action_kernel\n"
            "safe_material_action_kernel.process_request(%r)\n"
            % (plugin_directory, request_id)
        )
        sendCommand(command)
        return True

    def onTimeout(self, sender, selector, data):
        """定时处理后总是重新安排；异常不阻断 Abaqus GUI。"""

        try:
            self._process_one()
        except Exception:
            pass
        self._schedule()
        return 1

    def onManual(self, sender, selector, data):
        """高级用户可从菜单手动处理一个请求。"""

        try:
            self._process_one()
        except Exception:
            pass
        return 1


# 保留模块级引用，避免 FOX 回调对象被回收。
SAFE_ACTION_PUMP = SafeActionPump()
toolset = getAFXApp().getAFXMainWindow().getPluginToolset()
toolset.registerGuiMenuButton(
    object=SAFE_ACTION_PUMP,
    buttonText="Abaqus Codex Assistant|Process One Pending Safe Action",
    messageId=SafeActionPump.ID_MANUAL,
    applicableModules=ALL,
    version="0.2.1",
    author="1721780603-cell and contributors",
    description="Process one validated material action in the GUI event loop.",
)
