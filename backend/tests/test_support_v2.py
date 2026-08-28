"""support_agent v2 状态机冒烟测试（不依赖真实 LLM/网络）。

覆盖：意图启动 -> 收图 -> 分析(mock) -> 确认 -> 生成发布参数 -> 确认发布 -> 取消回退。
"""
import asyncio
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, ".")
sys.path.insert(0, "..")

from app.agents.support_agent import agent_chat, clear_history   # noqa: E402
from app.agents.support_state import PublishGoodsPhase           # noqa: E402

MOCK_ANALYSIS = {
    "title": "iPhone 13 128G 蓝色",
    "description": "自用一年，无磕碰，电池健康90%",
    "category": "手机",
    "condition": "九成新",
    "suggested_price": 3200,
}


async def main() -> None:
    uid = 999
    clear_history(uid)

    # 1. 非发布意图 -> 普通问答降级（mock LLM 文本）
    with patch("app.agents.support_agent._general_chat", AsyncMock(return_value="你好呀！")) as gc:
        r = await agent_chat(uid, "你好，请问平台能做什么？")
    assert r["task_state"] == "idle" and r["phase"] is None, r
    gc.assert_awaited_once()
    print("[1] 普通问答降级 OK")

    # 2. 发布意图 -> 进入收集阶段
    r = await agent_chat(uid, "我要发布商品")
    assert r["task_state"] == "publish_goods", r
    assert r["phase"] == "collecting_images", r
    print("[2] 意图启动 OK")

    # 3. 上传图片 -> 自动分析(mock) -> awaiting_confirm
    with patch("app.agents.support_tools._goods_analyze", AsyncMock(return_value=MOCK_ANALYSIS)):
        r = await agent_chat(uid, "", image_urls=["http://test/img1.jpg", "http://test/img2.jpg"])
    assert r["phase"] == "awaiting_confirm", r
    assert r["action"]["type"] == "analysis_confirm", r
    assert "iPhone 13" in r["answer"], r
    print("[3] 传图+分析 OK")

    # 4a. 修改 -> 回退 collecting_images（保留图片）
    r = await agent_chat(uid, "修改一下")
    assert r["phase"] == "collecting_images", r
    print("[4a] 修改回退 OK")

    # 4b. 重新分析 -> 再次 awaiting_confirm
    with patch("app.agents.support_tools._goods_analyze", AsyncMock(return_value=MOCK_ANALYSIS)):
        r = await agent_chat(uid, "分析")
    assert r["phase"] == "awaiting_confirm", r
    print("[4b] 重新分析 OK")

    # 5. 确认分析 -> awaiting_publish，生成发布参数
    r = await agent_chat(uid, "确认")
    assert r["phase"] == "awaiting_publish", r
    assert r["action"]["type"] == "publish_confirm", r
    data = r["action"]["data"]
    assert data["title"] == "iPhone 13 128G 蓝色", data
    assert data["price"] == 3200 and len(data["image_urls"]) == 2, data
    print("[5] 确认分析+生成发布参数 OK")

    # 6. 确认发布 -> published
    r = await agent_chat(uid, "确认发布")
    assert r["phase"] == "published", r
    assert r["action"]["type"] == "published", r
    print("[6] 确认发布 OK")

    # 7. 完成后新意图 -> 可重新开始
    r = await agent_chat(uid, "我还想卖个平板")
    assert r["phase"] == "collecting_images", r
    print("[7] 完成后重启任务 OK")

    # 8. 取消路径：进入任务后取消
    r = await agent_chat(uid, "取消")
    assert r["phase"] == "cancelled", r
    print("[8] 取消 OK")

    print("\nALL PASS")


if __name__ == "__main__":
    asyncio.run(main())