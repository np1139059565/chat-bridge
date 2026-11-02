"""远程桥接 —— 推送目标的兜底与持久化

问题背景：
    抽屉上报（report）时只带网页侧的消息切片，并不带「这条该推给谁」——
    收件人标识（QQ openid / 微信 user_id / 企微 user）是各通道自己的概念。
    因此每条通道都要记住「最近一个跟我说话的人」，推送时用它兜底。

为什么必须持久化：
    只存内存时，服务重启后该值为空，此后的上报会因找不到推送目标而
    静默失败——表现为「AI 回了但手机收不到，重启后才恢复」。落盘后
    重启即可续用，直到用户下次发消息刷新。

本模块统一这套「记住最近用户 + 落盘 + 读回」的逻辑，各通道只需传入
自己的状态文件名，不再各写一份。
"""
import json
import threading

import paths


class TargetStore:
    """某条通道的「最近用户」记忆与持久化。

    一条通道一个实例（见文件末尾的 qq / weixin / wecom 三个实例）。
    实例内部自带锁：多条线程可能同时收到消息并登记，读写须串行。
    """

    def __init__(self, name, file_path=None):
        """构造一个目标存储。

        @param name      通道名（用于日志与默认文件名）
        @param file_path 落盘路径；不传则用 paths 下的约定位置
        """
        # 通道名：日志里据此区分是哪条通道在登记
        self.name = name
        # 落盘路径：默认放在 flask_server/data/ 下，按通道名区分
        self._path = file_path or (paths.DATA_DIR / ("target_%s.json" % name))
        # 保护 _user 的锁：多条线程可能同时登记
        self._lock = threading.Lock()
        # 最近用户标识；空串表示还没有记录
        self._user = ""
        # 首次使用时从磁盘恢复，避免重启后丢目标
        self._load()

    def _load(self):
        """从磁盘读回最近用户；文件不存在或损坏时静默跳过。"""
        try:
            raw = self._path.read_text(encoding="utf-8")
            data = json.loads(raw)
            # 只认字符串形态，其他形态一律当无记录
            if isinstance(data, dict) and isinstance(data.get("user"), str):
                self._user = data["user"]
        except Exception:
            # 首次运行没有文件、或文件损坏：都按无记录处理，不影响启动
            pass

    def _save(self):
        """把最近用户写回磁盘；失败只影响重启后的兜底，不影响本次推送。"""
        try:
            # 目录可能不存在（首次运行），先建好
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"user": self._user}, ensure_ascii=False),
                encoding="utf-8")
        except Exception:
            # 落盘失败不抛：本次推送仍可用内存值，下次登记会再试
            pass

    def note(self, user_id):
        """登记「刚跟我说话的人」，并立即落盘。

        @param user_id 用户标识；空值不覆盖既有记录
        """
        # 空值直接忽略：避免一次无标识的事件把兜底目标清空
        if not user_id:
            return
        with self._lock:
            # 与既有值相同就不重复写盘，减少无谓 IO
            if self._user == user_id:
                return
            self._user = user_id
            self._save()

    def get(self):
        """取最近用户标识；无记录返回空串。"""
        with self._lock:
            return self._user


# 三条通道各自的实例：状态互不干扰，落盘文件也各自独立。
# 放在模块级而非每个 router 里，保证同一进程内只有一份真相。
qq = TargetStore("qq")
weixin = TargetStore("weixin")
wecom = TargetStore("wecom")
