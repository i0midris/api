import os
import json
from distutils.util import strtobool

SECRET_KEY = os.environ["SECRET_KEY"]
DEBUG = bool(strtobool(os.getenv("FLASK_DEBUG", "false")))
LOG_FILE_SIZE = os.getenv("LOG_FILE_SIZE", "10485760")

# Multi-device configuration
def get_devices_config():
    """
    Load device configurations from environment variable or config file
    Expected format in .env:
    DEVICES_CONFIG='[
        {"id": 1, "name": "Main Entrance", "ip": "192.168.1.100", "port": 4370, "password": 0},
        {"id": 2, "name": "Back Door", "ip": "192.168.1.101", "port": 4370, "password": 0},
        {"id": 3, "name": "Office Floor", "ip": "192.168.1.102", "port": 4370, "password": 0}
    ]'
    
    Or from individual environment variables:
    DEVICE_1_IP=192.168.1.100
    DEVICE_1_NAME=Main Entrance
    DEVICE_2_IP=192.168.1.101
    DEVICE_2_NAME=Back Door
    etc.
    """
    devices = []
    
    # Method 1: JSON configuration
    devices_json = os.getenv('DEVICES_CONFIG')
    if devices_json:
        try:
            return json.loads(devices_json)
        except json.JSONDecodeError:
            pass
    
    # Method 2: Individual environment variables
    device_id = 1
    while True:
        device_ip = os.getenv(f'DEVICE_{device_id}_IP')
        if not device_ip:
            break
            
        device_config = {
            'id': device_id,
            'name': os.getenv(f'DEVICE_{device_id}_NAME', f'Device {device_id}'),
            'ip': device_ip,
            'port': int(os.getenv(f'DEVICE_{device_id}_PORT', '4370')),
            'password': int(os.getenv(f'DEVICE_{device_id}_PASSWORD', '0')),
            'timeout': int(os.getenv(f'DEVICE_{device_id}_TIMEOUT', '350')),
            'force_udp': bool(strtobool(os.getenv(f'DEVICE_{device_id}_FORCE_UDP', 'false')))
        }
        devices.append(device_config)
        device_id += 1
    
    # Fallback to single device for backward compatibility
    if not devices:
        single_ip = os.getenv('DEVICE_IP')
        if single_ip:
            devices.append({
                'id': 1,
                'name': 'Default Device',
                'ip': single_ip,
                'port': int(os.getenv('DEVICE_PORT', '4370')),
                'password': int(os.getenv('DEVICE_PASSWORD', '0')),
                'timeout': int(os.getenv('DEVICE_TIMEOUT', '350')),
                'force_udp': bool(strtobool(os.getenv('DEVICE_FORCE_UDP', 'false')))
            })
    
    return devices

DEVICES = get_devices_config()
