"""参数校验。"""


def validate_upload(user_id: str, file_id: str, has_file: bool, has_url: bool) -> None:
    """校验上传参数：id 必填、file 与 url 互斥。"""
    if not user_id or not file_id:
        raise ValueError("user_id 与 file_id 为必填项")
    if has_file == has_url:
        raise ValueError("file 与 url 必须且只能提供其中一个")
