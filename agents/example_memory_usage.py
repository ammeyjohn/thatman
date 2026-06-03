"""
Hindsight 记忆系统使用示例
演示如何使用 hindsight-client 访问 Hindsight 服务实现长期记忆

前置条件：
1. 安装 hindsight-client: pip install hindsight-client
2. 启动 Hindsight 服务:
   - 方式1 (pip): 
       pip install hindsight-api
       export OPENAI_API_KEY=sk-xxx
       export HINDSIGHT_API_LLM_API_KEY=$OPENAI_API_KEY
       hindsight-api
   - 方式2 (Docker):
       docker run -it --pull always --name hindsight --restart unless-stopped \\
           -p 8888:8888 -p 9999:9999 \\
           -e HINDSIGHT_API_LLM_API_KEY=$OPENAI_API_KEY \\
           -v $HOME/.hindsight-docker:/home/hindsight/.pg0 \\
           ghcr.io/vectorize-io/hindsight:latest
3. 服务启动后访问: http://localhost:8888
"""

from llm_client import get_llm_client, get_llm_client_with_memory


def example_basic():
    """基础 hindsight 记忆示例"""
    print("=" * 50)
    print("示例 1: 基础 hindsight 记忆")
    print("=" * 50)

    # 创建带 hindsight 记忆的客户端
    # 确保 Hindsight 服务已在 localhost:8888 启动
    client = get_llm_client_with_memory(
        bank_id="demo-agent",
        base_url="http://localhost:8888",
    )

    # 模拟多轮对话，自动 retain 到 hindsight
    conversations = [
        "你好，我叫小明",
        "我喜欢打篮球和游泳",
        "你记得我叫什么名字吗？",
        "我最喜欢的运动是什么？",
    ]

    for i, prompt in enumerate(conversations, 1):
        print(f"\n\033[36m[第 {i} 轮]\033[0m")
        print(f"用户: {prompt}")
        print("AI: ", end="", flush=True)

        # 使用带 hindsight 记忆的对话
        response = client.chat_with_memory(prompt, auto_retain=True)
        print(response)

    # 查看 hindsight 记忆统计
    stats = client.get_memory_stats()
    print(f"\n\033[90m[DEBUG] Hindsight 记忆统计: {stats}\033[0m")


def example_manual_retain():
    """手动 retain 记忆示例"""
    print("\n" + "=" * 50)
    print("示例 2: 手动 retain 记忆")
    print("=" * 50)

    client = get_llm_client_with_memory(
        bank_id="manual-agent",
        base_url="http://localhost:8888",
    )

    # 手动添加重要信息到 hindsight
    client.add_hindsight(
        content="用户的项目截止日期是 2026 年 6 月 15 日",
        context="project_deadline"
    )
    client.add_hindsight(
        content="用户偏好使用 Vue.js 而不是 React",
        context="tech_preference"
    )
    client.add_hindsight(
        content="用户正在学习 Python 和 Web 开发",
        context="learning"
    )

    print("\033[90m[DEBUG] 已手动 retain 到 hindsight\033[0m")

    # 查询与记忆相关的问题
    prompts = [
        "我什么时候需要完成项目？",
        "我应该用哪个前端框架？",
        "我在学习什么技术？",
    ]

    for prompt in prompts:
        print(f"\n用户: {prompt}")
        print("AI: ", end="", flush=True)
        response = client.chat_with_memory(prompt)
        print(response)

    # 查看统计
    stats = client.get_memory_stats()
    print(f"\n\033[90m[DEBUG] 记忆统计: {stats}\033[0m")


def example_recall_directly():
    """直接 recall 检索记忆"""
    print("\n" + "=" * 50)
    print("示例 3: 直接 recall 检索记忆")
    print("=" * 50)

    client = get_llm_client_with_memory(
        bank_id="recall-agent",
        base_url="http://localhost:8888",
    )

    # 先添加一些记忆
    client.add_hindsight("用户喜欢喝咖啡，尤其是美式", "preference")
    client.add_hindsight("用户每天早上 8 点起床", "routine")
    client.add_hindsight("用户在学 Python 编程", "learning")
    client.add_hindsight("用户不喜欢吃辣", "preference")

    # 直接 recall 检索
    queries = ["咖啡", "编程", "生活习惯"]

    for query in queries:
        print(f"\n查询: '{query}'")
        memories = client.recall_hindsight(query)
        for i, mem in enumerate(memories, 1):
            print(f"  {i}. [{mem.get('type', '')}] {mem.get('text', '')}")


