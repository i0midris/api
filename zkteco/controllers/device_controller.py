# zkteco/controllers/device_controller.py

from flask import Blueprint, jsonify, current_app
from zkteco.services.zk_service import ZkService
from zk import ZK

bp = Blueprint('device', __name__, url_prefix='/')


@bp.route('/device/capture', methods=['GET'])
def device_connect():
    """
    Connect to the first configured ZKTeco device.
    """
    devices = current_app.config.get('DEVICES', [])
    if not devices:
        return jsonify({"message": "No devices configured"}), 400

    dev = devices[0]
    ip   = dev.get('ip')
    port = dev.get('port')
    name = dev.get('name')

    try:
        ZkService(
            zk_class=ZK,
            ip=ip,
            port=port,
            verbose=current_app.config.get('DEBUG', False)
        )
        return jsonify({
            "message": f"Connected to {name} ({ip}:{port}) successfully"
        }), 200

    except Exception as e:
        return jsonify({
            "message": f"Error connecting to {name} ({ip}:{port}): {e}"
        }), 500



@bp.route('/devices/capture-all', methods=['GET'])
def capture_all_devices():
    devices = current_app.config.get('DEVICES', [])
    if not devices:
        return jsonify({"message": "No devices configured"}), 400

    results = {}
    for dev in devices:
        name = dev.get('name')
        ip   = dev.get('ip')
        port = dev.get('port')

        # Instantiate your service (this no longer blocks on connect in __init__)
        svc = ZkService(
            zk_class=ZK,
            ip=ip,
            port=port,
            verbose=current_app.config.get('DEBUG', False)
        )

        # Now explicitly try to connect (returns True/False)
        connected = svc.connect()

        results[name] = "connected" if connected else "offline"

    status_code = 200 if all(v == "connected" for v in results.values()) else 207
    return jsonify(results), status_code
