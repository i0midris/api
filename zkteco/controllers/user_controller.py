from flask import Blueprint, request, jsonify, current_app
from zkteco.services.multi_device_service import get_multi_device_service
from zkteco.validations import (create_user_schema, delete_user_schema, 
                               get_fingerprint_schema, delete_fingerprint_schema, validate_data)
import base64
from datetime import datetime

bp = Blueprint('user', __name__, url_prefix='/')
multi_device_service = get_multi_device_service()

def serialize_user(user):
    return {
        "id": user.user_id,
        "name": user.name,
        "groupId": user.group_id,
        "privilege": user.privilege,
        "uid": user.uid
    }

def serialize_template(template):
    return {
        "id": template.uid,
        "fid": template.fid,
        "valid": template.valid,
        "template": base64.b64encode(template.template).decode('utf-8'),
        "size": len(template.template) if template.template else 0
    }

# ===============================
# DEVICE MANAGEMENT ENDPOINTS
# ===============================

@bp.route('/devices', methods=['GET'])
def get_devices():
    """Get all configured devices and their status"""
    try:
        devices = multi_device_service.get_available_devices()
        return jsonify({
            "message": "Devices retrieved successfully",
            "data": devices,
            "count": len(devices)
        })
    except Exception as e:
        current_app.logger.error(f"Error retrieving devices: {e}")
        return jsonify({"message": f"Error retrieving devices: {str(e)}"}), 500

@bp.route('/device/<int:device_id>/info', methods=['GET'])
def get_device_info(device_id):
    """Get specific device information"""
    try:
        device_config = multi_device_service.get_device_info(device_id)
        if not device_config:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        device_info = multi_device_service.execute_on_device(device_id, 'get_device_info')
        
        return jsonify({
            "message": "Device info retrieved successfully",
            "data": {
                **device_info,
                "device_id": device_id,
                "device_name": device_config['name'],
                "ip": device_config['ip'],
                "port": device_config['port']
            }
        })
    except Exception as e:
        error_message = f"Error getting device {device_id} info: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/all-devices/info', methods=['GET'])
def get_all_devices_info():
    """Get information from all devices"""
    try:
        results = multi_device_service.execute_on_all_devices('get_device_info')
        
        devices_info = {}
        for device_id, result in results.items():
            device_config = multi_device_service.get_device_info(device_id)
            if result['success']:
                devices_info[device_id] = {
                    **result['data'],
                    "device_id": device_id,
                    "device_name": device_config['name'],
                    "ip": device_config['ip'],
                    "port": device_config['port'],
                    "status": "online"
                }
            else:
                devices_info[device_id] = {
                    "device_id": device_id,
                    "device_name": device_config['name'],
                    "ip": device_config['ip'],
                    "port": device_config['port'],
                    "status": "offline",
                    "error": result['error']
                }
        
        return jsonify({
            "message": "Device information retrieved from all devices",
            "data": devices_info,
            "summary": {
                "total_devices": len(devices_info),
                "online_devices": sum(1 for d in devices_info.values() if d.get('status') == 'online'),
                "offline_devices": sum(1 for d in devices_info.values() if d.get('status') != 'online')
            }
        })
    except Exception as e:
        error_message = f"Error getting all devices info: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/device/<int:device_id>/status', methods=['GET'])
def get_device_status(device_id):
    """Get specific device status"""
    try:
        device_config = multi_device_service.get_device_info(device_id)
        if not device_config:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        # Simple connectivity check
        users = multi_device_service.execute_on_device(device_id, 'get_all_users')
        return jsonify({
            "message": f"Device {device_config['name']} is accessible",
            "data": {
                "device_id": device_id,
                "device_name": device_config['name'],
                "status": "online",
                "users_count": len(users) if users else 0,
                "ip": device_config['ip'],
                "port": device_config['port']
            }
        })
    except Exception as e:
        device_config = multi_device_service.get_device_info(device_id)
        error_message = f"Device {device_id} not accessible: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({
            "message": error_message,
            "data": {
                "device_id": device_id,
                "device_name": device_config['name'] if device_config else f"Device {device_id}",
                "status": "offline",
                "error": str(e)
            }
        }), 503

