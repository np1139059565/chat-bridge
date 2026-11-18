R1 VERDICT 2026-11-18
SCOPE: bus(refs/r1-evidence/master) vs old(origin/legacy/old-stable) - 102 file decisions (M50+D51+R1)
LEDGER: DIRECT 21 / MERGE 1 / NOT 80

== DIRECT-PORT M (14) ==
extend/content/02_blocks.js [yuanbao multi-container collectAll]
extend/dialog/parts/00b_lifecycle.js [humanize countdown]
extend/dialog/parts/05l_autoexec.js [humanize rate gate]
extend/dialog/parts/08_settings.js [per-minute cap UI]
extend/dialog/parts/08b_settings.js [comment sync]
extend/dialog/parts/08h_profile_fields.js [atBottomCheck hint]
extend/dialog/parts/08k_config_blocks.js [skills write/read null + Array.isArray guard]
extend/dialog/parts/09_skills.js [comment block]
extend/dialog/styles/02f_site_profiles.css [.ae-limit]
flask_server/remote_bridge/command_dispatch.py [async ack + timeout notice: 3d5d9d9+fdc18c7]
flask_server/config/definition.yaml [qwen profile: 74861ce; yuanbao filePaste: fdf67c1]
flask_server/routes/web.py [perplexity sites entry]
flask_server/web_bridge/__init__.py [perplexity host hint]
flask_server/tests/js/test_config_diff_noise.test.js [relative path: aed612e]

== DIRECT-PORT D (7 companion tests) ==
flask_server/tests/js/test_autoexec_humanize.test.js
flask_server/tests/js/test_skill_toggle_commit.test.js
flask_server/tests/test_web_async_command_reply.py
flask_server/tests/test_web_async_command_timeout.py
flask_server/tests/test_web_inbox_command_reply.py
flask_server/tests/test_web_inbox_dedup_persist.py
flask_server/tests/test_yuanbao_file_paste.py

== MERGE-PORT (1) ==
flask_server/web_bridge/web_inbox.py [port: content_seen persist 2a12be2 + global command kinds 2337423/c1f99b5; keep: system role in dedup tuples]

== NOT-PORT (80) ==
M-code 21: old-superset fixes (00_state,03_bridge,03b_paste,06_execute,channel_binding,page_registry,rb-init,delivery,qq_files,qq_gateway,wecom_gateway,weixin_gateway,cards,system_prompt,web_mirror) + naming-only (app.py) + old-side tests (channel_binding,channel_delivery,channel_delivery_text_file,page_registry) + whitespace (08j)
M-noncode 14: README + 12 collab docs + quality_baseline.json
D 44: standard-interface 9+4 tests (main-rework surface) + web_mirror_ai_snapshot_log scaffold (07a80be) + skills 28 (credential risk, old keeps enabled:false) + process docs 2
R 1: test rename pair (each side keeps its own)

== SEQUENCING / NOTES ==
1. web_inbox merge BEFORE its 2 companion tests
2. 08k port BEFORE test_skill_toggle_commit
3. command_dispatch port: _register_pending gains (openid,action) param; ack block goes after _resolve_target gate
4. 07a80be snapshot log: re-port only if B2 fingerprint-drift probe resumes
5. custom_tools enabled flags stay old=false
6. Revision log: 08k/09_skills upgraded to direct (3-point evidence, see chat); inbox tests moved from interface bucket to direct
