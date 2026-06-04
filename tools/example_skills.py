#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
示例 Skills 测试脚本
通过 llama-server 的 OpenAI 接口，让大模型调用 skills 读取 docs 文档
"""

import json
import os
import sys
from typing import Dict, List, Any, Optional
from pathlib import Path

# OpenAI 客户端
from openai import OpenAI


# ============== Skills 定义 ==============

SKILLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_doc",
            "description": "读取 docs 目录下的文档内容并返回",
            "parameters": {
                "type": "object",
                "properties": {
                    "doc_name": {
                        "type": "string",
                        "description": "文档名称，如 'game_manual.md', '世界观.md' 等"
                    }
                },
                "required": ["doc_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "返回当前项目中指定文件夹下的文件列表",
            "parameters": {
                "type": "object",
                "properties": {
                    "folder_path": {
                        "type": "string",
                        "description": "文件夹路径，相对于项目根目录，如 'docs', 'server', 'web/src' 等"
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "是否递归列出子目录，默认为 false"
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "文件匹配模式，如 '*.py', '*.md', '*.ts' 等，可选"
                    }
                },
                "required": ["folder_path"]
            }
        }
    }
]


def read_doc(doc_name: str) -> Dict[str, Any]:
    """
    Skill: 读取指定文档内容

    Args:
        doc_name: 文档名称（如 'game_manual.md'）

    Returns:
        包含文档内容的字典
    """
    docs_dir = Path(__file__).parent.parent / "docs"
    file_path = docs_dir / doc_name

    print_colored(f"[SKILL] 执行 read_doc: {doc_name}", "blue")

    # 安全检查：确保文件在 docs 目录内
    try:
        file_path = file_path.resolve()
        docs_dir = docs_dir.resolve()
        if not str(file_path).startswith(str(docs_dir)):
            return {
                "success": False,
                "error": f"非法路径: {doc_name}",
                "content": None
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"路径解析错误: {e}",
            "content": None
        }

    # 检查文件是否存在
    if not file_path.exists():
        # 列出可用文档
        available_docs = []
        if docs_dir.exists():
            available_docs = [f.name for f in docs_dir.iterdir() if f.is_file()]

        return {
            "success": False,
            "error": f"文档不存在: {doc_name}",
            "available_docs": available_docs,
            "content": None
        }

    # 读取文档内容
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return {
            "success": True,
            "doc_name": doc_name,
            "file_path": str(file_path),
            "content": content,
            "content_length": len(content)
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"读取文档失败: {e}",
            "content": None
        }


def list_available_docs() -> List[str]:
    """列出 docs 目录下所有可用文档"""
    docs_dir = Path(__file__).parent.parent / "docs"
    if not docs_dir.exists():
        return []
    return [f.name for f in docs_dir.iterdir() if f.is_file() and f.suffix == '.md']


def list_files(folder_path: str, recursive: bool = False, file_pattern: Optional[str] = None) -> Dict[str, Any]:
    """
    Skill: 列出指定文件夹下的文件

    Args:
        folder_path: 文件夹路径（相对于项目根目录）
        recursive: 是否递归列出子目录
        file_pattern: 文件匹配模式（如 '*.py'）

    Returns:
        包含文件列表的字典
    """
    project_root = Path(__file__).parent.parent
    target_dir = project_root / folder_path

    print_colored(f"[SKILL] 执行 list_files: {folder_path} (recursive={recursive}, pattern={file_pattern})", "blue")

    # 安全检查：确保路径在项目根目录内
    try:
        target_dir = target_dir.resolve()
        project_root = project_root.resolve()
        if not str(target_dir).startswith(str(project_root)):
            return {
                "success": False,
                "error": f"非法路径: {folder_path}",
                "files": [],
                "folders": []
            }
    except Exception as e:
        return {
            "success": False,
            "error": f"路径解析错误: {e}",
            "files": [],
            "folders": []
        }

    # 检查目录是否存在
    if not target_dir.exists():
        return {
            "success": False,
            "error": f"目录不存在: {folder_path}",
            "files": [],
            "folders": []
        }

    if not target_dir.is_dir():
        return {
            "success": False,
            "error": f"路径不是目录: {folder_path}",
            "files": [],
            "folders": []
        }

    # 收集文件和文件夹
    files = []
    folders = []

    try:
        if recursive:
            for item in target_dir.rglob('*'):
                relative_path = item.relative_to(project_root)
                if item.is_file():
                    # 检查文件匹配模式
                    if file_pattern and not item.match(file_pattern):
                        continue
                    files.append(str(relative_path))
                elif item.is_dir():
                    folders.append(str(relative_path))
        else:
            for item in target_dir.iterdir():
                relative_path = item.relative_to(project_root)
                if item.is_file():
                    # 检查文件匹配模式
                    if file_pattern and not item.match(file_pattern):
                        continue
                    files.append(str(relative_path))
                elif item.is_dir():
                    folders.append(str(relative_path))

        # 排序
        files.sort()
        folders.sort()

        return {
            "success": True,
            "folder_path": folder_path,
            "recursive": recursive,
            "file_pattern": file_pattern,
            "total_files": len(files),
            "total_folders": len(folders),
            "files": files,
            "folders": folders
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"列出文件失败: {e}",
            "files": [],
            "folders": []
        }


# ============== OpenAI 客户端 ==============

class LLMClient:
    """llama-server OpenAI 接口客户端"""

    def __init__(self, base_url: str = "http://localhost:7779/v1", api_key: str = "sk-no-key-required"):
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key
        )
        self.model = "local-model"  # llama-server 的模型名称
        self.max_iterations = 10  # 最大迭代轮数

    def _execute_skill(self, function_name: str, function_args: Dict[str, Any]) -> Dict[str, Any]:
        """执行指定的 skill"""
        if function_name == "read_doc":
            return read_doc(**function_args)
        elif function_name == "list_files":
            return list_files(**function_args)
        else:
            return {
                "success": False,
                "error": f"未知工具: {function_name}"
            }

    def chat_with_skills(self, user_message: str) -> Dict[str, Any]:
        """
        与 LLM 对话，支持 function calling（单轮）

        Args:
            user_message: 用户输入

        Returns:
            包含回复内容和可能的函数调用结果
        """
        messages = [
            {
                "role": "system",
                "content": f"""你是一个智能助手，可以使用工具来读取文档和浏览项目文件。

