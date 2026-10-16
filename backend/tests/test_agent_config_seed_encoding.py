"""回归测试：agent_config 空库 seed 必须写入正确 UTF-8 中文（钉住 bugs/agent-config-mojibake.md）。

背景：聊天页 Agent 下拉显示乱码（Ã©Â»Â¤Ã¨Â®Â¤ DeepAgent），排查确认源码常量正常，
损坏来自一次外部 PUT 回写时客户端双重编码。本测试钉住 seed 路径写入的
name / system_prompt 与源码常量逐字一致，防止源码文件编码或 seed 路径回归。

运行：
  cd backend && ./venv/Scripts/python.exe -m pytest tests/test_agent_config_seed_encoding.py -q
"""

import asyncio

import pytest

import agent.config_store as cs
from agent.deep_agent import SYSTEM_PROMPT


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    db = str(tmp_path / "seed_enc_test.db")
    monkeypatch.setattr(cs, "DB_PATH", db)
    return db


def test_seed_writes_correct_chinese(tmp_db):
    async def run():
        cfg = await cs.load_default_config()
        assert cfg["name"] == "默认 DeepAgent"
        assert cfg["system_prompt"] == SYSTEM_PROMPT
        # 无 mojibake 特征序列（Ã/Â 开头的高位字节重组痕迹）
        assert "Ã" not in cfg["name"] and "Â" not in cfg["name"]
        # 再读一次，确认 DB 往返无损
        again = await cs.get_agent(cfg["id"])
        assert again["name"] == "默认 DeepAgent"
        assert again["system_prompt"] == SYSTEM_PROMPT
    asyncio.run(run())
