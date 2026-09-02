"""后端一键启动

按依赖顺序启动 4 个后端服务：
  personaldb (9100) → simpleOutline (10001) → slide_agent (10011) → main_api (6800)

特性（对齐复现计划 11.2 / 13）：
  - 统一加载 backend/.env（子进程继承当前环境变量）
  - 端口占用检测：启动前检查，被占用则报错退出
  - 日志重定向：每个服务 stdout/stderr 追加写入 logs/<service>.log
  - 优雅停止：Ctrl+C 或任一服务提前退出时，逐级 terminate → 超时 kill
"""
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# (服务目录, 启动脚本, 默认端口) —— 顺序即依赖顺序
SERVICES = [
    ("personaldb", "main.py", 9100),
    ("simpleOutline", "main_api.py", 10001),
    ("slide_agent", "main_api.py", 10011),
    ("main_api", "main.py", 6800),
]

# 服务名 → 端口对应的环境变量名（允许在 .env 中覆盖）
PORT_ENV = {
    "personaldb": "PERSONALDB_PORT",
    "simpleOutline": "OUTLINE_API_PORT",
    "slide_agent": "CONTENT_API_PORT",
    "main_api": "MAIN_API_PORT",
}


def load_env() -> None:
    """加载 backend/.env（若存在）。子进程默认继承当前进程环境变量。"""
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env", override=False)
    except ImportError:
        pass  # 未装 python-dotenv 时各服务回落到内置默认值


def resolve_port(name: str, default: int) -> int:
    return int(os.getenv(PORT_ENV.get(name, ""), str(default)))


def port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def main() -> None:
    load_env()

    # 端口占用检测
    for name, _script, default_port in SERVICES:
        port = resolve_port(name, default_port)
        if port_in_use(port):
            print(f"[error] 端口 {port} 已被占用（{name}），请先停止对应进程。")
            sys.exit(1)

    log_dir = ROOT / "logs"
    log_dir.mkdir(exist_ok=True)

    procs: list[tuple[str, subprocess.Popen, object]] = []
    try:
        for name, script, _port in SERVICES:
            cwd = ROOT / name
            log_path = log_dir / f"{name}.log"
            print(f"[start] 启动 {name} ({script})，日志 → logs/{name}.log")
            log_f = open(log_path, "ab")  # 追加模式，保留历史日志
            p = subprocess.Popen(
                [sys.executable, script],
                cwd=cwd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
            )
            procs.append((name, p, log_f))
            time.sleep(0.5)

        print("\n✅ 后端 4 服务已启动，按 Ctrl+C 停止。")

        # 主进程监听：任一服务提前退出（如崩溃）则停止其余服务
        while True:
            time.sleep(0.5)
            if any(p.poll() is not None for _n, p, _f in procs):
                print("[stop] 检测到某服务退出，正在停止其余服务 …")
                break
    except KeyboardInterrupt:
        print("\n[stop] 正在停止所有服务 …")
    finally:
        for _name, p, _f in procs:
            if p.poll() is None:
                p.terminate()
        deadline = time.time() + 5
        for _name, p, _f in procs:
            try:
                p.wait(timeout=max(0.1, deadline - time.time()))
            except subprocess.TimeoutExpired:
                p.kill()
        for _name, _p, log_f in procs:
            log_f.close()
        print("[stop] 已全部停止。")


if __name__ == "__main__":
    main()
