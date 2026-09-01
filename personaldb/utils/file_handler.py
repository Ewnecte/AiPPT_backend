"""文件落地：保存上传内容、下载 URL。"""
import os
import tempfile
import uuid

import httpx

DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "aippt_download")


def _ensure_dir() -> str:
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    return DOWNLOAD_DIR


def save_upload(content: bytes, filename: str) -> str:
    """把上传文件内容写入临时目录，返回路径。"""
    ext = os.path.splitext(filename)[1] or ".bin"
    path = os.path.join(_ensure_dir(), f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as f:
        f.write(content)
    return path


def download_url(url: str) -> str:
    """下载 URL 到临时目录，返回本地路径。"""
    resp = httpx.get(url, follow_redirects=True, timeout=120)
    resp.raise_for_status()
    ext = os.path.splitext(url.split("?")[0].split("#")[0])[1] or ".html"
    path = os.path.join(_ensure_dir(), f"{uuid.uuid4().hex}{ext}")
    with open(path, "wb") as f:
        f.write(resp.content)
    return path