可用工具：
1. read_doc: 读取 docs 目录下的文档内容
2. list_files: 列出指定文件夹下的文件和子目录

docs 目录下的可用文档列表：
{json.dumps(list_available_docs(), ensure_ascii=False, indent=2)}

当用户询问关于文档内容的问题时，请使用 read_doc 工具读取相应文档。
当用户询问项目结构或文件列表时，请使用 list_files 工具。"""
            },
            {
                "role": "user",
                "content": user_message
            }
        ]

        print_colored("[LLM] 发送请求到 llama-server...", "gray")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=SKILLS_SCHEMAS,
                tool_choice="auto"
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"LLM 请求失败: {e}",
                "content": None
            }

        message = response.choices[0].message

        if message.tool_calls:
            print_colored(f"[LLM] 模型决定调用工具: {message.tool_calls[0].function.name}", "yellow")

            tool_call = message.tool_calls[0]
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            skill_result = self._execute_skill(function_name, function_args)

            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tool_call.id,
                        "type": "function",
                        "function": {
                            "name": function_name,
                            "arguments": tool_call.function.arguments
                        }
                    }
                ]
            })

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(skill_result, ensure_ascii=False)
            })

            print_colored("[LLM] 发送工具结果给模型...", "gray")

            try:
                final_response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages
                )

                return {
                    "success": True,
                    "skill_called": function_name,
                    "skill_args": function_args,
                    "skill_result": skill_result,
                    "content": final_response.choices[0].message.content
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"最终回复请求失败: {e}",
                    "skill_called": function_name,
                    "skill_result": skill_result
                }

        else:
            return {
                "success": True,
                "skill_called": None,
                "content": message.content
            }

    def iterative_chat(self, user_message: str) -> Dict[str, Any]:
        """
        多轮迭代对话，模型自主判断工作是否完成
        最多迭代 10 轮

        Args:
            user_message: 用户输入的任务

        Returns:
            包含完整执行过程和最终回复
        """
        print_colored(f"\n{'='*60}", "cyan")
        print_colored("开始多轮迭代任务", "cyan")
        print_colored(f"用户问题: {user_message}", "white")
        print_colored(f"{'='*60}\n", "cyan")

        messages = [
            {
                "role": "system",
                "content": f"""你是一个智能助手，可以使用工具来完成用户的任务。