def example_memory_types():
    """不同 context 的记忆"""
    print("\n" + "=" * 50)
    print("示例 4: 按 context 分类记忆")
    print("=" * 50)

    client = get_llm_client_with_memory(
        bank_id="context-agent",
        base_url="http://localhost:8888",
    )

    # 添加不同 context 的记忆
    memories = [
        ("用户喜欢科幻电影，尤其是《星际穿越》", "entertainment"),
        ("用户在 2026 年 5 月参加了 Python 培训", "career"),
        ("用户的工作是数据分析师", "career"),
        ("用户认为代码可读性比性能更重要", "philosophy"),
    ]

    for content, context in memories:
        client.add_hindsight(content, context)
        print(f"\033[90m[DEBUG] 添加 [{context}]: {content[:40]}...\033[0m")

    # 查看统计
    stats = client.get_memory_stats()
    print(f"\n记忆统计: {stats}")


def example_clear_memory():
    """清空记忆示例"""
    print("\n" + "=" * 50)
    print("示例 5: 清空记忆")
    print("=" * 50)

    client = get_llm_client_with_memory(
        bank_id="clear-agent",
        base_url="http://localhost:8888",
    )

    # 添加一些记忆
    client.add_hindsight("测试记忆内容", "test")
    client.chat_with_memory("你好")

    print(f"清空前: {client.get_memory_stats()}")

    # 只清空短期记忆
    client.clear_memory(clear_short_term_only=True)
    print(f"清空短期记忆后: {client.get_memory_stats()}")

    # 清空 hindsight bank
    client.clear_memory(clear_short_term_only=False)
    print(f"清空 hindsight bank 后: {client.get_memory_stats()}")


def example_without_memory():
    """不使用记忆的对比示例"""
    print("\n" + "=" * 50)
    print("示例 6: 不使用记忆的对比")
    print("=" * 50)

    # 无记忆模式
    client_no_memory = get_llm_client(enable_memory=False)

    print("\n\033[33m[无记忆模式]\033[0m")
    response1 = client_no_memory.simple_chat("我叫小红")
    print(f"AI: {response1}")

    response2 = client_no_memory.simple_chat("我叫什么名字？")
    print(f"AI: {response2}")

    # 有 hindsight 记忆模式
    client_with_memory = get_llm_client_with_memory(
        bank_id="compare-agent",
        base_url="http://localhost:8888",
    )

    print("\n\033[32m[hindsight 记忆模式]\033[0m")
    response3 = client_with_memory.chat_with_memory("我叫小红")
    print(f"AI: {response3}")

    response4 = client_with_memory.chat_with_memory("我叫什么名字？")
    print(f"AI: {response4}")


def example_with_mission():
    """使用 mission 配置 hindsight"""
    print("\n" + "=" * 50)
    print("示例 7: 使用 mission 配置")
    print("=" * 50)

    client = get_llm_client_with_memory(
        bank_id="mission-agent",
        base_url="http://localhost:8888",
        mission="你是一个修仙世界的 AI 助手，帮助用户修炼和探索",
    )

    # 添加修仙相关记忆
    client.add_hindsight("用户是青云宗外门弟子", "identity")
    client.add_hindsight("用户修炼的是《太玄经》", "cultivation")
    client.add_hindsight("用户当前境界是炼气期三层", "cultivation")

    # 查询
    prompts = [
        "我是谁？",
        "我修炼什么功法？",
        "我现在什么境界？",
    ]

    for prompt in prompts:
        print(f"\n用户: {prompt}")
        print("AI: ", end="", flush=True)
        response = client.chat_with_memory(prompt)
        print(response)


if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("Hindsight 记忆系统使用示例")
    print("=" * 50)
    print("\n前置条件：")
    print("1. 安装: pip install hindsight-client")
    print("2. 启动 Hindsight 服务 (见文件顶部注释)")
    print("3. 服务地址: http://localhost:8888")

    # 运行示例（取消注释想要运行的示例）

    # example_basic()
    # example_manual_retain()
    # example_recall_directly()
    # example_memory_types()
    example_clear_memory()
    # example_without_memory()
    # example_with_mission()

    print("\n\n请选择要运行的示例，取消注释相应的函数调用")
    print("可用示例:")
    print("  1. example_basic() - 基础 hindsight 记忆")
    print("  2. example_manual_retain() - 手动 retain 记忆")
    print("  3. example_recall_directly() - 直接 recall 检索")
    print("  4. example_memory_types() - 按 context 分类记忆")
    print("  5. example_clear_memory() - 清空记忆")
    print("  6. example_without_memory() - 不使用记忆的对比")
    print("  7. example_with_mission() - 使用 mission 配置")
