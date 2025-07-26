from flask import Blueprint, request, jsonify
from zkteco.services.zk_service import get_zk_service
from zkteco.validations import create_user_schema, delete_user_schema, get_fingerprint_schema, delete_fingerprint_schema, validate_data
from flask import current_app
import base64
from datetime import datetime


bp = Blueprint('user', __name__, url_prefix='/')
zk_service = get_zk_service()

@bp.route('/user', methods=['POST'])
def create_user():
    data = request.json

    # Validate against the create user schema
    error = validate_data(data, create_user_schema.schema)
    if error:
        return jsonify({"error": error}), 400

    try:
        user_id = data.get('user_id')
        user_data = data.get('user_data')

        current_app.logger.info(f"Creating user with ID: {user_id} and Data: {user_data}")
        
        # Check if user already exists
        if zk_service.user_exists(user_id):
            current_app.logger.warning(f"User {user_id} already exists")
            return jsonify({"message": "User already exists"}), 409
    
        zk_service.create_user(user_id, user_data)
        return jsonify({"message": "User added successfully"})
    except Exception as e:
        error_message = f"Error creating user: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

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

@bp.route('/users', methods=['GET'])
def get_all_users():
    try:
        users = zk_service.get_all_users()
        if not users:
            return jsonify({"message": "No users found", "data": []})
        
        # Serialize each User object to a dictionary
        serialized_users = [serialize_user(user) for user in users]
        return jsonify({"message": "Users retrieved successfully", "data": serialized_users})
    except Exception as e:
        error_message = f"Error retrieving users: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/user/<user_id>', methods=['GET'])
def get_user(user_id):
    try:
        user = zk_service.get_user_by_id(int(user_id))
        if not user:
            return jsonify({"message": "User not found"}), 404
        
        serialized_user = serialize_user(user)
        return jsonify({"message": "User retrieved successfully", "data": serialized_user})
    except Exception as e:
        error_message = f"Error retrieving user: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/user/<user_id>', methods=['DELETE'])
def delete_user(user_id):
    data = {"user_id": int(user_id)}

    error = validate_data(data, delete_user_schema.schema)
    if error:
        return jsonify({"error": error}), 400
    
    try:
        # Check if user exists before deletion
        if not zk_service.user_exists(data["user_id"]):
            return jsonify({"message": "User not found"}), 404
            
        current_app.logger.info(f"Deleting user with ID: {user_id}")
        zk_service.delete_user(data["user_id"])
        return jsonify({"message": "User deleted successfully"})
    except Exception as e:
        error_message = f"Error deleting user: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/user/<user_id>/fingerprint', methods=['POST'])
def create_fingerprint(user_id):
    data = request.json
    temp_id = data.get('temp_id')
    
    if temp_id is None:
        return jsonify({"error": "temp_id is required"}), 400
    
    try:
        # Check if user exists
        if not zk_service.user_exists(int(user_id)):
            return jsonify({"message": "User not found"}), 404
            
        current_app.logger.info(f"Creating fingerprint for user with ID: {user_id} and finger index: {temp_id}")
        zk_service.enroll_user(int(user_id), int(temp_id))
        return jsonify({"message": "Fingerprint enrollment started successfully"})
    except Exception as e:
        error_message = f"Error creating fingerprint: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/user/<user_id>/fingerprint/<temp_id>', methods=['DELETE'])
def delete_fingerprint(user_id, temp_id):
    data = {"user_id": int(user_id), "temp_id": int(temp_id)}

    error = validate_data(data, delete_fingerprint_schema.schema)
    if error:
        return jsonify({"error": error}), 400

    try:
        # Check if user exists
        if not zk_service.user_exists(data["user_id"]):
            return jsonify({"message": "User not found"}), 404
            
        current_app.logger.info(f"Deleting fingerprint for user with ID: {user_id} and finger index: {temp_id}")
        zk_service.delete_user_template(data["user_id"], data["temp_id"])
        return jsonify({"message": "Fingerprint deleted successfully"})
    except Exception as e:
        error_message = f"Error deleting fingerprint: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/user/<user_id>/fingerprint/<temp_id>', methods=['GET'])
