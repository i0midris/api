from zk import ZK
from typing import Type, Dict, List
from dotenv import load_dotenv
import requests
import subprocess
import os
import threading
from struct import unpack
from socket import timeout
import time
from distutils.util import strtobool
import logging
from logging.handlers import RotatingFileHandler
from concurrent.futures import ThreadPoolExecutor
import signal
import sys
from dataclasses import dataclass
from enum import Enum

load_dotenv()

# Configuration
@dataclass
class DeviceConfig:
    id: int
    name: str
    ip: str
    port: int = 4370
    password: int = 0
    timeout: int = None
    force_udp: bool = False

class ServiceStatus(Enum):
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"

class MultiDeviceLiveCaptureService:
    def __init__(self):
        self.setup_logging()
        self.devices: Dict[int, DeviceConfig] = {}
        self.capture_threads: Dict[int, threading.Thread] = {}
        self.device_wrappers: Dict[int, 'ZktecoWrapper'] = {}
        self.status = ServiceStatus.STARTING
        self.shutdown_event = threading.Event()
        self.load_device_configurations()
        self.setup_signal_handlers()

    def setup_logging(self):
        """Configure logging with rotation"""
        log_file_size = int(os.getenv('LOG_FILE_SIZE', 10485760))
        log_file_path = os.path.join(os.getcwd(), 'multi-live-capture.log')
        
        handler = RotatingFileHandler(log_file_path, maxBytes=log_file_size, backupCount=3)
        formatter = logging.Formatter('[%(asctime)s] %(levelname)s [Device-%(device_id)s] %(message)s')
        handler.setFormatter(formatter)
        
        self.logger = logging.getLogger("multi-device-live-capture")
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)

    def setup_signal_handlers(self):
        """Setup graceful shutdown handlers"""
        signal.signal(signal.SIGTERM, self.signal_handler)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGHUP, self.signal_handler)

    def signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        self.logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.shutdown()

    def load_device_configurations(self):
        """Load device configurations from environment"""
        # Method 1: JSON configuration
        devices_json = os.getenv('DEVICES_CONFIG')
        if devices_json:
            import json
            try:
                devices_data = json.loads(devices_json)
                for device_data in devices_data:
                    config = DeviceConfig(**device_data)
                    self.devices[config.id] = config
                return
            except json.JSONDecodeError as e:
                self.logger.error(f"Invalid JSON in DEVICES_CONFIG: {e}")

        # Method 2: Individual environment variables
        device_id = 1
        while True:
            device_ip = os.getenv(f'DEVICE_{device_id}_IP')
            if not device_ip:
                break
                
            config = DeviceConfig(
                id=device_id,
                name=os.getenv(f'DEVICE_{device_id}_NAME', f'Device {device_id}'),
                ip=device_ip,
                port=int(os.getenv(f'DEVICE_{device_id}_PORT', '4370')),
                password=int(os.getenv(f'DEVICE_{device_id}_PASSWORD', '0')),
                timeout=int(os.getenv(f'DEVICE_{device_id}_TIMEOUT', '350')) if os.getenv(f'DEVICE_{device_id}_TIMEOUT') else None,
                force_udp=bool(strtobool(os.getenv(f'DEVICE_{device_id}_FORCE_UDP', 'false')))
            )
            self.devices[config.id] = config
            device_id += 1

        # Fallback: Single device for backward compatibility
        if not self.devices:
            single_ip = os.getenv('DEVICE_IP')
            if single_ip:
                config = DeviceConfig(
                    id=1,
                    name='Default Device',
                    ip=single_ip,
                    port=int(os.getenv('DEVICE_PORT', '4370')),
                    password=int(os.getenv('DEVICE_PASSWORD', '0')),
                    timeout=int(os.getenv('DEVICE_TIMEOUT', '350')) if os.getenv('DEVICE_TIMEOUT') else None,
                    force_udp=bool(strtobool(os.getenv('DEVICE_FORCE_UDP', 'false')))
                )
                self.devices[1] = config

        self.logger.info(f"Loaded {len(self.devices)} device configurations")

    def start(self):
        """Start live capture for all configured devices"""
        self.status = ServiceStatus.STARTING
        self.logger.info("Starting multi-device live capture service...")

        if not self.devices:
            self.logger.error("No devices configured. Exiting.")
            self.status = ServiceStatus.ERROR
            return False

        # Start capture for each device in parallel
        with ThreadPoolExecutor(max_workers=len(self.devices)) as executor:
            futures = []
            for device_id, config in self.devices.items():
                future = executor.submit(self.start_device_capture, device_id, config)
                futures.append((device_id, future))

            # Wait for all devices to initialize
            for device_id, future in futures:
                try:
                    success = future.result(timeout=30)  # 30 second timeout per device
                    if success:
                        self.logger.info(f"Device {device_id} ({self.devices[device_id].name}) started successfully")
                    else:
                        self.logger.error(f"Device {device_id} ({self.devices[device_id].name}) failed to start")
                except Exception as e:
                    self.logger.error(f"Device {device_id} initialization error: {e}")

        self.status = ServiceStatus.RUNNING
        self.logger.info(f"Multi-device live capture service started with {len(self.device_wrappers)} active devices")

        # Start monitoring thread
        monitor_thread = threading.Thread(target=self.monitor_devices, daemon=True)
        monitor_thread.start()

        return True

    def start_device_capture(self, device_id: int, config: DeviceConfig) -> bool:
        """Start live capture for a specific device"""
        try:
            # Create device wrapper with enhanced logging
            wrapper = ZktecoWrapper(
                zk_class=ZK,
                ip=config.ip,
                port=config.port,
                verbose=bool(strtobool(os.getenv("FLASK_DEBUG", "false"))),
                timeout=config.timeout,
                password=config.password,
                force_udp=config.force_udp,
                device_id=device_id,
                device_name=config.name,
                logger=self.logger
            )

            if wrapper.zk:  # Only add if connection successful
                self.device_wrappers[device_id] = wrapper
                return True
            else:
                self.logger.error(f"Failed to initialize device {device_id} ({config.name})")
                return False

        except Exception as e:
            self.logger.error(f"Error starting capture for device {device_id}: {e}")
            return False

    def monitor_devices(self):
        """Monitor device health and restart if needed"""
        self.logger.info("Starting device monitoring thread")
        
        while not self.shutdown_event.is_set():
            try:
                # Check each device every 30 seconds
                for device_id, wrapper in list(self.device_wrappers.items()):
                    if not wrapper.is_healthy():
                        self.logger.warning(f"Device {device_id} ({wrapper.device_name}) is unhealthy, attempting restart...")
                        self.restart_device(device_id)

                # Wait before next check
                self.shutdown_event.wait(30)

            except Exception as e:
                self.logger.error(f"Error in device monitoring: {e}")
                self.shutdown_event.wait(30)

    def restart_device(self, device_id: int):
        """Restart a specific device"""
        try:
            if device_id in self.device_wrappers:
                # Stop existing wrapper
                wrapper = self.device_wrappers[device_id]
                wrapper.stop()
                del self.device_wrappers[device_id]

            # Restart device
            config = self.devices[device_id]
            if self.start_device_capture(device_id, config):
                self.logger.info(f"Device {device_id} ({config.name}) restarted successfully")
            else:
                self.logger.error(f"Failed to restart device {device_id} ({config.name})")

        except Exception as e:
            self.logger.error(f"Error restarting device {device_id}: {e}")

    def shutdown(self):
        """Gracefully shutdown all devices"""
        self.status = ServiceStatus.STOPPING
        self.logger.info("Shutting down multi-device live capture service...")

        # Signal shutdown to all threads
        self.shutdown_event.set()

        # Stop all device wrappers
        for device_id, wrapper in self.device_wrappers.items():
            try:
                self.logger.info(f"Stopping device {device_id} ({wrapper.device_name})")
                wrapper.stop()
            except Exception as e:
                self.logger.error(f"Error stopping device {device_id}: {e}")

        self.device_wrappers.clear()
        self.status = ServiceStatus.STOPPED
        self.logger.info("Multi-device live capture service stopped")

    def get_status(self):
        """Get service status"""
        return {
            'status': self.status.value,
            'total_devices': len(self.devices),
            'active_devices': len(self.device_wrappers),
            'devices': {
                device_id: {
                    'name': config.name,
                    'ip': config.ip,
                    'port': config.port,
                    'active': device_id in self.device_wrappers,
                    'healthy': self.device_wrappers[device_id].is_healthy() if device_id in self.device_wrappers else False
                }
                for device_id, config in self.devices.items()
            }
        }


