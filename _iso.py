
import sys, os, tempfile, sqlite3
sys.path.insert(0, os.path.abspath('.'))
import paths
# 用临时库，避免污染真实记忆库
tmp = tempfile.mkdtemp()
paths.MEMORY_DB_DIR = __import__('pathlib').Path(tmp)
paths.MEMORY_DB_PATH = paths.MEMORY_DB_DIR / 'test.db'
import importlib, memory_db
importlib.reload(memory_db)
import memory_nodes
importlib.reload(memory_nodes)
conn = memory_db.get_conn()
# 造数据：会话 A 两个节点(1,2)，会话 B 两个节点(3,4)，时间递进
def ins(i, conv, ts):
    conn.execute("INSERT INTO nodes(id,msg_id,conv_id,site_key,parent_id,source,role,created_at) VALUES(?,?,?,?,0,?,?,?)",
                 (i, 'm%d'%i, conv, 'glm', 'user', 'user', ts))
ins(1,'A',100); ins(2,'A',200); ins(3,'B',150); ins(4,'B',300)
conn.commit()
# 参照节点 2（会话A，ts=200）。修复后：只应删会话A内更早的 -> 节点1
old = memory_nodes.ids_older_than(2, 'A')
print('会话A内更早:', sorted(old))
old2 = memory_nodes.ids_older_than(4, 'B')
print('会话B内更早:', sorted(old2))
assert sorted(old)==[1], old
assert sorted(old2)==[3], old2
print('PASS: 会话隔离生效，B 会话节点未被 A 波及')