# ===============================
# SINGLE DEVICE USER OPERATIONS
# ===============================

@bp.route('/device/<int:device_id>/user', methods=['POST'])
def create_user_on_device(device_id):
    """Create user on specific device"""
    data = request.json
    error = validate_data(data, create_user_schema.schema)
    if error:
        return jsonify({"error": error}), 400

    try:
        user_id = data.get('user_id')
        user_data = data.get('user_data')
        
        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        current_app.logger.info(f"Creating user {user_id} on device {device_id}")
        
        # Check if user exists
        if multi_device_service.execute_on_device(device_id, 'user_exists', user_id):
            return jsonify({"message": "User already exists on this device"}), 409
        
        multi_device_service.execute_on_device(device_id, 'create_user', user_id, user_data)
        
        return jsonify({
            "message": f"User created successfully on {device_info['name']}",
            "device_id": device_id,
            "device_name": device_info['name'],
            "user_id": user_id
        })
    except Exception as e:
        error_message = f"Error creating user on device {device_id}: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/device/<int:device_id>/users', methods=['GET'])
def get_users_from_device(device_id):
    """Get all users from specific device"""
    try:
        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        users = multi_device_service.execute_on_device(device_id, 'get_all_users')
        
        if not users:
            return jsonify({
                "message": f"No users found on {device_info['name']}",
                "data": [],
                "device_id": device_id,
                "device_name": device_info['name'],
                "count": 0
            })
        
        serialized_users = [serialize_user(user) for user in users]
        return jsonify({
            "message": f"Users retrieved from {device_info['name']}",
            "data": serialized_users,
            "device_id": device_id,
            "device_name": device_info['name'],
            "count": len(serialized_users)
        })
    except Exception as e:
        error_message = f"Error retrieving users from device {device_id}: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/device/<int:device_id>/user/<user_id>', methods=['GET'])
def get_user_from_device(device_id, user_id):
    """Get specific user from specific device"""
    try:
        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        user = multi_device_service.execute_on_device(device_id, 'get_user_by_id', int(user_id))
        if not user:
            return jsonify({"message": f"User {user_id} not found on {device_info['name']}"}), 404
        
        serialized_user = serialize_user(user)
        return jsonify({
            "message": f"User retrieved from {device_info['name']}",
            "data": serialized_user,
            "device_id": device_id,
            "device_name": device_info['name']
        })
    except Exception as e:
        error_message = f"Error retrieving user from device {device_id}: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/device/<int:device_id>/user/<user_id>', methods=['DELETE'])
def delete_user_from_device(device_id, user_id):
    """Delete user from specific device"""
    data = {"user_id": int(user_id)}
    error = validate_data(data, delete_user_schema.schema)
    if error:
        return jsonify({"error": error}), 400
    
    try:
        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        # Check if user exists before deletion
        if not multi_device_service.execute_on_device(device_id, 'user_exists', data["user_id"]):
            return jsonify({"message": f"User {user_id} not found on {device_info['name']}"}), 404
            
        current_app.logger.info(f"Deleting user {user_id} from device {device_id}")
        multi_device_service.execute_on_device(device_id, 'delete_user', data["user_id"])
        
        return jsonify({
            "message": f"User deleted successfully from {device_info['name']}",
            "device_id": device_id,
            "device_name": device_info['name'],
            "user_id": int(user_id)
        })
    except Exception as e:
        error_message = f"Error deleting user from device {device_id}: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

# ===============================
# MULTI-DEVICE USER OPERATIONS
# ===============================

