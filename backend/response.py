"""统一响应格式。HTTP 状态码 = 业务码，前端按状态码分类处理。

返回协议
--------
成功（HTTP 200）
    {"code": 200, "message": "success", "data": <任意>}

失败（HTTP 400-599）
    {"code": <HTTP 码>, "message": "原因", "data": null}
    非法码降级为 400
"""
from flask import jsonify


def success(data=None, message="success"):
    return jsonify({"code": 200, "message": message, "data": data})


def error(message="error", code=500, data=None):
    """
    错误响应。
    - code: 业务码 = HTTP 码（推荐 400-599）
    - 非法码降级 400
    """
    if code < 400 or code > 599:
        code = 400
    return jsonify({"code": code, "message": message, "data": data}), code