"""内置指令 /new1：新建会话并接续任务。

职责：定义 /new1 的步骤与执行入口。

为什么单独成文件：它是一条由多步组成的指令，步骤与语义说明本身有篇幅；
而 command_panel.py 已接近行数上限，混在一起会挤占主流程的可读性。

依赖说明：/new1 的第一步 /new 是站点点击指令，刻意留在 definition.yaml
的自定义区（选择器随站点改版调整，不适合写死在代码里）；后两步
/csp 与 /sa 是内置指令。执行统一交 command_panel 的组合执行器。
"""

# /new1 的步骤定义：提权为内置后固定在此，不受设置页增删自定义指令影响。
# 语义是「开一个新会话并把任务接着做下去」：
#   1) /new  点站点的新建对话按钮，切到空白会话；
#   2) /csp  复制上一轮的系统提示词，使新会话延续同一套规则；
#   3) /sa on 打开自动回传，新会话里的卡片才会自动执行。
# 间隔取 5 秒：新建会话后网页要重新渲染，太短会在按钮尚未就绪时点击落空。
NEW1_ENTRY = {
    "name": "/new1",
    "label": "新建会话并接续任务",
    "steps": ["/new", "/csp", "/sa on"],
    "interval": 5,
}


def make_handler(run_combo):
    """构造 /new1 的处理函数。

    传入组合执行器而非直接导入，是为了避免与 command_panel 形成循环导入：
    command_panel 要在分发表里登记本函数，本函数又要调用它的执行器。

    @param run_combo 组合指令执行器，签名 (qq_client, openid, msg_id, entry)
    @returns 处理函数，签名 (qq_client, openid, arg, msg_id)
    """

    def handle(qq_client, openid, arg, msg_id):
        """逐步执行 /new → /csp → /sa on。"""
        run_combo(qq_client, openid, msg_id, NEW1_ENTRY)

    return handle