@bp.route('/all-devices/user', methods=['POST'])
def create_user_on_all_devices():
    """Create user on all devices"""
    data = request.json
    error = validate_data(data, create_user_schema.schema)
    if error:
        return jsonify({"error": error}), 400

    try:
        user_id = data.get('user_id')
        user_data = data.get('user_data')
        
        current_app.logger.info(f"Creating user {user_id} on all devices")
        
        results = multi_device_service.execute_on_all_devices('create_user', user_id, user_data)
        
        success_count = sum(1 for r in results.values() if r['success'])
        total_devices = len(results)
        
        return jsonify({
            "message": f"User creation completed on {success_count}/{total_devices} devices",
            "results": results,
            "user_id": user_id,
            "summary": {
                "total_devices": total_devices,
                "successful": success_count,
                "failed": total_devices - success_count
            }
        })
    except Exception as e:
        error_message = f"Error creating user on all devices: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/selected-devices/user', methods=['POST'])
def create_user_on_selected_devices():
    """Create user on selected devices"""
    data = request.json
    
    # Validate user data
    user_error = validate_data({
        'user_id': data.get('user_id'),
        'user_data': data.get('user_data')
    }, create_user_schema.schema)
    if user_error:
        return jsonify({"error": user_error}), 400
    
    # Validate device selection
    device_ids = data.get('device_ids', [])
    if not device_ids or not isinstance(device_ids, list):
        return jsonify({"error": "device_ids must be a non-empty list"}), 400

    try:
        user_id = data.get('user_id')
        user_data = data.get('user_data')
        
        current_app.logger.info(f"Creating user {user_id} on devices: {device_ids}")
        
        results = multi_device_service.execute_on_selected_devices(
            device_ids, 'create_user', user_id, user_data
        )
        
        success_count = sum(1 for r in results.values() if r['success'])
        total_devices = len(results)
        
        return jsonify({
            "message": f"User creation completed on {success_count}/{total_devices} selected devices",
            "results": results,
            "user_id": user_id,
            "summary": {
                "selected_devices": len(device_ids),
                "processed_devices": total_devices,
                "successful": success_count,
                "failed": total_devices - success_count
            }
        })
    except Exception as e:
        error_message = f"Error creating user on selected devices: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/all-devices/users', methods=['GET'])
def get_users_from_all_devices():
    """Get users from all devices"""
    try:
        current_app.logger.info("Retrieving users from all devices")
        
        results = multi_device_service.execute_on_all_devices('get_all_users')
        
        # Process results to combine user data
        all_users_by_device = {}
        total_users = 0
        
        for device_id, result in results.items():
            device_name = result['device_name']
            if result['success']:
                users = result['data'] or []
                serialized_users = [serialize_user(user) for user in users]
                all_users_by_device[device_id] = {
                    "device_id": device_id,
                    "device_name": device_name,
                    "users": serialized_users,
                    "count": len(serialized_users),
                    "status": "success"
                }
                total_users += len(serialized_users)
            else:
                all_users_by_device[device_id] = {
                    "device_id": device_id,
                    "device_name": device_name,
                    "users": [],
                    "count": 0,
                    "status": "error",
                    "error": result['error']
                }
        
        return jsonify({
            "message": f"Retrieved users from all devices (Total: {total_users})",
            "data": all_users_by_device,
            "summary": {
                "total_devices": len(results),
                "total_users": total_users,
                "successful_devices": sum(1 for r in results.values() if r['success']),
                "failed_devices": sum(1 for r in results.values() if not r['success'])
            }
        })
    except Exception as e:
        error_message = f"Error retrieving users from all devices: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/all-devices/user/<user_id>', methods=['DELETE'])
def delete_user_from_all_devices(user_id):
    """Delete user from all devices"""
    data = {"user_id": int(user_id)}
    error = validate_data(data, delete_user_schema.schema)
    if error:
        return jsonify({"error": error}), 400
    
    try:
        current_app.logger.info(f"Deleting user {user_id} from all devices")
        
        results = multi_device_service.execute_on_all_devices('delete_user', data["user_id"])
        
        success_count = sum(1 for r in results.values() if r['success'])
        total_devices = len(results)
        
        return jsonify({
            "message": f"User deletion completed on {success_count}/{total_devices} devices",
            "results": results,
            "user_id": int(user_id),
            "summary": {
                "total_devices": total_devices,
                "successful": success_count,
                "failed": total_devices - success_count
            }
        })
    except Exception as e:
        error_message = f"Error deleting user from all devices: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/selected-devices/user/<user_id>', methods=['DELETE'])