可用工具：
1. read_doc: 读取 docs 目录下的文档内容
2. list_files: 列出指定文件夹下的文件和子目录

docs 目录下的可用文档列表：
{json.dumps(list_available_docs(), ensure_ascii=False, indent=2)}

你的工作流程：
1. 分析用户的问题，判断需要哪些信息
2. 使用工具获取所需信息
3. 分析获取的信息，判断任务是否完成
4. 如果任务未完成，继续使用工具获取更多信息（最多10轮）
5. 任务完成后，给出完整的回答

在每次回复中，你需要明确说明：
- 当前步骤的分析
- 是否需要继续获取信息
- 任务是否已经完成

当任务完成时，请明确说明"任务已完成"并给出最终答案。"""
            },
            {
                "role": "user",
                "content": user_message
            }
        ]

        iteration = 0
        skill_history = []

        while iteration < self.max_iterations:
            iteration += 1
            print_colored(f"\n--- 第 {iteration}/{self.max_iterations} 轮 ---", "yellow")

            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    tools=SKILLS_SCHEMAS,
                    tool_choice="auto"
                )
            except Exception as e:
                return {
                    "success": False,
                    "error": f"第 {iteration} 轮 LLM 请求失败: {e}",
                    "iterations": iteration,
                    "skill_history": skill_history
                }

            message = response.choices[0].message

            # 检查是否有工具调用
            if message.tool_calls:
                tool_call = message.tool_calls[0]
                function_name = tool_call.function.name
                function_args = json.loads(tool_call.function.arguments)

                print_colored(f"[模型] 决定调用工具: {function_name}", "blue")
                print_colored(f"[模型] 参数: {json.dumps(function_args, ensure_ascii=False)}", "gray")

                # 执行 skill
                skill_result = self._execute_skill(function_name, function_args)
                skill_history.append({
                    "iteration": iteration,
                    "skill": function_name,
                    "args": function_args,
                    "result": skill_result
                })

                if skill_result.get("success"):
                    print_colored(f"[SKILL] 执行成功", "green")
                    if function_name == "read_doc":
                        preview = skill_result.get("content", "")[:100]
                        print_colored(f"  内容预览: {preview}...", "gray")
                    elif function_name == "list_files":
                        files_count = skill_result.get("total_files", 0)
                        folders_count = skill_result.get("total_folders", 0)
                        print_colored(f"  找到 {files_count} 个文件, {folders_count} 个文件夹", "gray")
                else:
                    print_colored(f"[SKILL] 执行失败: {skill_result.get('error')}", "red")

                # 将工具调用和结果添加到对话历史
                messages.append({
                    "role": "assistant",
                    "content": message.content or f"我需要调用 {function_name} 工具来获取更多信息",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": function_name,
                                "arguments": tool_call.function.arguments
                            }
                        }
                    ]
                })

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(skill_result, ensure_ascii=False)
                })

            else:
                # 模型没有调用工具，直接返回回复
                content = message.content or ""
                print_colored(f"[模型] 回复: {content[:200]}...", "white")

                # 检查是否表示任务完成
                completion_indicators = [
                    "任务已完成", "任务完成", "已完成", "完成",
                    "final answer", "completed", "done"
                ]
                is_completed = any(indicator in content.lower() for indicator in completion_indicators)

                if is_completed or iteration >= self.max_iterations:
                    print_colored(f"\n{'='*60}", "green")
                    if is_completed:
                        print_colored("任务已完成", "green")
                    else:
                        print_colored("达到最大迭代次数，任务结束", "yellow")
                    print_colored(f"共执行 {iteration} 轮", "green")
                    print_colored(f"{'='*60}\n", "green")

                    return {
                        "success": True,
                        "iterations": iteration,
                        "is_completed": is_completed,
                        "skill_history": skill_history,
                        "content": content
                    }

                # 继续下一轮
                messages.append({
                    "role": "assistant",
                    "content": content
                })

                # 提示模型继续
                messages.append({
                    "role": "user",
                    "content": "请继续分析，判断任务是否完成。如果需要更多信息，请使用工具。"
                })

        # 达到最大迭代次数
        print_colored(f"\n{'='*60}", "yellow")
        print_colored("达到最大迭代次数 (10轮)", "yellow")
        print_colored(f"{'='*60}\n", "yellow")

        return {
            "success": True,
            "iterations": iteration,
            "is_completed": False,
            "skill_history": skill_history,
            "content": "已达到最大迭代次数，任务未能自动完成。"
        }


# ============== 工具函数 ==============

def print_colored(text: str, color: str = "white"):
    """打印带颜色的文本"""
    colors = {
        "gray": "\033[90m",
        "white": "\033[0m",
        "yellow": "\033[93m",
        "red": "\033[91m",
        "green": "\033[92m",
        "blue": "\033[94m",
        "cyan": "\033[96m"
    }
    reset = "\033[0m"
    print(f"{colors.get(color, colors['white'])}{text}{reset}")


def print_section(title: str):
    """打印分节标题"""
    print_colored("\n" + "=" * 60, "cyan")
    print_colored(f" {title} ", "cyan")
    print_colored("=" * 60, "cyan")


def main():
    """主函数"""
    print_colored("=" * 60, "blue")
    print_colored("大模型 Skills 调用测试 (llama-server)", "blue")
    print_colored("=" * 60, "blue")

    # 检查 openai 包
    try:
        import openai
    except ImportError:
        print_colored("\n[ERROR] 请先安装 openai 包:", "red")
        print_colored("  pip install openai", "yellow")
        return 1

    # 显示可用文档
    print_section("可用文档列表")
    docs = list_available_docs()
    for doc in docs:
        print_colored(f"  • {doc}", "green")

    # 初始化 LLM 客户端
    print_section("初始化 LLM 客户端")
    base_url = os.environ.get("LLAMA_SERVER_URL", "http://localhost:7779/v1")
    print_colored(f"API 地址: {base_url}", "gray")

    client = LLMClient(base_url=base_url)

    # 测试场景 - 单轮模式
    print_section("单轮模式测试")

    test_cases = [
        "请读取 game_manual.md 文档并告诉我游戏的基本规则",
        "世界观.md 里描述的是什么样的世界？",
        "请查看 npc_config.md 中的 NPC 配置",
        "列出 server 目录下的所有文件",
        "web/src 目录下有哪些 TypeScript 文件？",
        "这是一个普通问题，不需要读取文档",
    ]

    for i, test_input in enumerate(test_cases, 1):
        print_colored(f"\n【测试 {i}】", "yellow")
        print_colored(f"用户输入: {test_input}", "white")
        print_colored("-" * 40, "gray")

        result = client.chat_with_skills(test_input)

        if result["success"]:
            if result.get("skill_called"):
                print_colored(f"✓ 调用了 Skill: {result['skill_called']}", "green")
                print_colored(f"  参数: {json.dumps(result['skill_args'], ensure_ascii=False)}", "gray")

                skill_result = result.get("skill_result", {})
                if skill_result.get("success"):
                    # 根据 skill 类型显示不同的预览
                    if result['skill_called'] == "read_doc":
                        content_preview = skill_result.get("content", "")[:200]
                        print_colored(f"  文档内容预览: {content_preview}...", "gray")
                    elif result['skill_called'] == "list_files":
                        files = skill_result.get("files", [])
                        folders = skill_result.get("folders", [])
                        print_colored(f"  找到 {len(files)} 个文件, {len(folders)} 个文件夹", "gray")
                        if files:
                            print_colored(f"  文件示例: {', '.join(files[:5])}{'...' if len(files) > 5 else ''}", "gray")
                else:
                    print_colored(f"  Skill 执行失败: {skill_result.get('error')}", "red")

            print_colored(f"\n模型回复:", "blue")
            print(result.get("content", "无回复"))
        else:
            print_colored(f"✗ 失败: {result.get('error')}", "red")

    # 测试场景 - 多轮迭代模式
    print_section("多轮迭代模式测试（最多10轮）")

    iterative_test_cases = [
        "帮我了解整个项目的结构，包括有哪些主要目录和文档",
        "请分析 docs 目录下的所有配置文件，告诉我游戏有哪些配置",
    ]

    for i, test_input in enumerate(iterative_test_cases, 1):
        print_colored(f"\n【迭代测试 {i}】", "yellow")
        print_colored(f"用户输入: {test_input}", "white")
        print_colored("-" * 40, "gray")

        result = client.iterative_chat(test_input)

        if result["success"]:
            print_colored(f"\n✓ 迭代完成，共 {result['iterations']} 轮", "green")
            print_colored(f"✓ 任务完成状态: {'已完成' if result['is_completed'] else '未完成'}", "green")

            if result.get('skill_history'):
                print_colored(f"\n使用的 Skills:", "cyan")
                for item in result['skill_history']:
                    print_colored(f"  第{item['iteration']}轮: {item['skill']} - {item['args']}", "gray")

            print_colored(f"\n最终回复:", "blue")
            print(result.get("content", "无回复"))
        else:
            print_colored(f"✗ 失败: {result.get('error')}", "red")

    # 交互模式
    print_section("交互模式")
    print_colored("命令:", "cyan")
    print_colored("  1. 直接输入问题 - 使用单轮模式", "gray")
    print_colored("  2. /iter <问题>  - 使用多轮迭代模式（最多10轮）", "gray")
    print_colored("  3. quit/exit/q   - 退出", "gray")
    print()

    while True:
        try:
            user_input = input("\n\033[93m你: \033[0m").strip()
        except (EOFError, KeyboardInterrupt):
            print_colored("\n再见！", "green")
            break

        if not user_input:
            continue

        if user_input.lower() in ('quit', 'exit', 'q'):
            print_colored("再见！", "green")
            break

        # 检查是否使用迭代模式
        if user_input.startswith('/iter '):
            query = user_input[6:].strip()
            if not query:
                print_colored("请输入问题，例如: /iter 帮我分析项目结构", "yellow")
                continue

            print_colored("使用多轮迭代模式...", "cyan")
            result = client.iterative_chat(query)

            if result["success"]:
                print_colored(f"\n[迭代完成: {result['iterations']}轮]", "cyan")
                print_colored(f"助手: {result.get('content', '')}", "white")
            else:
                print_colored(f"错误: {result.get('error')}", "red")
        else:
            # 单轮模式
            print_colored("思考中...", "gray")
            result = client.chat_with_skills(user_input)

            if result["success"]:
                if result.get("skill_called"):
                    print_colored(f"[使用了工具: {result['skill_called']}]", "cyan")
                print_colored(f"\n助手: {result.get('content', '')}", "white")
            else:
                print_colored(f"错误: {result.get('error')}", "red")

    return 0


if __name__ == "__main__":
    sys.exit(main())