def get_fingerprint(user_id, temp_id):
    data = {"user_id": int(user_id), "temp_id": int(temp_id)}

    error = validate_data(data, get_fingerprint_schema.schema)
    if error:
        return jsonify({"error": error}), 400
    
    try:
        # Check if user exists
        if not zk_service.user_exists(data["user_id"]):
            return jsonify({"message": "User not found"}), 404
            
        current_app.logger.info(f"Getting fingerprint for user with ID: {user_id} and finger index: {temp_id}")
        template = zk_service.get_user_template(data["user_id"], data["temp_id"])
        
        if not template:
            return jsonify({"message": "No template found", "data": None}), 404
            
        # Serialize template
        serialized_template = serialize_template(template)
        current_app.logger.info(f"Fingerprint retrieved successfully for user {user_id}")
        return jsonify({"message": "Fingerprint retrieved successfully", "data": serialized_template})
    except Exception as e:
        error_message = f"Error retrieving fingerprint: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/user/<user_id>/fingerprint/<temp_id>/restore', methods=['POST'])
def restore_fingerprint(user_id, temp_id):
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

        # Check user existence
        if not zk_service.user_exists(user_id_int):
            return jsonify({"error": f"User {user_id_int} not found on device"}), 404

        # Strict base64 decoding
        try:
            template_bytes = base64.b64decode(encoded_template, validate=True)
        except Exception as e:
            return jsonify({"error": f"Invalid base64 format: {str(e)}"}), 400

        # Template size sanity check
        template_size = len(template_bytes)
        if not (300 <= template_size <= 2000):
            current_app.logger.warning(f"⚠️ Suspicious fingerprint size: {template_size} bytes for user={user_id_int}, finger={finger_index}")
            return jsonify({"error": f"Invalid template size ({template_size} bytes)"}), 400

        # Log and restore
        current_app.logger.info(
            f"Restoring fingerprint | user={user_id_int}, finger={finger_index}, size={template_size}"
        )

        # Set the fingerprint on the device
        success = zk_service.set_user_template(user_id_int, finger_index, template_bytes)

        if not success:
            return jsonify({"error": "ZKTeco device rejected the template"}), 500

        return jsonify({
            "message": "Fingerprint restored successfully",
            "user_id": user_id_int,
            "finger_index": finger_index
        })

    except Exception as e:
        current_app.logger.exception("❌ Exception while restoring fingerprint")
        return jsonify({"error": f"Error restoring fingerprint: {str(e)}"}), 500


@bp.route('/device/info', methods=['GET'])
def get_device_info():
    try:
        info = zk_service.get_device_info()
        if not info:
            return jsonify({"message": "Could not retrieve device information"}), 500
        return jsonify({"message": "Device info retrieved successfully", "data": info})
    except Exception as e:
        error_message = f"Error getting device info: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({"message": error_message}), 500

@bp.route('/device/status', methods=['GET'])
def get_device_status():
    try:
        # Simple connectivity check
        users = zk_service.get_all_users()
        return jsonify({
            "message": "Device is accessible",
            "status": "online",
            "users_count": len(users) if users else 0
        })
    except Exception as e:
        error_message = f"Device not accessible: {str(e)}"
        current_app.logger.error(error_message)
        return jsonify({
            "message": error_message,
            "status": "offline"
        }), 503

from datetime import datetime

@bp.route('/attendance', methods=['GET'])
def get_attendance():
    try:
        # Get optional query params
        from_date_str = request.args.get('from')
        to_date_str = request.args.get('to')

        from_date = datetime.strptime(from_date_str, "%Y-%m-%d") if from_date_str else None
        to_date = datetime.strptime(to_date_str, "%Y-%m-%d") if to_date_str else None
        if to_date:
            # Include the full end day
            to_date = to_date.replace(hour=23, minute=59, second=59)

        records = zk_service.get_attendance()
        if not records:
            return jsonify({"message": "No attendance records found", "data": []})

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
                "punch": r.punch
            })

        return jsonify({"message": "Filtered attendance retrieved", "data": data})
    except Exception as e:
        current_app.logger.error(f"Error fetching attendance: {e}")
        return jsonify({"message": f"Error: {str(e)}"}), 500

