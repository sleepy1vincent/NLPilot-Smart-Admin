"""统一响应格式：所有接口都走这两个函数，HTTP 状态码 = 业务码。

返回协议（success / error）
===========================
    {
      "code":    int,           HTTP 状态码，同时作为业务码
      "message": str,           给用户看的一句话（不是给前端做判断用）
      "data":    any | null,    业务数据；失败时固定 null
    }

    成功：code = 200，data = 业务对象
    失败：code = 400~599（非法码一律降级 400），data = null
          error() 同时把 HTTP 状态码设成同一个值，前端可以直接按 http 状态分流
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