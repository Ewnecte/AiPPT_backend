"""后端一键启动（骨架版）

按依赖顺序启动 4 个后端服务：
  personaldb (9100) → simpleOutline (10001) → slide_agent (10011) → main_api (6800)

骨架版仅负责拉起进程；真实实现建议补充：
  - 端口占用检测与清理
  - 优雅停止（信号传播）
  - 各服务日志写入 logs/<service>.log
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

# (服务目录, 启动脚本) —— 顺序即依赖顺序
SERVICES = [
    ("personaldb", "main.py"),
    ("simpleOutline", "main_api.py"),
    ("slide_agent", "main_api.py"),
    ("main_api", "main.py"),
]


def main():
    procs = []
    try:
        for name, script in SERVICES:
            cwd = os.path.join(ROOT, name)
            print(f"[start] 启动 {name}  ({script})")
            p = subprocess.Popen([sys.executable, script], cwd=cwd)
            procs.append((name, p))
            time.sleep(0.5)

        print("\n✅ 后端 4 服务已启动，按 Ctrl+C 停止。")
        for _, p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\n[stop] 正在停止所有服务 …")
        for name, p in procs:
            p.terminate()
        for name, p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("[stop] 已全部停止。")


if __name__ == "__main__":
    main()