def delete_user_from_selected_devices(user_id):
    """Delete user from selected devices"""
    data = request.json
    device_ids = data.get('device_ids', [])
    
    if not device_ids or not isinstance(device_ids, list):
        return jsonify({"error": "device_ids must be a non-empty list"}), 400

    user_data = {"user_id": int(user_id)}
    error = validate_data(user_data, delete_user_schema.schema)
    if error:
        return jsonify({"error": error}), 400
    
    try:
        current_app.logger.info(f"Deleting user {user_id} from devices: {device_ids}")
        
        results = multi_device_service.execute_on_selected_devices(
            device_ids, 'delete_user', user_data["user_id"]
        )
        
        success_count = sum(1 for r in results.values() if r['success'])
        total_devices = len(results)
        
        return jsonify({
            "message": f"User deletion completed on {success_count}/{total_devices} selected devices",
            "results": results,
            "user_id": int(user_id),
            "summary": {
                "selected_devices": len(device_ids),
                "processed_devices": total_devices,
                "successful": success_count,
                "failed": total_devices - success_count
            }
        })
    except Exception as e:
        error_message = f"Error deleting user from selected devices: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

# ===============================
# FINGERPRINT OPERATIONS - SINGLE DEVICE
# ===============================

@bp.route('/device/<int:device_id>/user/<user_id>/fingerprint', methods=['POST'])
def create_fingerprint_on_device(device_id, user_id):
    """Create fingerprint on specific device"""
    data = request.json
    temp_id = data.get('temp_id')
    
    if temp_id is None:
        return jsonify({"error": "temp_id is required"}), 400
    
    try:
        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        # Check if user exists
        if not multi_device_service.execute_on_device(device_id, 'user_exists', int(user_id)):
            return jsonify({"message": "User not found on this device"}), 404
            
        current_app.logger.info(f"Creating fingerprint for user {user_id} on device {device_id}")
        multi_device_service.execute_on_device(device_id, 'enroll_user', int(user_id), int(temp_id))
        
        return jsonify({
            "message": f"Fingerprint enrollment started on {device_info['name']}",
            "device_id": device_id,
            "device_name": device_info['name'],
            "user_id": int(user_id),
            "temp_id": int(temp_id)
        })
    except Exception as e:
        error_message = f"Error creating fingerprint on device {device_id}: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/device/<int:device_id>/user/<user_id>/fingerprint/<temp_id>', methods=['GET'])
def get_fingerprint_from_device(device_id, user_id, temp_id):
    """Get fingerprint from specific device"""
    data = {"user_id": int(user_id), "temp_id": int(temp_id)}
    error = validate_data(data, get_fingerprint_schema.schema)
    if error:
        return jsonify({"error": error}), 400
    
    try:
        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        # Check if user exists
        if not multi_device_service.execute_on_device(device_id, 'user_exists', data["user_id"]):
            return jsonify({"message": "User not found on this device"}), 404
            
        current_app.logger.info(f"Getting fingerprint for user {user_id} from device {device_id}")
        template = multi_device_service.execute_on_device(
            device_id, 'get_user_template', data["user_id"], data["temp_id"]
        )
        
        if not template:
            return jsonify({
                "message": f"No fingerprint template found on {device_info['name']}",
                "data": None,
                "device_id": device_id,
                "device_name": device_info['name']
            }), 404
            
        # Serialize template
        serialized_template = serialize_template(template)
        return jsonify({
            "message": f"Fingerprint retrieved from {device_info['name']}",
            "data": serialized_template,
            "device_id": device_id,
            "device_name": device_info['name']
        })
    except Exception as e:
        error_message = f"Error retrieving fingerprint from device {device_id}: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/device/<int:device_id>/user/<user_id>/fingerprint/<temp_id>', methods=['DELETE'])
