
from typing import Dict, List, Optional, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from zk import ZK
from zkteco.services.zk_service import ZkService
from zkteco.logger import app_logger
from zkteco.config.settings import DEVICES

class MultiDeviceService:
    def __init__(self):
        self.devices: Dict[int, ZkService] = {}
        self.device_configs: Dict[int, dict] = {}
        self.lock = threading.Lock()
        self._initialize_devices()
    
    def _initialize_devices(self):
        """Initialize all configured devices"""
        for device_config in DEVICES:
            device_id = device_config['id']
            self.device_configs[device_id] = device_config
            
            try:
                zk_service = ZkService(
                    zk_class=ZK,
                    ip=device_config['ip'],
                    port=device_config['port'],
                    timeout=device_config.get('timeout', 350),
                    password=device_config.get('password', 0),
                    force_udp=device_config.get('force_udp', False),
                    verbose=False
                )
                self.devices[device_id] = zk_service
                app_logger.info(f"Device {device_id} ({device_config['name']}) initialized successfully")
            except Exception as e:
                app_logger.error(f"Failed to initialize device {device_id}: {e}")
    
    def get_device(self, device_id: int) -> Optional[ZkService]:
        """Get a specific device service"""
        return self.devices.get(device_id)
    
    def get_all_devices(self) -> Dict[int, ZkService]:
        """Get all device services"""
        return self.devices.copy()
    
    def get_device_info(self, device_id: int) -> Optional[dict]:
        """Get device configuration info"""
        return self.device_configs.get(device_id)
    
    def get_available_devices(self) -> List[dict]:
        """Get list of all configured devices with their status"""
        devices_info = []
        for device_id, config in self.device_configs.items():
            device_service = self.devices.get(device_id)
            status = "offline"
            
            if device_service:
                try:
                    # Quick connectivity test
                    device_service.get_all_users()
                    status = "online"
                except:
                    status = "offline"
            
            devices_info.append({
                "id": device_id,
                "name": config['name'],
                "ip": config['ip'],
                "port": config['port'],
                "status": status
            })
        
        return devices_info
    
    def execute_on_device(self, device_id: int, operation: str, *args, **kwargs):
        """Execute an operation on a specific device"""
        device = self.get_device(device_id)
        if not device:
            raise ValueError(f"Device {device_id} not found")
        
        method = getattr(device, operation, None)
        if not method:
            raise ValueError(f"Operation '{operation}' not supported")
        
        return method(*args, **kwargs)
    
    def execute_on_all_devices(self, operation: str, *args, **kwargs) -> Dict[int, Any]:
        """Execute an operation on all devices concurrently"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=len(self.devices)) as executor:
            # Submit tasks for all devices
            future_to_device = {
                executor.submit(self._safe_execute, device_id, operation, *args, **kwargs): device_id
                for device_id in self.devices.keys()
            }
            
            # Collect results
            for future in as_completed(future_to_device):
                device_id = future_to_device[future]
                try:
                    results[device_id] = {
                        "success": True,
                        "data": future.result(),
                        "device_name": self.device_configs[device_id]['name']
                    }
                except Exception as e:
                    results[device_id] = {
                        "success": False,
                        "error": str(e),
                        "device_name": self.device_configs[device_id]['name']
                    }
                    app_logger.error(f"Operation '{operation}' failed on device {device_id}: {e}")
        
        return results
    
    def _safe_execute(self, device_id: int, operation: str, *args, **kwargs):
        """Safely execute operation with error handling"""
        return self.execute_on_device(device_id, operation, *args, **kwargs)
    
    def execute_on_selected_devices(self, device_ids: List[int], operation: str, *args, **kwargs) -> Dict[int, Any]:
        """Execute an operation on selected devices"""
        results = {}
        
        with ThreadPoolExecutor(max_workers=len(device_ids)) as executor:
            future_to_device = {
                executor.submit(self._safe_execute, device_id, operation, *args, **kwargs): device_id
                for device_id in device_ids if device_id in self.devices
            }
            
            for future in as_completed(future_to_device):
                device_id = future_to_device[future]
                try:
                    results[device_id] = {
                        "success": True,
                        "data": future.result(),
                        "device_name": self.device_configs[device_id]['name']
                    }
                except Exception as e:
                    results[device_id] = {
                        "success": False,
                        "error": str(e),
                        "device_name": self.device_configs[device_id]['name']
                    }
        
        return results

# Global instance
multi_device_service = MultiDeviceService()

def get_multi_device_service() -> MultiDeviceService:
    return multi_device_service
