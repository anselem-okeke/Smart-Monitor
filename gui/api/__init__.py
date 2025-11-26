from flask import Blueprint
api_bp = Blueprint("api", __name__)
# Import modules so their routes attach to api_bp
from . import summary, hosts, alerts,stream, network, smart, services, k8s # noqa
