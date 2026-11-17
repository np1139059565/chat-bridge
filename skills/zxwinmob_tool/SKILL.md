# zxwinmob_tool — zxwinmob 容器环境操作

通过 SSH 连到 paas-controller，再经 kubectl 操作 ranoss 命名空间下的 zxwinmob 业务容器：查 Pod、进容器执行命令、拷文件、重启进程、部署 web 安装包。

## 能力

| 工具 | 用途 |
| --- | --- |
| `zxw_list_pods` | 列出 Pod（含 IP、节点），可按关键字过滤 |
| `zxw_exec` | 在容器内执行 shell 命令 |
| `zxw_ls` | 列出容器工作目录 |
| `zxw_restart` | 重启容器内 java 进程 |
| `zxw_push` | 把控制器上的文件拷进容器 |
| `zxw_deploy_start` | 后台启动一次部署，返回 task_id |
| `zxw_deploy_status` | 查部署任务状态与日志 |

## 环境

| 别名 | IP | 说明 |
| --- | --- | --- |
| `69` | 10.227.105.69 | 集群 A 控制器 |
| `86` | 10.227.105.86 | 集群 B 控制器 |
| `102` | 10.220.50.102 | 集群 C 控制器，安装包存放于此 |
| `192` | 10.232.56.192 | 新环境控制器（paas-controller-1） |

登录信息统一：`ubuntu` / `UbuntU1!2@3#4$`，命名空间默认 `ranoss`，容器工作目录 `/home/zxwinmob`。

## 处理要求

1. 若本次会话尚未阅读过本说明，先用 `read_skill`（`skill=zxwinmob_tool`、`path=SKILL.md`）读取。
2. 调用前先用 `get_tool_params` 查参数名，不臆造别名。
3. 进容器执行命令走 `zxw_exec`，脚本已自动补 `--`；新版 kubectl 缺 `--` 会直接报错。
4. 部署分两步：先 `zxw_deploy_start` 拿 task_id，再轮询 `zxw_deploy_status`。部署耗时远超单次工具 60 秒上限，脚本型工具硬超时会杀进程树，因此部署动作在控制器后台执行。
5. 重启遵循容器既有机制：杀掉 java 进程，`start.sh` 的守护循环会在 3 秒内用新 jar 拉起，不要自行改动启动方式。
6. 容器内 `ps -ef` 的 PID 在第 1 列（格式 `PID USER TIME CMD`），取进程号时按第 1 列取。

## 典型流程

部署一个 web 包到某套环境：

1. `zxw_list_pods` 确认目标 Pod 在跑。
2. 确认安装包已在控制器 `~/lcy/` 下。
3. `zxw_deploy_start`（`host` 目标机、`pod` 传关键字、`match=true`、`zip-name`、`zip-host` 包所在机）。
4. 反复 `zxw_deploy_status` 直到 `state` 为 `SUCCESS` 或 `FAILED`。
5. `zxw_exec` 看应用日志确认启动正常。

## 实测参考

以 427MB 的 cclo.jar 为基准，单次部署（含跨机中转、解包、重打包、重启）约 60 秒。
`zxw_deploy_start` 本身秒级返回，耗时都在后台任务里。

包不在目标机时（如包在 102、部署到 69/86），`zip-host` 指定源机，脚本经 SFTP 自动中转，无需手工拷包。

## 已知边界

- 容器内无 `curl` / `wget`，验证应用存活用 `ps -ef` 看 java 进程或读 `log/<日期>/cclo.info.log`。
- 健康检查脚本 `livenessCheck.sh` 在容器内缺依赖，返回 127，不作为判断依据。
- 部署完成后 `cclo.jar.bak` 保留在容器内，可作为回滚备份。
