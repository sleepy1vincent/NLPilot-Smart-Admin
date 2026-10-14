from flask import Blueprint, request
from response import success, error
from dao import purchases_dao


bp=Blueprint("purchases",__name__,url_prefix="/api")

@bp.route("/purchases",methods=["GET"])
def get_purchase():
    name=request.args.get("name")
    name = (name or "").replace(" ", "").strip()
    days=request.args.get("days",type=int)
    row=purchases_dao.get_purchase(name,days)
    return success(data=row,message=f"共{len(row)}条")