class ZktecoWrapper:
    def __init__(self, zk_class: Type[ZK], ip, port=4370, verbose=False, timeout=None, 
                 password=0, force_udp=False, device_id=None, device_name=None, logger=None):
        self.device_id = device_id or 1
        self.device_name = device_name or f"Device_{ip}"
        self.ip = ip
        self.port = port
        self.logger = logger or logging.getLogger(__name__)
        self.zk = None
        self.live_capture_thread = None
        self.stop_event = threading.Event()
        self.last_ping_time = time.time()
        self.ping_interval = 15  # seconds
        
        try:
            self.zk = zk_class(
                ip,
                port=port,
                timeout=timeout,
                password=password,
                force_udp=force_udp,
                verbose=verbose
            )
            self.connect(enable_live_capture=True)
        except Exception as e:
            self.log_error(f"Could not connect to device on {ip}:{port} : {e}")

    def log_info(self, message):
        """Log info with device context"""
        self.logger.info(message, extra={'device_id': self.device_id})

    def log_error(self, message):
        """Log error with device context"""
        self.logger.error(message, extra={'device_id': self.device_id})

    def log_warning(self, message):
        """Log warning with device context"""
        self.logger.warning(message, extra={'device_id': self.device_id})

    def is_healthy(self) -> bool:
        """Check if device is healthy"""
        try:
            if not self.zk or not self.zk.is_connect:
                return False
            
            # Check if live capture thread is running
            if not self.live_capture_thread or not self.live_capture_thread.is_alive():
                return False
            
            # Check last ping time
            if time.time() - self.last_ping_time > self.ping_interval * 3:
                return False
                
            return self.zk.helper.test_ping()
        except Exception:
            return False

    def start_live_capture_thread(self):
        """Start live capture in separate thread"""
        if self.live_capture_thread and self.live_capture_thread.is_alive():
            return
            
        self.stop_event.clear()
        self.live_capture_thread = threading.Thread(
            target=self.live_capture,
            name=f"LiveCapture-{self.device_id}",
            daemon=True
        )
        self.live_capture_thread.start()
        self.log_info(f"Live capture thread started for {self.device_name}")

    def live_capture(self, new_timeout=None):
        """Enhanced live capture with better error handling"""
        try:
            self.zk.cancel_capture()
            self.zk.verify_user()
            self.enable_device()
            self.zk.reg_event(1)
            self.zk._ZK__sock.settimeout(new_timeout)
            self.zk.end_live_capture = False
            
            self.log_info(f"Live capture started for {self.device_name}")
            
            while not self.stop_event.is_set() and not self.zk.end_live_capture:
                try:
                    data_recv = self.zk._ZK__sock.recv(1032)
                    self.zk._ZK__ack_ok()
                    self.last_ping_time = time.time()

                    # Parse attendance data (same as original)
                    if self.zk.tcp:
                        size = unpack('<HHI', data_recv[:8])[2]
                        header = unpack('HHHH', data_recv[8:16])
                        data = data_recv[16:]
                    else:
                        size = len(data_recv)
                        header = unpack('<4H', data_recv[:8])
                        data = data_recv[8:]
                
                    if not header[0] == 500:
                        continue
                    if not len(data):
                        continue
                        
                    while len(data) >= 10:
                        user_id = self.parse_user_data(data)
                        if user_id:
                            self.send_attendance_request(user_id)
                            
                except timeout:
                    # Timeout is normal, just continue
                    continue
                except BlockingIOError:
                    continue
                except Exception as e:
                    self.log_error(f"Error in live capture loop: {e}")
                    time.sleep(1)  # Brief pause before retry
                    
        except Exception as e:
            self.log_error(f"Critical error in live capture: {e}")
        finally:
            try:
                self.zk._ZK__sock.settimeout(None)
                self.zk.reg_event(0)
                self.log_info(f"Live capture stopped for {self.device_name}")
            except Exception as e:
                self.log_error(f"Error cleaning up live capture: {e}")

    def parse_user_data(self, data) -> str:
        """Parse user ID from data packet"""
        try:
            data_len = len(data)
            user_id = None
            
            if data_len == 10:
                user_id, _status, _punch, _timehex = unpack('<HBB6s', data)
                data = data[10:]
            elif data_len == 12:
                user_id, _status, _punch, _timehex = unpack('<IBB6s', data)
                data = data[12:]
            elif data_len == 14:
                user_id, _status, _punch, _timehex, _other = unpack('<HBB6s4s', data)
                data = data[14:]
            elif data_len == 32:
                user_id, _status, _punch, _timehex = unpack('<24sBB6s', data[:32])
                data = data[32:]
            elif data_len == 36:
                user_id, _status, _punch, _timehex, _other = unpack('<24sBB6s4s', data[:36])
                data = data[36:]
            elif data_len == 37:
                user_id, _status, _punch, _timehex, _other = unpack('<24sBB6s5s', data[:37])
                data = data[37:]
            elif data_len >= 52:
                user_id, _status, _punch, _timehex, _other = unpack('<24sBB6s20s', data[:52])
                data = data[52:]
                
            if isinstance(user_id, int):
                return str(user_id)
            else:
                return (user_id.split(b'\x00')[0]).decode(errors='ignore')
                
        except Exception as e:
            self.log_error(f"Error parsing user data: {e}")
            return None

    def send_attendance_request(self, member_id):
        """Send attendance to backend with device context"""
        try:
            if self.stop_event.is_set():
                return
                
            backend_url = os.environ.get('BACKEND_URL')
            if not backend_url:
                self.log_error("BACKEND_URL not configured")
                return
                
            attendance_url = f"{backend_url}/check-in"
            payload = {
                'member_id': member_id,
                'device_id': self.device_id,
                'device_name': self.device_name,
                'timestamp': time.time()
            }
            
            response = requests.post(attendance_url, json=payload, timeout=5)
            response.raise_for_status()
            
            self.log_info(f"Attendance sent for user {member_id}")
            
        except requests.RequestException as e:
            self.log_error(f"Error sending attendance for user {member_id}: {e}")
        except Exception as e:
            self.log_error(f"Unexpected error in send_attendance_request: {e}")

    def connect(self, enable_live_capture=False):
        """Enhanced connection with env-driven retry + non-blocking first connect."""
        # fast-return if already good
        if self.zk and self.zk.is_connect and self.zk.helper.test_ping():
            if enable_live_capture:
                self.start_live_capture_thread()
            return True

        retry_count = 0
        # read from env (defaults to old values)
        max_retries = int(os.getenv("DEVICE_CONNECT_RETRIES", "10"))
        base_delay  = int(os.getenv("DEVICE_RETRY_DELAY",   "6"))

        while retry_count < max_retries and not getattr(self, "stop_event", threading.Event()).is_set():
            try:
                self.zk.connect()
                self.log_info(f"Connected to {self.device_name} successfully")
                retry_count = 0

                if enable_live_capture:
                    self.start_live_capture_thread()
                return True

            except Exception as e:
                retry_count += 1
                # only wait if we’re going to retry
                if retry_count < max_retries:
                    delay = min(base_delay * retry_count, 60)
                    self.log_warning(
                        f"Connection attempt {retry_count}/{max_retries} to {self.device_name} failed: {e!r}. "
                        f"Retrying in {delay}s…"
                    )
                    # block this wrapper’s thread, not the main app
                    getattr(self, "stop_event", threading.Event()).wait(delay)
                else:
                    self.log_error(f"Failed to connect after {max_retries} attempts to {self.device_name}")
                    break

        return False

    def enable_device(self):
        """Enable device with error handling"""
        try:
            if self.zk:
                self.zk.enable_device()
        except Exception as e:
            self.log_error(f"Error enabling device: {e}")

    def disable_device(self):
        """Disable device with error handling"""
        try:
            if self.zk:
                self.zk.disable_device()
        except Exception as e:
            self.log_error(f"Error disabling device: {e}")

    def stop(self):
        """Stop live capture and disconnect"""
        self.log_info(f"Stopping live capture for {self.device_name}")
        
        # Signal stop to threads
        self.stop_event.set()
        
        # Stop live capture
        if self.zk:
            try:
                self.zk.end_live_capture = True
                self.zk.reg_event(0)
            except Exception as e:
                self.log_error(f"Error stopping live capture: {e}")
        
        # Wait for thread to finish
        if self.live_capture_thread and self.live_capture_thread.is_alive():
            self.live_capture_thread.join(timeout=5)
            
        # Disconnect
        try:
            if self.zk and self.zk.is_connect:
                self.zk.disconnect()
                self.log_info(f"Disconnected from {self.device_name}")
        except Exception as e:
            self.log_error(f"Error disconnecting: {e}")


def main():
    """Main entry point"""
    try:
        service = MultiDeviceLiveCaptureService()
        
        if service.start():
            # Keep service running
            try:
                while service.status == ServiceStatus.RUNNING:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass
            finally:
                service.shutdown()
        else:
            print("Failed to start service")
            sys.exit(1)
            
    except Exception as e:
        print(f"Critical error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()