def delete_fingerprint_from_device(device_id, user_id, temp_id):
    """Delete fingerprint from specific device"""
    data = {"user_id": int(user_id), "temp_id": int(temp_id)}
    error = validate_data(data, delete_fingerprint_schema.schema)
    if error:
        return jsonify({"error": error}), 400

    try:
        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        # Check if user exists
        if not multi_device_service.execute_on_device(device_id, 'user_exists', data["user_id"]):
            return jsonify({"message": "User not found on this device"}), 404
            
        current_app.logger.info(f"Deleting fingerprint for user {user_id} from device {device_id}")
        multi_device_service.execute_on_device(
            device_id, 'delete_user_template', data["user_id"], data["temp_id"]
        )
        
        return jsonify({
            "message": f"Fingerprint deleted from {device_info['name']}",
            "device_id": device_id,
            "device_name": device_info['name'],
            "user_id": int(user_id),
            "temp_id": int(temp_id)
        })
    except Exception as e:
        error_message = f"Error deleting fingerprint from device {device_id}: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/device/<int:device_id>/user/<user_id>/fingerprint/<temp_id>/restore', methods=['POST'])
def restore_fingerprint_to_device(device_id, user_id, temp_id):
    """Restore fingerprint to specific device"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "JSON data is required"}), 400

        encoded_template = data.get('template')
        if not encoded_template:
            return jsonify({"error": "Missing fingerprint template"}), 400

        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        # Validate user_id and temp_id
        try:
            user_id_int = int(user_id)
            finger_index = int(temp_id)
        except ValueError:
            return jsonify({"error": "Invalid user_id or temp_id (must be integers)"}), 400

        # Check user existence
        if not multi_device_service.execute_on_device(device_id, 'user_exists', user_id_int):
            return jsonify({"error": f"User {user_id_int} not found on {device_info['name']}"}), 404

        # Strict base64 decoding
        try:
            template_bytes = base64.b64decode(encoded_template, validate=True)
        except Exception as e:
            return jsonify({"error": f"Invalid base64 format: {str(e)}"}), 400

        # Template size sanity check
        template_size = len(template_bytes)
        if not (300 <= template_size <= 2000):
            current_app.logger.warning(
                f"⚠️ Suspicious fingerprint size: {template_size} bytes for user={user_id_int}, finger={finger_index}, device={device_id}"
            )
            return jsonify({"error": f"Invalid template size ({template_size} bytes)"}), 400

        # Log and restore
        current_app.logger.info(
            f"Restoring fingerprint | device={device_id}, user={user_id_int}, finger={finger_index}, size={template_size}"
        )

        # Set the fingerprint on the device
        success = multi_device_service.execute_on_device(
            device_id, 'set_user_template', user_id_int, finger_index, template_bytes
        )

        if not success:
            return jsonify({"error": f"Device {device_info['name']} rejected the template"}), 500

        return jsonify({
            "message": f"Fingerprint restored successfully to {device_info['name']}",
            "device_id": device_id,
            "device_name": device_info['name'],
            "user_id": user_id_int,
            "finger_index": finger_index
        })

    except Exception as e:
        current_app.logger.exception(f"❌ Exception while restoring fingerprint to device {device_id}")
        return jsonify({"error": f"Error restoring fingerprint: {str(e)}"}), 500

# ===============================
# FINGERPRINT OPERATIONS - MULTI DEVICE
# ===============================

@bp.route('/all-devices/user/<user_id>/fingerprint/<temp_id>/restore', methods=['POST'])
def restore_fingerprint_to_all_devices(user_id, temp_id):
    """Restore fingerprint to all devices"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "JSON data is required"}), 400

        encoded_template = data.get('template')
        if not encoded_template:
            return jsonify({"error": "Missing fingerprint template"}), 400

        # Validate user_id and temp_id
        try:
            user_id_int = int(user_id)
            finger_index = int(temp_id)
        except ValueError:
            return jsonify({"error": "Invalid user_id or temp_id (must be integers)"}), 400

        # Strict base64 decoding
        try:
            template_bytes = base64.b64decode(encoded_template, validate=True)
        except Exception as e:
            return jsonify({"error": f"Invalid base64 format: {str(e)}"}), 400

        # Template size sanity check
        template_size = len(template_bytes)
        if not (300 <= template_size <= 2000):
            return jsonify({"error": f"Invalid template size ({template_size} bytes)"}), 400

        current_app.logger.info(f"Restoring fingerprint to all devices | user={user_id_int}, finger={finger_index}")

        results = multi_device_service.execute_on_all_devices(
            'set_user_template', user_id_int, finger_index, template_bytes
        )

        success_count = sum(1 for r in results.values() if r['success'])
        total_devices = len(results)

        return jsonify({
            "message": f"Fingerprint restore completed on {success_count}/{total_devices} devices",
            "results": results,
            "user_id": user_id_int,
            "finger_index": finger_index,
            "summary": {
                "total_devices": total_devices,
                "successful": success_count,
                "failed": total_devices - success_count
            }
        })

    except Exception as e:
        current_app.logger.exception("❌ Exception while restoring fingerprint to all devices")
        return jsonify({"error": f"Error restoring fingerprint: {str(e)}"}), 500

