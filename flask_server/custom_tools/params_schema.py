"""参数声明规范化：全库唯一规范化点，schema/数组双输入，对 schema 幂等。

独立成模块：loader.py 触及行数上限，registry 也直接调用，关注点分离。
"""

from .paths import NAME_RE


def _check_param_name(pname, tool_name):
    """校验参数名非空且匹配 NAME_RE，非法即抛 ValueError。"""
    if not pname or not NAME_RE.match(str(pname)):
        raise ValueError("工具 %s 的参数名非法：" % tool_name + str(pname))


def _array_param_prop(p):
    """历史数组单项转 schema 属性对象（type 缺省 string，description 可选）。"""
    prop = {"type": (p.get("type") or "string")}
    if p.get("description"):
        prop["description"] = p.get("description")
    return prop


def _schema_params(decl, tool_name):
    """标准 schema 对象取 (props, required)；属性对象浅拷贝保留子结构。"""
    props_in = decl.get("properties")
    req_in = decl.get("required") or []
    if not isinstance(props_in, dict) or not isinstance(req_in, list):
        raise ValueError("工具 %s 的 parameters 结构非法（properties 须为对象、required 须为数组）" % tool_name)
    props = {}
    for pname, spec in props_in.items():
        _check_param_name(pname, tool_name)
        if not isinstance(spec, dict):
            raise ValueError("工具 %s 的参数 %s 声明须为对象" % (tool_name, pname))
        props[pname] = dict(spec)
    return props, [r for r in req_in if r]


def _array_params(decl, tool_name):
    """历史数组取 (props, required)：逐项校验 name 并转属性对象。"""
    props = {}
    required = []
    for p in decl:
        pname = (p.get("name") if isinstance(p, dict) else None) or ""
        if not pname:
            raise ValueError("工具 %s 存在缺少 name 的参数" % tool_name)
        _check_param_name(pname, tool_name)
        props[pname] = _array_param_prop(p)
        if p.get("required"):
            required.append(pname)
    return props, required


def normalize_params_schema(decl, tool_name):
    """把参数声明规范化为标准 JSON Schema 对象；输入双格式兼容。

    阶段 1b（见 docs/tool-schema-migration.md）后内部规范格式为
    {"type": "object", "properties": {参数名: 属性}, "required": [参数名]}。
    本函数是全库唯一的规范化点，接受两种输入：
    - 标准 schema 对象：属性对象（含 anyOf / items / maxItems 等）原样保留；
    - 历史数组：[{"name", "type", "required", "description"}, ...] 转换为 schema。
    两种输入都做参数名合法性校验；对 schema 输入幂等（再过一遍结果不变）。
    @param decl      参数声明（schema 对象 / 历史数组 / None）
    @param tool_name 工具名（仅用于报错文案）
    @returns 标准 schema 对象；存在必填参数时附顶层 required 数组
    """
    if decl is None:
        decl = []
    if isinstance(decl, dict):
        props, required = _schema_params(decl, tool_name)
    elif isinstance(decl, list):
        props, required = _array_params(decl, tool_name)
    else:
        raise ValueError("工具 %s 的 parameters 格式非法（须为 schema 对象或数组）" % tool_name)
    schema = {"type": "object", "properties": props}
    if required:
        schema["required"] = required
    return schema
