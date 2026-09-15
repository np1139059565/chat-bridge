"""
路由包：按功能域划分 HTTP 接口，各子模块定义 Flask 蓝图，由 app.py 统一注册到应用。
- tools.py        /tools、/tool（内置 + 自定义工具调用）
- prompts.py      /prompt_sections、/hot_fix、/（首页）
- config_route.py /config（配置读写）
- custom_tools.py /custom_tools 系列
- rules.py        /rules 系列
- cards.py        /api/cards 系列（外部卡片总线）
- ext.py          /api/ext/<provider> 外部工具提供方通道
"""
