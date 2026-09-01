"""大纲 Agent 本地测试客户端（不走 A2A，直接测生成逻辑）。"""
import asyncio
import os

from agent import stream_outline


async def main():
    content = input("请输入 PPT 主题：").strip() or "新能源汽车行业发展趋势"
    language = os.getenv("OUTLINE_LANGUAGE", "中文")
    provider = os.getenv("MODEL_PROVIDER", "ali")
    model = os.getenv("LLM_MODEL", "qwen-turbo-latest")

    print(f"\n使用模型 {provider}/{model} 生成大纲（流式）…\n")
    async for delta in stream_outline(content, language, provider, model):
        print(delta, end="", flush=True)
    print("\n\n—— 生成结束 ——")


if __name__ == "__main__":
    asyncio.run(main())
