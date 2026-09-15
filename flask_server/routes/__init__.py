"""
路由包：按功能域拆分 server.py 的路由注册。

各子模块定义 Flask 蓝图，由 app.py 统一注册到应用：
- tools.py        /tools、/tool（内置 + 自定义工具调用）
- prompts.py      /prompt_sections、/hot_fix、/（首页）
- config_route.py /config（配置读写）
- custom_tools.py /custom_tools 系列
- rules.py        /rules 系列
- cards.py        /api/cards 系列（原 routes_cards.py）
- ext.py          外部工具提供方通道（原 routes_ext.py）
"""
