# 异常与自愈（self-healing）

工具调用可能失败或返回"成功但明显不对"的结果，请按下面流程处置，不要盲目重试：

1. 若返回「成功: false」，看错误分类 origin：
   - origin=parameter：这是参数问题（缺失/类型错/取值非法）。先调用 get_tool_params 核对该工具的准确参数名，再用正确参数重试；不要去改工具代码。
   - origin=environment：路径/权限问题，确认路径与权限后重试；不要去改工具代码。
   - origin=tool_internal：这是本地工具代码自身缺陷，反复改参数无效。直接走第 3 步自愈。
2. 若返回「成功: true」但结果与你的请求明显不符（例如：你请求的路径 ≠ 返回的 directory、应为空却非空/应为非空却空、参数像被忽略），先怀疑是参数名写错：
   - 立即调用 get_tool_params 核对准确参数名，若你用了别名（如把 target_directory 写成 path），用正确参数名重试即可——这属于 parameter 问题，不是代码缺陷，不要用 hot_reload_fix。
3. 确认为工具代码缺陷（tool_internal）时，执行自愈：
   - 调用 read_tool_source（参数 tool=出问题的工具名）读取其当前源码，定位缺陷函数；
   - 调用 hot_reload_fix（参数 old_str/new_str 或 content）对 tools_impl.py 打补丁，服务会自动热重载，失败会回滚；
   - 热重载完成后，用「原参数」重新调用该工具验证。不要反复改参数。
