"""AI 工具调用镜像插件 —— 文件传输黑名单

职责：定义「可执行文件 / 脚本」这类不应在设备之间传输的扩展名。

为什么需要独立于 file_types 的白名单：
    file_types.PASTEABLE_EXTS 服务于「作为文本附件贴进 AI 输入框」，
    脚本与可执行文件以文本形态贴过去是无害的——AI 只会读、不会执行。
    但同一个文件作为「文件」落到手机上，就可能被误点执行，风险完全不同。

因此本清单只管「传输」这一侧：
    - push_file（电脑 → 手机）：命中即拒绝，提示先打成压缩包；
    - qq_files（手机 → 电脑）、web_file（网页 → 电脑）：命中即拒绝并回告原因。

维护：新增需要拦的类型只改这一处，三个入口同时生效。
"""

# 不应在设备之间直接传输的扩展名（小写，带前导点）。
# 覆盖 Windows 可执行体、脚本宿主、Unix 可执行脚本、移动端安装包与快捷方式。
BLOCKED_EXTS = frozenset({
    # Windows 可执行体与安装包
    ".exe", ".dll", ".sys", ".scr", ".msi", ".com", ".pif", ".cpl",
    # Windows 脚本与脚本宿主
    ".bat", ".cmd", ".ps1", ".psm1", ".psd1", ".vbs", ".vbe",
    ".js", ".jse", ".wsf", ".wsh", ".hta", ".reg", ".lnk",
    # Unix / macOS 可执行
    ".sh", ".bash", ".zsh", ".csh", ".ksh", ".command", ".app",
    ".dmg", ".pkg", ".deb", ".rpm",
    # 移动端安装包与运行包
    ".apk", ".ipa", ".jar", ".war",
})


def is_blocked(file_path):
    """判断某文件是否属于禁止传输的类型。

    @param file_path 文件路径
    @returns 命中黑名单返回 True
    """
    from file_types import suffix_of
    return suffix_of(file_path) in BLOCKED_EXTS


def blocked_hint(file_path):
    """生成给用户的拒绝原因（含可行的替代做法）。

    @param file_path 文件路径
    @returns 面向用户的提示文本
    """
    from file_types import suffix_of
    ext = suffix_of(file_path) or "（无扩展名）"
    return (
        "出于安全考虑，不传输可执行文件 / 脚本（%s）；"
        "如需交付此类文件，请先打包为压缩包" % ext
    )
