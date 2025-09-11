from flask import jsonify
from . import api_bp
from .. import read_service as rs

@api_bp.get("/summary")
def api_summary():
    return jsonify(rs.get_summary())