@bp.route('/selected-devices/user/<user_id>/fingerprint/<temp_id>/restore', methods=['POST'])
def restore_fingerprint_to_selected_devices(user_id, temp_id):
    """Restore fingerprint to selected devices"""
    try:
        data = request.json
        if not data:
            return jsonify({"error": "JSON data is required"}), 400

        encoded_template = data.get('template')
        device_ids = data.get('device_ids', [])
        
        if not encoded_template:
            return jsonify({"error": "Missing fingerprint template"}), 400
        
        if not device_ids or not isinstance(device_ids, list):
            return jsonify({"error": "device_ids must be a non-empty list"}), 400

        # Validate user_id and temp_id
        try:
            user_id_int = int(user_id)
            finger_index = int(temp_id)
        except ValueError:
            return jsonify({"error": "Invalid user_id or temp_id (must be integers)"}), 400

        # Strict base64 decoding
        try:
            template_bytes = base64.b64decode(encoded_template, validate=True)
        except Exception as e:
            return jsonify({"error": f"Invalid base64 format: {str(e)}"}), 400

        # Template size sanity check
        template_size = len(template_bytes)
        if not (300 <= template_size <= 2000):
            return jsonify({"error": f"Invalid template size ({template_size} bytes)"}), 400

        current_app.logger.info(f"Restoring fingerprint to selected devices | user={user_id_int}, finger={finger_index}, devices={device_ids}")

        results = multi_device_service.execute_on_selected_devices(
            device_ids, 'set_user_template', user_id_int, finger_index, template_bytes
        )

        success_count = sum(1 for r in results.values() if r['success'])
        total_devices = len(results)

        return jsonify({
            "message": f"Fingerprint restore completed on {success_count}/{total_devices} selected devices",
            "results": results,
            "user_id": user_id_int,
            "finger_index": finger_index,
            "summary": {
                "selected_devices": len(device_ids),
                "processed_devices": total_devices,
                "successful": success_count,
                "failed": total_devices - success_count
            }
        })

    except Exception as e:
        current_app.logger.exception("❌ Exception while restoring fingerprint to selected devices")
        return jsonify({"error": f"Error restoring fingerprint: {str(e)}"}), 500

# ===============================
# ATTENDANCE OPERATIONS
# ===============================

