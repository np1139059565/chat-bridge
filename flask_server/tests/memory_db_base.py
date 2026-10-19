"""记忆库测试的公共基类

职责：把「记忆库重定向到临时目录」的初始化与清理集中在一处，
供各记忆相关测试类继承，避免每个测试文件各写一份相同的
临时目录创建、路径改写与连接关闭逻辑。

用法：
    from memory_db_base import MemoryDBTestBase

    class TestXxx(MemoryDBTestBase):
        PREFIX = "mycase_test_"   # 可选，便于排查残留临时目录时识别来源

需要额外重定向规则目录的测试，可继承 MemoryDBAndRulesTestBase。

说明：
- 每个测试方法独立建临时目录，互不干扰；
- 收尾一律恢复原始路径并删除临时目录，即使断言失败也不残留；
- 子类若需在 setUp 中追加动作，务必先调用父类 setUp。
"""
import shutil
import tempfile
import unittest
from pathlib import Path

import paths
import memory_db


class MemoryDBTestBase(unittest.TestCase):
    """把记忆库目录与库文件重定向到独立临时目录。

    子类可通过 PREFIX 指定临时目录前缀，便于定位残留来源。
    """

    # 临时目录前缀：子类覆盖后，出问题时可从目录名直接看出是哪个测试留下的
    PREFIX = "memdb_test_"

    def setUp(self):
        """建立临时目录并重定向记忆库路径。"""
        self.tmp = tempfile.mkdtemp(prefix=self.PREFIX)
        # 记录原始路径，收尾时原样还原，避免影响同进程内的其它测试
        self._orig_dir = paths.MEMORY_DB_DIR
        self._orig_path = paths.MEMORY_DB_PATH
        paths.MEMORY_DB_DIR = Path(self.tmp)
        memory_db.reset_for_tests(Path(self.tmp) / "test.db")

    def tearDown(self):
        """关闭连接、还原路径并删除临时目录。"""
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dir
        paths.MEMORY_DB_PATH = self._orig_path
        shutil.rmtree(self.tmp, ignore_errors=True)


class MemoryDBAndRulesTestBase(MemoryDBTestBase):
    """在记忆库之外，额外把规则目录也重定向到临时目录。

    适用于会读写 rules 目录的测试（如固化、规则相关）。
    库文件放在临时目录下的 memory 子目录，规则放在 rules 子目录。
    """

    PREFIX = "memrules_test_"

    def setUp(self):
        """建立临时目录，同时重定向记忆库与规则目录。"""
        self.tmp = tempfile.mkdtemp(prefix=self.PREFIX)
        self._orig_dbdir = paths.MEMORY_DB_DIR
        self._orig_dbpath = paths.MEMORY_DB_PATH
        self._orig_rules = paths.RULES_DIR
        paths.MEMORY_DB_DIR = Path(self.tmp) / "memory"
        paths.RULES_DIR = Path(self.tmp) / "rules"
        memory_db.reset_for_tests(Path(self.tmp) / "memory" / "test.db")

    def tearDown(self):
        """关闭连接、还原全部路径并删除临时目录。"""
        memory_db.close_conn()
        paths.MEMORY_DB_DIR = self._orig_dbdir
        paths.MEMORY_DB_PATH = self._orig_dbpath
        paths.RULES_DIR = self._orig_rules
        shutil.rmtree(self.tmp, ignore_errors=True)
