@echo off
rem ============================================================
rem chat-bridge 本地工具服务一键启动脚本
rem 用途：双击即可启动 Flask 工具服务，省去手打三条命令。
rem 用法：start_server.cmd            使用配置文件里的主机与端口
rem       start_server.cmd --port 5001  临时指定端口（优先级最高）
rem       start_server.cmd --host 0.0.0.0 --port 5001
rem ============================================================

rem 把控制台代码页切换为 UTF-8，保证中文提示不乱码
chcp 65001 >nul

rem 关闭命令回显后开启变量延迟展开，便于在 if 块内判断变量
setlocal enabledelayedexpansion

rem 切换到脚本自身所在目录（即 flask_server），避免从别处双击时路径错位
cd /d "%~dp0"

rem ------------------------------------------------------------
rem 第一步：挑选可用的 Python 解释器
rem 优先级：虚拟环境 .venv > py 启动器 > PATH 中的 python
rem ------------------------------------------------------------
set "PY_CMD="

rem 若项目内存在虚拟环境，优先使用它，保证依赖隔离
if exist "%~dp0.venv\Scripts\python.exe" (
  set "PY_CMD=.venv\Scripts\python.exe"
  goto :python_found
)

rem 尝试 Windows 自带的 py 启动器，明确指定 Python 3
py -3 --version >nul 2>nul
if not errorlevel 1 (
  set "PY_CMD=py -3"
  goto :python_found
)

rem 退回 PATH 中的 python 命令
python --version >nul 2>nul
if not errorlevel 1 (
  set "PY_CMD=python"
  goto :python_found
)

rem 三种方式都找不到时给出明确提示并退出
echo [错误] 未检测到可用的 Python 3，请先安装 Python 并加入 PATH。
pause
exit /b 1

:python_found
echo [信息] 使用解释器：!PY_CMD!

rem ------------------------------------------------------------
rem 第二步：检查核心依赖，缺失时自动安装
rem 只导入三个核心包做快速探测，避免每次启动都跑完整 pip
rem ------------------------------------------------------------
!PY_CMD! -c "import flask, yaml, websocket" >nul 2>nul
if errorlevel 1 (
  echo [提示] 检测到依赖缺失，正在安装 requirements.txt ...
  !PY_CMD! -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接或 pip 镜像配置。
    pause
    exit /b 1
  )
  echo [信息] 依赖安装完成。
)

rem ------------------------------------------------------------
rem 第三步：启动服务，并把命令行参数原样透传给 server.py
rem 例如 --host / --port 会被 server.py 解析并覆盖配置文件
rem ------------------------------------------------------------
echo [启动] 正在启动本地工具服务，按 Ctrl+C 可停止 ...
echo.
!PY_CMD! server.py %*

rem 记录退出码，便于排查异常退出原因
set "EXIT_CODE=%errorlevel%"
echo.
echo [结束] 服务已退出，退出码：%EXIT_CODE%

rem 双击运行时窗口默认会立刻关闭，这里暂停以便查看日志
pause
exit /b %EXIT_CODE%
