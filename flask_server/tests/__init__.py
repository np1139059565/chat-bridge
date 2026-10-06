"""测试包：让 tests/ 成为一个可导入的包，便于统一发现与运行测试。

放置约定：
- 本目录只放自动化测试，不参与服务运行时导入。
- 运行方式（在 flask_server/ 目录下）：python -m unittest discover -s tests -v
"""
