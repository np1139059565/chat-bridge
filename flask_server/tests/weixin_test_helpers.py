"""微信通道测试的公共替身与夹具

抽成独立模块的原因：
    微信通道的测试按主题分在两个文件里（协议客户端 / 推送指令），
    两者都需要「不触网的微信客户端」和「清空路由进程状态」的夹具。
    放在这里避免两份重复实现——重复的替身会让两边逐渐跑偏，
    测的就不是同一份约定了。

注意：本模块不是测试文件（不以 test_ 开头），pytest 不会收集它。
"""
import os
import sys
import tempfile

# 让调用方能 import 服务端模块（与其它测试一致的做法）
_HERE = os.path.dirname(os.path.abspath(__file__))
_SERVER = os.path.dirname(_HERE)
if _SERVER not in sys.path:
    sys.path.insert(0, _SERVER)

from remote_bridge import weixin_router as router                  # noqa: E402
from remote_bridge.weixin_client import WeixinClient               # noqa: E402


class FakeWeixinClient(WeixinClient):
    """记录发送内容的微信客户端，不触网。

    继承真实客户端，确保 needs_window / send_c2c 等契约来自真实类，
    而不是在替身里另写一套（那样测的就不是真代码了）。
    """

    def __init__(self):
        # 凭证与游标指向临时文件，避免污染真实数据目录
        tmp = tempfile.gettempdir()
        super().__init__(os.path.join(tmp, 'wx_test_cred.json'),
                         os.path.join(tmp, 'wx_test_buf.txt'), None)
        self.sent = []          # [(to, text)]
        self.fail_next = False  # 置真时下一次发送失败

    def send_text(self, to_user, text, context_token=""):
        """记录发送内容；fail_next 为真时模拟一次失败。"""
        if self.fail_next:
            self.fail_next = False
            return False, "simulated_failure"
        self.sent.append((to_user, text))
        return True, {"ret": 0}


def make_msg(mid, role="assistant", text="内容"):
    """构造一条最小消息对象，供推送路由用例使用。

    @param mid   消息 id
    @param role  角色（user / assistant）
    @param text  段落正文
    @returns 消息字典
    """
    return {"id": mid, "role": role, "source": role,
            "blocks": [{"type": "paragraph", "text": text}]}


# 清空路由状态的 autouse 夹具放在 tests/conftest.py：
# 只有定义在 conftest 里才对整个测试目录生效，放在本模块只影响本模块。