@bp.route('/device/<int:device_id>/attendance', methods=['GET'])
def get_attendance_from_device(device_id):
    """Get attendance records from specific device"""
    try:
        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        # Get optional query params
        from_date_str = request.args.get('from')
        to_date_str = request.args.get('to')

        from_date = datetime.strptime(from_date_str, "%Y-%m-%d") if from_date_str else None
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else None
        if to_date:
            # Include the full end day
            to_date = to_date.replace(hour=23, minute=59, second=59)

        records = multi_device_service.execute_on_device(device_id, 'get_attendance')
        if not records:
            return jsonify({
                "message": f"No attendance records found on {device_info['name']}",
                "data": [],
                "device_id": device_id,
                "device_name": device_info['name'],
                "count": 0
            })

        data = []
        for r in records:
            ts = r.timestamp

            if from_date and ts < from_date:
                continue
            if to_date and ts > to_date:
                continue

            data.append({
                "user_id": r.user_id,
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "status": r.status,
                "punch": r.punch,
                "device_id": device_id,
                "device_name": device_info['name']
            })

        return jsonify({
            "message": f"Attendance records retrieved from {device_info['name']}",
            "data": data,
            "device_id": device_id,
            "device_name": device_info['name'],
            "count": len(data),
            "filters": {
                "from_date": from_date_str,
                "to_date": to_date_str
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error fetching attendance from device {device_id}: {e}")
        return jsonify({"message": f"Error: {str(e)}"}), 500

@bp.route('/all-devices/attendance', methods=['GET'])
def get_attendance_from_all_devices():
    """Get attendance records from all devices"""
    try:
        # Get optional query params
        from_date_str = request.args.get('from')
        to_date_str = request.args.get('to')

        from_date = datetime.strptime(from_date_str, "%Y-%m-%d") if from_date_str else None
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else None
        if to_date:
            # Include the full end day
            to_date = to_date.replace(hour=23, minute=59, second=59)

        current_app.logger.info("Retrieving attendance from all devices")
        
        results = multi_device_service.execute_on_all_devices('get_attendance')
        
        # Process results to combine attendance data
        all_attendance_by_device = {}
        all_attendance_combined = []
        total_records = 0
        
        for device_id, result in results.items():
            device_name = result['device_name']
            if result['success']:
                records = result['data'] or []
                
                device_attendance = []
                for r in records:
                    ts = r.timestamp

                    if from_date and ts < from_date:
                        continue
                    if to_date and ts > to_date:
                        continue

                    attendance_record = {
                        "user_id": r.user_id,
                        "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                        "status": r.status,
                        "punch": r.punch,
                        "device_id": device_id,
                        "device_name": device_name
                    }
                    device_attendance.append(attendance_record)
                    all_attendance_combined.append(attendance_record)

                all_attendance_by_device[device_id] = {
                    "device_id": device_id,
                    "device_name": device_name,
                    "attendance": device_attendance,
                    "count": len(device_attendance),
                    "status": "success"
                }
                total_records += len(device_attendance)
            else:
                all_attendance_by_device[device_id] = {
                    "device_id": device_id,
                    "device_name": device_name,
                    "attendance": [],
                    "count": 0,
                    "status": "error",
                    "error": result['error']
                }

        # Sort combined attendance by timestamp
        all_attendance_combined.sort(key=lambda x: x['timestamp'], reverse=True)

        return jsonify({
            "message": f"Retrieved attendance from all devices (Total: {total_records} records)",
            "data": {
                "by_device": all_attendance_by_device,
                "combined": all_attendance_combined
            },
            "summary": {
                "total_devices": len(results),
                "total_records": total_records,
                "successful_devices": sum(1 for r in results.values() if r['success']),
                "failed_devices": sum(1 for r in results.values() if not r['success'])
            },
            "filters": {
                "from_date": from_date_str,
                "to_date": to_date_str
            }
        })
    except Exception as e:
        current_app.logger.error(f"Error fetching attendance from all devices: {e}")
        return jsonify({"message": f"Error: {str(e)}"}), 500

# ===============================
# DEVICE CAPTURE ENDPOINTS
# ===============================

@bp.route('/device/<int:device_id>/capture', methods=['GET'])
def start_device_capture(device_id):
    """Start live capture on specific device"""
    try:
        from zkteco.services.zk_service import ZkService
        from zk import ZK
        
        device_info = multi_device_service.get_device_info(device_id)
        if not device_info:
            return jsonify({"message": f"Device {device_id} not found"}), 404

        # Start capture service for this device
        ZkService(
            zk_class=ZK,
            ip=device_info['ip'],
            port=device_info['port'],
            verbose=current_app.config.get('DEBUG', False)
        )

        return jsonify({
            "message": f"Live capture started on {device_info['name']}",
            "device_id": device_id,
            "device_name": device_info['name']
        })
    except Exception as e:
        error_message = f"Error starting capture on device {device_id}: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

# ===============================
# BACKWARD COMPATIBILITY ENDPOINTS
# ===============================

@bp.route('/user', methods=['POST'])
def create_user():
    """Create user (backward compatibility - uses first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available"}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    current_app.logger.info(f"Using device {first_device['id']} for backward compatibility")
    
    # Forward to single device endpoint
    return create_user_on_device(first_device['id'])

@bp.route('/users', methods=['GET'])
def get_all_users():
    """Get all users (backward compatibility - from first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available", "data": []}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    current_app.logger.info(f"Using device {first_device['id']} for backward compatibility")
    
    # Forward to single device endpoint
    return get_users_from_device(first_device['id'])

@bp.route('/user/<user_id>', methods=['GET'])
def get_user(user_id):
    """Get user (backward compatibility - from first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available"}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    
    # Forward to single device endpoint
    return get_user_from_device(first_device['id'], user_id)

@bp.route('/user/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Delete user (backward compatibility - from first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available"}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    
    # Forward to single device endpoint
    return delete_user_from_device(first_device['id'], user_id)

@bp.route('/user/<user_id>/fingerprint', methods=['POST'])
def create_fingerprint(user_id):
    """Create fingerprint (backward compatibility - on first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available"}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    
    # Forward to single device endpoint
    return create_fingerprint_on_device(first_device['id'], user_id)

@bp.route('/user/<user_id>/fingerprint/<temp_id>', methods=['DELETE'])
def delete_fingerprint(user_id, temp_id):
    """Delete fingerprint (backward compatibility - from first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available"}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    
    # Forward to single device endpoint
    return delete_fingerprint_from_device(first_device['id'], user_id, temp_id)

@bp.route('/user/<user_id>/fingerprint/<temp_id>', methods=['GET'])
def get_fingerprint(user_id, temp_id):
    """Get fingerprint (backward compatibility - from first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available"}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    
    # Forward to single device endpoint
    return get_fingerprint_from_device(first_device['id'], user_id, temp_id)

@bp.route('/user/<user_id>/fingerprint/<temp_id>/restore', methods=['POST'])
def restore_fingerprint(user_id, temp_id):
    """Restore fingerprint (backward compatibility - to first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available"}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    
    # Forward to single device endpoint
    return restore_fingerprint_to_device(first_device['id'], user_id, temp_id)

@bp.route('/device/info', methods=['GET'])
def get_device_info_legacy():
    """Get device info (backward compatibility - first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available"}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    
    # Forward to single device endpoint
    return get_device_info(first_device['id'])

@bp.route('/device/status', methods=['GET'])
def get_device_status_legacy():
    """Get device status (backward compatibility - first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available"}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    
    # Forward to single device endpoint
    return get_device_status(first_device['id'])

@bp.route('/attendance', methods=['GET'])
def get_attendance():
    """Get attendance (backward compatibility - from first available device)"""
    devices = multi_device_service.get_available_devices()
    if not devices:
        return jsonify({"message": "No devices available", "data": []}), 503
    
    # Use first available device for backward compatibility
    first_device = devices[0]
    
    # Forward to single device endpoint
    return get_attendance_from_device(first_device['id'])