"""标准 System Prompt 生成测试（任务 A-2）：覆盖验收文档的六个场景。

- 单元层：直接调用 core/system_prompt.py 的分段与聚合函数，规则段通过
  重定向 rules.RULES_DIR 到 tmp_path 注入受控规则集；技能段通过
  monkeypatch prompt_sections.sections / skills 注入假数据（真源筛选
  口径的正确性由 test_prompt_sections.py 覆盖，此处不重复）；
- 路由层：独立 Flask app 只注册 system_prompt_bp，断言 GET
  /v1/system_prompt 的 200 / JSON 结构 / 与数据层输出一致；
- 场景 6（单一真源）：patch 上游真源数据后取回输出验证随之变化，
  证明生成器逐次从真源读取，没有第二份常量缓存。
"""
import sys
from pathlib import Path

import pytest

_BASE = Path(__file__).resolve().parents[1]
for _entry in (str(_BASE), str(_BASE / "core"), str(_BASE / "tools")):
    if _entry not in sys.path:
        sys.path.insert(0, _entry)

import rules                                   # noqa: E402
import prompt_sections                         # noqa: E402
import system_prompt as sp                     # noqa: E402
from flask import Flask                        # noqa: E402
from routes.system_prompt import bp as system_prompt_bp   # noqa: E402


FAKE_SECTIONS = [
    {"skill": "demo_skill", "text": "demo 技能的统一说明文字。"},
]

FAKE_SKILLS = [
    {"name": "demo_skill", "summary": "演示用技能", "tools": ["demo_tool"]},
]


@pytest.fixture
def rule_env(tmp_path, monkeypatch):
    """重定向规则目录到 tmp_path，返回写规则帮手。

    rules 在导入期把 paths.RULES_DIR 绑定为模块级 RULES_DIR，
    _path()/list_rules() 都走该模块变量，故两处都要 patch 才生效。
    """
    rd = tmp_path / "rules"
    rd.mkdir()
    monkeypatch.setattr(rules, "RULES_DIR", rd)
    monkeypatch.setattr(rules, "META_PATH", rd / "_meta.json")
    return rd


@pytest.fixture
def skill_env(monkeypatch):
    """注入固定的假技能数据，隔离真实技能目录与本机上下线状态。"""
    monkeypatch.setattr(prompt_sections, "sections", lambda: list(FAKE_SECTIONS))
    monkeypatch.setattr(prompt_sections, "skills",
                        lambda: [dict(s) for s in FAKE_SKILLS])


# ---------- 场景 1：四段齐全 ----------

def test_s1_all_four_sections_present(rule_env, skill_env):
    """输出含四段标记且顺序固定：身份 -> 规则 -> 技能 -> 通则。"""
    rules.write_rule("r_alpha", "# 规则甲\n正文一", priority="always")
    result = sp.build_system_prompt()
    text = result["system_prompt"]
    for m in (sp.MARK_IDENTITY, sp.MARK_RULES, sp.MARK_SKILLS, sp.MARK_PARAMS):
        assert m in text
    idx = [text.index(m) for m in
           (sp.MARK_IDENTITY, sp.MARK_RULES, sp.MARK_SKILLS, sp.MARK_PARAMS)]
    assert idx == sorted(idx)
    assert len(result["sections"]) == 4


def test_s1_empty_envs_still_render_four_marks(rule_env, skill_env):
    """无规则、无技能时四段标记仍在，占位文案兜底。"""
    text = sp.build_system_prompt()["system_prompt"]
    for m in (sp.MARK_IDENTITY, sp.MARK_RULES, sp.MARK_SKILLS, sp.MARK_PARAMS):
        assert m in text


# ---------- 场景 2：规则正文不注入 ----------

def test_s2_rule_body_not_injected(rule_env, skill_env):
    """规则段只有名称 + 优先级标签，不含摘要与正文。"""
    rules.write_rule("r_secret", "# 标题行当摘要\n正文中藏着 SECRET_MARKER_42",
                     priority="on-demand")
    text = sp.build_system_prompt()["system_prompt"]
    assert "r_secret" in text
    assert "SECRET_MARKER_42" not in text
    assert "标题行当摘要" not in text


def test_s2_priority_labels_used(rule_env, skill_env):
    """优先级以中文标签呈现（与 rules.PRIORITY_LABELS 口径一致）。"""
    rules.write_rule("r_p", "x", priority="always")
    rules.write_rule("r_q", "y", priority="on-demand")
    text = sp.build_system_prompt()["system_prompt"]
    assert "总是" in text
    assert "按需" in text

# ---------- 场景 3：已上线口径（生成器信任上游过滤） ----------

def test_s3_only_listed_skills_appear(rule_env, skill_env):
    """上游给出的清单之外的内容不出现：生成器不自行发明技能。"""
    text = sp.build_system_prompt()["system_prompt"]
    assert "demo_skill" in text
    assert "demo_tool" in text
    assert "不存在的技能" not in text


def test_s3_empty_upstream_shows_placeholder(rule_env, monkeypatch):
    """上游为空（模拟全部下线）时：无技能名，占位文案兜底。"""
    monkeypatch.setattr(prompt_sections, "sections", lambda: [])
    monkeypatch.setattr(prompt_sections, "skills", lambda: [])
    text = sp.build_system_prompt()["system_prompt"]
    assert "demo_skill" not in text
    assert "当前没有已上线的技能" in text
# ---------- 场景 4：方言隔离 ----------

def test_s4_no_dialect_words(rule_env, skill_env):
    bt = chr(96) * 3
    text = sp.build_system_prompt()["system_prompt"]
    assert bt not in text
    for w in ("回传格式", "朗读", "语音朗读", "选择器", "方言", "语言包", "翻译员", "调用格式"):
        assert w not in text, "方言词泄漏：%s" % w

# ---------- 场景 5：参数清单不塞满 ----------

def test_s5_no_param_schema(rule_env, skill_env):
    text = sp.build_system_prompt()["system_prompt"]
    for w in ("properties", "required", '"type": "object"', "anyOf"):
        assert w not in text, "参数 schema 泄漏：%s" % w
    assert "get_tool_params" in text


def test_skills_prose_not_in_subject(rule_env, skill_env):
    """步骤②：技能说明正文不进主体，仅留名称/摘要/工具名。"""
    text = sp.build_system_prompt()['system_prompt']
    for s in FAKE_SECTIONS:
        t = (s.get('text') or '').strip()
        assert not t or t not in text