"""
LangChain + llama.cpp 使用示例
演示如何调用 llama.cpp 的 OpenAI 兼容服务
"""
import sys
from llm_client import LLMClient, get_llm_client


def example_simple_chat():
    """示例1: 简单的单轮对话"""
    print("=" * 50)
    print("示例1: 简单对话")
    print("=" * 50)

    client = get_llm_client()
    prompt = "你好，请介绍一下你自己。"

    print(f"用户: {prompt}")
    print("AI: ", end="", flush=True)

    response = client.simple_chat(prompt)
    print(response)
    print()


def example_multi_turn_chat():
    """示例2: 多轮对话"""
    print("=" * 50)
    print("示例2: 多轮对话")
    print("=" * 50)

    client = get_llm_client()

    messages = [
        {"role": "system", "content": "你是一个有帮助的AI助手，回答要简洁明了。"},
        {"role": "user", "content": "什么是机器学习？"},
    ]

    print("用户: 什么是机器学习？")
    print("AI: ", end="", flush=True)

    response1 = client.chat(messages)
    print(response1)
    print()

    # 继续对话
    messages.append({"role": "assistant", "content": response1})
    messages.append({"role": "user", "content": "能给我举一个例子吗？"})

    print("用户: 能给我举一个例子吗？")
    print("AI: ", end="", flush=True)

    response2 = client.chat(messages)
    print(response2)
    print()


def example_streaming_chat():
    """示例3: 流式输出"""
    print("=" * 50)
    print("示例3: 流式输出")
    print("=" * 50)

    client = get_llm_client(streaming=True)
    prompt = "请写一首关于春天的短诗。"

    print(f"用户: {prompt}")
    print("AI: ", end="", flush=True)

    # 流式输出会自动打印到控制台
    response = client.simple_chat(prompt)
    print()  # 换行
    print()


def example_with_parameters():
    """示例4: 自定义参数"""
    print("=" * 50)
    print("示例4: 自定义参数（低温度，更确定的回答）")
    print("=" * 50)

    client = get_llm_client()
    prompt = "Python 中列表和元组有什么区别？"

    print(f"用户: {prompt}")
    print("AI (temperature=0.1): ", end="", flush=True)

    messages = [{"role": "user", "content": prompt}]
    response = client.chat(messages, temperature=0.1, max_tokens=512)
    print(response)
    print()


def interactive_chat():
    """交互式聊天"""
    print("=" * 50)
    print("交互式聊天模式")
    print("输入 'quit' 或 'exit' 退出")
    print("=" * 50)
    print()

    client = get_llm_client(streaming=True)
    messages = []

    # 可选：设置系统提示词
    system_prompt = input("是否设置系统提示词？(直接回车跳过): ").strip()
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
        print()

    while True:
        try:
            user_input = input("用户: ").strip()

            if user_input.lower() in ["quit", "exit", "q"]:
                print("再见！")
                break

            if not user_input:
                continue

            messages.append({"role": "user", "content": user_input})

            print("AI: ", end="", flush=True)
            response = client.chat(messages)
            print()

            messages.append({"role": "assistant", "content": response})
            print()

        except KeyboardInterrupt:
            print("\n再见！")
            break
        except Exception as e:
            print(f"错误: {e}")
            break


def main():
    """主函数"""
    print("LangChain + llama.cpp 示例程序")
    print()

    # 检查命令行参数
    if len(sys.argv) > 1:
        mode = sys.argv[1]

        if mode == "simple":
            example_simple_chat()
        elif mode == "multi":
            example_multi_turn_chat()
        elif mode == "stream":
            example_streaming_chat()
        elif mode == "params":
            example_with_parameters()
        elif mode == "interactive":
            interactive_chat()
        else:
            print(f"未知模式: {mode}")
            print_usage()
    else:
        # 默认运行所有示例
        print("运行所有示例...")
        print("如需交互模式，请运行: python example.py interactive")
        print()

        try:
            example_simple_chat()
            example_multi_turn_chat()
            example_with_parameters()
        except Exception as e:
            print(f"运行示例时出错: {e}")
            print("请确保 llama.cpp 服务已启动")
            print()


def print_usage():
    """打印使用说明"""
    print("用法: python example.py [mode]")
    print()
    print("可用模式:")
    print("  simple       - 简单对话示例")
    print("  multi        - 多轮对话示例")
    print("  stream       - 流式输出示例")
    print("  params       - 自定义参数示例")
    print("  interactive  - 交互式聊天模式")
    print()
    print("默认运行所有非交互式示例")


if __name__ == "__main__":
    main()
