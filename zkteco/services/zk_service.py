from distutils.util import strtobool
import os
from zk.user import User
from zk.finger import Finger

from dotenv import load_dotenv
from zk import ZK, const
from typing import Type, Optional, List
import time
from zkteco.logger import app_logger

load_dotenv()

class ZkService:
    """
    Enhanced ZkService with improved error handling, logging, and connection management.
    This class handles communication with individual ZKTeco devices.
    """
    
    def __init__(self, zk_class: Type[ZK], ip: str, port: int = 4370, verbose: bool = False, 
                 timeout: int = 350, password: int = 0, force_udp: bool = False):
        """
        Initialize ZkService with device connection parameters.
        
        Args:
            zk_class: ZK class type for creating device connection
            ip: Device IP address
            port: Device port (default 4370)
            verbose: Enable verbose logging
            timeout: Connection timeout in seconds
            password: Device password (default 0)
            force_udp: Force UDP connection (default False)
        """
        self.ip = ip
        self.port = port
        self.timeout = timeout
        self.password = password
        self.force_udp = force_udp
        self.verbose = verbose
        self.zk = None
        
        try:
            self.zk = zk_class(
                ip,
                port=port,
                timeout=timeout,
                password=password,
                force_udp=force_udp,
                verbose=verbose
            )
            self.connect()
            app_logger.info(f"ZkService initialized successfully for {ip}:{port}")
        except Exception as e:
            app_logger.warning(f"Could not connect to ZKTeco device on {ip}:{port} : {e}")
            self.zk = None

    def is_connected(self) -> bool:
        """Check if device is currently connected"""
        try:
            return self.zk and self.zk.is_connect and self.zk.helper.test_ping()
        except Exception:
            return False

    def connect(self, max_retries: int = 3) -> bool:
        """
        Connect to ZKTeco device with retry logic.
        
        Args:
            max_retries: Maximum number of connection attempts
            
        Returns:
            bool: True if connected successfully, False otherwise
        """
        if not self.zk:
            app_logger.error(f"ZK instance not initialized for {self.ip}:{self.port}")
            return False
            
        if self.is_connected():
            return True

        retry_count = 0
        
        while retry_count < max_retries:
            try:
                self.zk.connect()
                app_logger.info(f"Connected to ZK device {self.ip}:{self.port} successfully")
                return True
            except Exception as e:
                retry_count += 1
                app_logger.warning(
                    f"Failed to connect to ZK device {self.ip}:{self.port}. "
                    f"Attempt {retry_count}/{max_retries}. Error: {e}"
                )
                if retry_count < max_retries:
                    # Exponential backoff with max 30s delay
                    delay = min(6 * retry_count, 30)
                    time.sleep(delay)
                else:
                    app_logger.error(f"Failed to connect after {max_retries} attempts to {self.ip}:{self.port}")
                    return False
        
        return False

    def disconnect(self) -> bool:
        """
        Disconnect from ZKTeco device.
        
        Returns:
            bool: True if disconnected successfully
        """
        try:
            if self.zk and self.zk.is_connect:
                self.zk.disconnect()
                app_logger.info(f"Disconnected from ZK device {self.ip}:{self.port}")
            return True
        except Exception as e:
            app_logger.error(f"Error disconnecting from ZK device {self.ip}:{self.port}: {e}")
            return False

    def enable_device(self) -> bool:
        """
        Enable the ZKTeco device.
        
        Returns:
            bool: True if enabled successfully
        """
        try:
            if self.zk:
                self.zk.enable_device()
                return True
        except Exception as e:
            app_logger.error(f"Error enabling device {self.ip}:{self.port}: {e}")
        return False

    def disable_device(self) -> bool:
        """
        Disable the ZKTeco device.
        
        Returns:
            bool: True if disabled successfully
        """
        try:
            if self.zk:
                self.zk.disable_device()
                return True
        except Exception as e:
            app_logger.error(f"Error disabling device {self.ip}:{self.port}: {e}")
        return False

    def _ensure_connection_and_disable(self) -> bool:
        """
        Ensure device is connected and disabled for safe operations.
        
        Returns:
            bool: True if ready for operations
        """
        if not self.connect():
            raise Exception(f"Could not connect to device {self.ip}:{self.port}")
        
        if not self.disable_device():
            app_logger.warning(f"Could not disable device {self.ip}:{self.port}, continuing anyway")
        
        return True

    def create_user(self, user_id: int, user_data: dict) -> bool:
        """
        Create a new user on the ZKTeco device.
        
        Args:
            user_id: Unique user identifier
            user_data: Dictionary containing user information
                - name: User's full name (required)
                - privilege: User privilege level (default: USER_DEFAULT)
                - password: User password (default: empty string)
                - group_id: User group ID (default: 0)
                - card: Card number (default: 0)
        
        Returns:
            bool: True if user created successfully
            
        Raises:
            Exception: If user creation fails
        """
        if not user_data.get('name'):
            raise ValueError("User name is required")
            
        try:
            self._ensure_connection_and_disable()
            
            self.zk.set_user(
                uid=user_id,
                name=user_data.get('name'),
                privilege=user_data.get('privilege', const.USER_DEFAULT),
                password=user_data.get('password', ''),
                group_id=user_data.get('group_id', 0),
                user_id=str(user_id),
                card=user_data.get('card', 0)
            )
            app_logger.info(f"User created successfully: user_id={user_id}, device={self.ip}:{self.port}")
            return True
            
        except Exception as e:
            app_logger.error(f"Error creating user {user_id} on {self.ip}:{self.port}: {e}")
            raise
        finally:
            self.enable_device()

    def get_all_users(self) -> Optional[List[User]]:
        """
        Retrieve all users from the ZKTeco device.
        
        Returns:
            List[User]: List of User objects, or None if operation fails
            
        Raises:
            Exception: If user retrieval fails
        """
        try:
            self._ensure_connection_and_disable()
            users = self.zk.get_users()
            app_logger.info(f"Retrieved {len(users) if users else 0} users from {self.ip}:{self.port}")
            return users
        except Exception as e:
            app_logger.error(f"Error retrieving users from {self.ip}:{self.port}: {e}")
            raise
        finally:
            self.enable_device()

    def get_user_by_id(self, user_id: int) -> Optional[User]:
        """
        Get a specific user by ID from the device.
        
        Args:
            user_id: User ID to search for
            
        Returns:
            User: User object if found, None otherwise
        """
        try:
            users = self.get_all_users()
            if not users:
                return None
                
            user = next((u for u in users if str(u.user_id) == str(user_id)), None)
            if user:
                app_logger.info(f"User {user_id} found on device {self.ip}:{self.port}")
            else:
                app_logger.info(f"User {user_id} not found on device {self.ip}:{self.port}")
            return user
        except Exception as e:
            app_logger.error(f"Error finding user {user_id} on {self.ip}:{self.port}: {e}")
            return None

    def user_exists(self, user_id: int) -> bool:
        """
        Check if a user exists on the device.
        
        Args:
            user_id: User ID to check
            
        Returns:
            bool: True if user exists, False otherwise
        """
        try:
            return self.get_user_by_id(user_id) is not None
        except Exception as e:
            app_logger.error(f"Error checking user existence {user_id} on {self.ip}:{self.port}: {e}")
            return False

    def delete_user(self, user_id: int) -> bool:
        """
        Delete a user from the ZKTeco device.
        
        Args:
            user_id: User ID to delete
            
        Returns:
            bool: True if user deleted successfully
            
        Raises:
            Exception: If user deletion fails
        """
        try:
            self._ensure_connection_and_disable()
            self.zk.delete_user(
                uid=user_id,
                user_id=str(user_id)
            )
            app_logger.info(f"User deleted successfully: user_id={user_id}, device={self.ip}:{self.port}")
            return True
        except Exception as e:
            app_logger.error(f"Error deleting user {user_id} from {self.ip}:{self.port}: {e}")
            raise
        finally:
            self.enable_device()

    def enroll_user(self, user_id: int, temp_id: int) -> bool:
        """
        Start fingerprint enrollment for a user.
        
        Args:
            user_id: User ID for enrollment
            temp_id: Template ID (finger index 0-9)
            
        Returns:
            bool: True if enrollment started successfully
            
        Raises:
            Exception: If enrollment fails to start
        """
        try:
            self._ensure_connection_and_disable()
            self.zk.enroll_user(
                uid=user_id,
                temp_id=temp_id,
                user_id=str(user_id)
            )
            app_logger.info(f"User enrollment started: user_id={user_id}, temp_id={temp_id}, device={self.ip}:{self.port}")
            return True
        except Exception as e:
            app_logger.error(f"Error enrolling user {user_id} on {self.ip}:{self.port}: {e}")
            raise
        finally:
            self.enable_device()

    def cancel_enroll_user(self) -> bool:
        """
        Cancel ongoing fingerprint enrollment.
        
        Returns:
            bool: True if cancellation successful
            
        Raises:
            Exception: If cancellation fails
        """
        try:
            if not self.connect():
                raise Exception(f"Could not connect to device {self.ip}:{self.port}")
                
            # Stop live capture if running
            if hasattr(self.zk, 'end_live_capture'):
                self.zk.end_live_capture = True
                
            self.disable_device()
            self.zk.cancel_capture()
            app_logger.info(f"User enrollment cancelled on device {self.ip}:{self.port}")
            return True
        except Exception as e:
            app_logger.error(f"Error cancelling enrollment on {self.ip}:{self.port}: {e}")
            raise
        finally:
            self.enable_device()

    def delete_user_template(self, user_id: int, temp_id: int) -> bool:
        """
        Delete a specific fingerprint template for a user.
        
        Args:
            user_id: User ID
            temp_id: Template ID (finger index)
            
        Returns:
            bool: True if template deleted successfully
            
        Raises:
            Exception: If template deletion fails
        """
        try:
            self._ensure_connection_and_disable()
            self.zk.delete_user_template(
                uid=user_id,
                temp_id=temp_id,
                user_id=str(user_id)
            )
            app_logger.info(f"Template deleted: user_id={user_id}, temp_id={temp_id}, device={self.ip}:{self.port}")
            return True
        except Exception as e:
            app_logger.error(f"Error deleting template for user {user_id} on {self.ip}:{self.port}: {e}")
            raise
        finally:
            self.enable_device()

    def get_user_template(self, user_id: int, temp_id: int) -> Optional[Finger]:
        """
        Retrieve a specific fingerprint template for a user.
        
        Args:
            user_id: User ID
            temp_id: Template ID (finger index)
            
        Returns:
            Finger: Finger template object if found, None otherwise
            
        Raises:
            Exception: If template retrieval fails
        """
        try:
            self._ensure_connection_and_disable()
            template = self.zk.get_user_template(
                uid=user_id,
                temp_id=temp_id,
                user_id=str(user_id)
            )
            if template:
                app_logger.info(f"Template retrieved: user_id={user_id}, temp_id={temp_id}, device={self.ip}:{self.port}")
            else:
                app_logger.warning(f"No template found: user_id={user_id}, temp_id={temp_id}, device={self.ip}:{self.port}")
            return template
        except Exception as e:
            app_logger.error(f"Error retrieving template for user {user_id} on {self.ip}:{self.port}: {e}")
            raise
        finally:
            self.enable_device()

    def set_user_template(self, user_id: int, temp_id: int, template_bytes: bytes) -> bool:
        """
        Set/restore a fingerprint template for a user.
        
        Args:
            user_id: User ID
            temp_id: Template ID (finger index)
            template_bytes: Binary fingerprint template data
            
        Returns:
            bool: True if template set successfully
            
        Raises:
            Exception: If template setting fails
        """
        try:
            self._ensure_connection_and_disable()

            # Validate template size
            template_size = len(template_bytes)
            if not (300 <= template_size <= 2000):
                raise ValueError(f"Invalid template size: {template_size} bytes (expected 300-2000)")

            # Get existing users to find the correct UID
            users = self.zk.get_users()
            user_map = {str(u.user_id): u for u in users} if users else {}

            # Create user if not found
            if str(user_id) not in user_map:
                app_logger.info(f"User {user_id} not found, creating on device {self.ip}:{self.port}")
                self.zk.set_user(
                    uid=int(user_id),
                    user_id=str(user_id),
                    name=f"user_{user_id}",
                    privilege=const.USER_DEFAULT,
                    password='',
                    group_id=0,
                    card=0
                )
                # Refresh user list
                users = self.zk.get_users()
                user_map = {str(u.user_id): u for u in users} if users else {}

            user = user_map.get(str(user_id))
            if not user:
                raise Exception(f"User {user_id} not found on device after creation attempt")

            # Create Finger object
            finger = Finger(uid=user.uid, fid=temp_id, template=template_bytes, valid=True)

            # Use HR_save_usertemplates for reliable template restoration
            self.zk.HR_save_usertemplates([
                [user, [finger]]
            ])

            app_logger.info(
                f"Template restored successfully | device={self.ip}:{self.port}, "
                f"user_id={user_id}, finger={temp_id}, size={template_size}"
            )
            return True

        except Exception as e:
            app_logger.error(
                f"Failed to restore template | device={self.ip}:{self.port}, "
                f"user={user_id}, finger={temp_id} | {e}"
            )
            raise

        finally:
            self.enable_device()

    def get_device_info(self) -> Optional[dict]:
        """
        Get comprehensive device information.
        
        Returns:
            dict: Device information including name, firmware, etc.
            None: If information retrieval fails
        """
        try:
            self.connect()
            
            # Get basic device info
            info = {
                'ip': self.ip,
                'port': self.port,
                'device_name': None,
                'firmware_version': None,
                'platform': None,
                'device_time': None,
                'users_count': 0,
                'templates_count': 0,
                'connection_status': 'connected' if self.is_connected() else 'disconnected'
            }
            
            # Try to get detailed info (some devices may not support all operations)
            try:
                info['device_name'] = self.zk.get_device_name()
            except:
                info['device_name'] = f"Device_{self.ip.replace('.', '_')}"
                
            try:
                info['firmware_version'] = self.zk.get_firmware_version()
            except:
                info['firmware_version'] = "Unknown"
                
            try:
                info['platform'] = self.zk.get_platform()
            except:
                info['platform'] = "Unknown"
                
            try:
                info['device_time'] = self.zk.get_time()
            except:
                info['device_time'] = None
                
            try:
                users = self.zk.get_users()
                info['users_count'] = len(users) if users else 0
            except:
                info['users_count'] = 0
                
            try:
                templates = self.zk.get_templates()
                info['templates_count'] = len(templates) if templates else 0
            except:
                info['templates_count'] = 0

            app_logger.info(f"Device info retrieved from {self.ip}:{self.port}: {info['device_name']}")
            return info
            
        except Exception as e:
            app_logger.error(f"Error getting device info from {self.ip}:{self.port}: {e}")
            return None

    def get_attendance(self) -> Optional[List]:
        """
        Retrieve attendance records from the device.
        
        Returns:
            List: List of attendance records, or None if retrieval fails
            
        Raises:
            Exception: If attendance retrieval fails
        """
        try:
            self._ensure_connection_and_disable()
            records = self.zk.get_attendance()
            app_logger.info(f"Retrieved {len(records) if records else 0} attendance records from {self.ip}:{self.port}")
            return records
        except Exception as e:
            app_logger.error(f"Error retrieving attendance records from {self.ip}:{self.port}: {e}")
            raise
        finally:
            self.enable_device()

    def clear_attendance(self) -> bool:
        """
        Clear all attendance records from the device.
        
        Returns:
            bool: True if records cleared successfully
            
        Raises:
            Exception: If clearing fails
        """
        try:
            self._ensure_connection_and_disable()
            self.zk.clear_attendance()
            app_logger.info(f"Attendance records cleared from device {self.ip}:{self.port}")
            return True
        except Exception as e:
            app_logger.error(f"Error clearing attendance from {self.ip}:{self.port}: {e}")
            raise
        finally:
            self.enable_device()

    def get_templates(self) -> Optional[List]:
        """
        Get all fingerprint templates from the device.
        
        Returns:
            List: List of fingerprint templates, or None if retrieval fails
        """
        try:
            self._ensure_connection_and_disable()
            templates = self.zk.get_templates()
            app_logger.info(f"Retrieved {len(templates) if templates else 0} templates from {self.ip}:{self.port}")
            return templates
        except Exception as e:
            app_logger.error(f"Error retrieving templates from {self.ip}:{self.port}: {e}")
            return None
        finally:
            self.enable_device()

    def test_voice(self, voice_id: int = 0) -> bool:
        """
        Test device voice/beep functionality.
        
        Args:
            voice_id: Voice ID to test (default: 0)
            
        Returns:
            bool: True if test successful
        """
        try:
            self.connect()
            self.zk.test_voice(voice_id)
            app_logger.info(f"Voice test successful on device {self.ip}:{self.port}")
            return True
        except Exception as e:
            app_logger.error(f"Error testing voice on {self.ip}:{self.port}: {e}")
            return False

    def restart_device(self) -> bool:
        """
        Restart the ZKTeco device.
        
        Returns:
            bool: True if restart command sent successfully
        """
        try:
            self.connect()
            self.zk.restart()
            app_logger.info(f"Restart command sent to device {self.ip}:{self.port}")
            return True
        except Exception as e:
            app_logger.error(f"Error restarting device {self.ip}:{self.port}: {e}")
            return False

    def poweroff_device(self) -> bool:
        """
        Power off the ZKTeco device.
        
        Returns:
            bool: True if poweroff command sent successfully
        """
        try:
            self.connect()
            self.zk.poweroff()
            app_logger.info(f"Power off command sent to device {self.ip}:{self.port}")
            return True
        except Exception as e:
            app_logger.error(f"Error powering off device {self.ip}:{self.port}: {e}")
            return False

    def get_device_status(self) -> dict:
        """
        Get comprehensive device status information.
        
        Returns:
            dict: Status information including connectivity, user count, etc.
        """
        status = {
            'ip': self.ip,
            'port': self.port,
            'connected': False,
            'ping_successful': False,
            'users_count': 0,
            'templates_count': 0,
            'last_error': None
        }
        
        try:
            # Test basic connectivity
            status['connected'] = self.is_connected()
            status['ping_successful'] = self.zk.helper.test_ping() if self.zk else False
            
            if status['connected']:
                # Get user count
                try:
                    users = self.get_all_users()
                    status['users_count'] = len(users) if users else 0
                except:
                    pass
                    
                # Get template count
                try:
                    templates = self.get_templates()
                    status['templates_count'] = len(templates) if templates else 0
                except:
                    pass
                    
        except Exception as e:
            status['last_error'] = str(e)
            app_logger.error(f"Error getting device status for {self.ip}:{self.port}: {e}")
        
        return status

    def __str__(self) -> str:
        """String representation of ZkService"""
        return f"ZkService({self.ip}:{self.port})"

    def __repr__(self) -> str:
        """Detailed string representation of ZkService"""
        return (f"ZkService(ip='{self.ip}', port={self.port}, "
                f"connected={self.is_connected()}, timeout={self.timeout})")

# Factory function for backward compatibility
def get_zk_service() -> ZkService:
    """
    Factory function to create a ZkService instance using environment variables.
    This maintains backward compatibility with single-device configurations.
    
    Returns:
        ZkService: Configured ZkService instance
    """
    return ZkService(
        zk_class=ZK,
        ip=os.environ.get('DEVICE_IP', '192.168.1.100'),
        port=int(os.environ.get('DEVICE_PORT', 4370)),
        verbose=bool(strtobool(os.getenv("FLASK_DEBUG", "false"))),
        timeout=int(os.environ.get('DEVICE_TIMEOUT', 350)),
        password=int(os.environ.get('DEVICE_PASSWORD', 0)),
        force_udp=bool(strtobool(os.getenv("DEVICE_FORCE_UDP", "false")))
    )