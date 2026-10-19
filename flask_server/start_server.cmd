@echo off
rem ============================================================
rem chat-bridge 本地工具服务一键启动脚本
rem 用途：双击即可启动 Flask 工具服务；启动前自动清理占用目标端口的旧进程。
rem 用法：start_server.cmd            使用配置文件里的主机与端口
rem       start_server.cmd --port 5001  临时指定端口（优先级最高）
rem       start_server.cmd --host 0.0.0.0 --port 5001
rem ============================================================

rem 把控制台代码页切换为 UTF-8，保证中文提示不乱码
chcp 65001 >nul

rem 开启变量延迟展开，便于在 if / for 块内读取最新变量值
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
rem 第三步：确定要使用的端口
rem 优先级与 server.py 保持一致：命令行 --port > runtime.yaml > 5000
rem ------------------------------------------------------------
set "PORT="
set "PREV_ARG="

rem 遍历全部命令行参数，取 --port 后面紧跟的那个值
for %%a in (%*) do (
  if /i "!PREV_ARG!"=="--port" set "PORT=%%~a"
  set "PREV_ARG=%%~a"
)

rem 命令行没给端口时，调用助手脚本读取配置里的端口
rem 单独成脚本是为了避开 cmd 里嵌套引号调用 Python 的转义陷阱
if not defined PORT (
  for /f "delims=" %%p in ('!PY_CMD! scripts\get_flask_port.py 2^>nul') do set "PORT=%%p"
)

rem 仍拿不到就退回服务端内置默认端口 5000
if not defined PORT set "PORT=5000"

echo [信息] 目标端口：!PORT!

rem ------------------------------------------------------------
rem 第四步：杀掉占用该端口的旧进程，避免端口被占导致启动失败
rem 只处理处于 LISTENING 状态的记录，取其 PID 后强制结束
rem ------------------------------------------------------------
set "PIDS="
for /f "tokens=5" %%p in ('netstat -ano ^| findstr /R /C:":!PORT! " ^| findstr /C:"LISTENING"') do (
  set "PIDS=!PIDS! %%p"
)

if defined PIDS (
  echo [提示] 端口 !PORT! 被占用，正在结束旧进程：!PIDS!
  for %%p in (!PIDS!) do (
    taskkill /F /PID %%p >nul 2>nul
    if errorlevel 1 (
      echo [警告] 结束进程 %%p 失败，可能权限不足；请以管理员身份重试。
    ) else (
      echo [信息] 已结束进程 %%p。
    )
  )
  rem 给系统一点时间释放端口，避免新进程立刻绑定失败
  timeout /t 1 /nobreak >nul
) else (
  echo [信息] 端口 !PORT! 当前空闲。
)

rem ------------------------------------------------------------
rem 第五步：启动服务，并把命令行参数原样透传给 server.py
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
