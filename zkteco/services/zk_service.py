from distutils.util import strtobool
import os
from zk.user import User
from zk.finger import Finger

from dotenv import load_dotenv
from zk import ZK, const
from typing import Type
import time
from zkteco.logger import app_logger

load_dotenv()

class ZkService:
    def __init__(self, zk_class: Type[ZK], ip, port=4370, verbose=False, timeout=350, password=0, force_udp=False):
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
        except Exception as e:
            app_logger.warning(f"Could not connect to Zkteco device on {ip}:{port} : {e}")

    def create_user(self, user_id, user_data):
        try:
            zk_instance = self.zk
            self.connect()
            self.disable_device()
            
            zk_instance.set_user(
                uid=user_id,
                name=user_data.get('name'),
                privilege=user_data.get('privilege', const.USER_DEFAULT),
                password=user_data.get('password', ''),
                group_id=user_data.get('group_id', 0),
                user_id=str(user_id),
                card=user_data.get('card', 0)
            )
            app_logger.info(f"User created successfully: user_id={user_id}")
        except Exception as e:
            app_logger.error(f"Error creating user {user_id}: {e}")
            raise
        finally:
            self.enable_device()

    def get_all_users(self):
        try:
            zk_instance = self.zk
            self.connect()
            self.disable_device()
            users = zk_instance.get_users()
            app_logger.info(f"Retrieved {len(users) if users else 0} users")
            return users
        except Exception as e:
            app_logger.error(f"Error retrieving users: {e}")
            raise
        finally:
            self.enable_device()

    def delete_user(self, user_id):
        try:
            zk_instance = self.zk
            self.connect()
            self.disable_device()
            zk_instance.delete_user(
                uid=user_id,
                user_id=str(user_id)
            )
            app_logger.info(f"User deleted successfully: user_id={user_id}")
        except Exception as e:
            app_logger.error(f"Error deleting user {user_id}: {e}")
            raise
        finally:
            self.enable_device()
    
    def enroll_user(self, user_id, temp_id):
        try:
            zk_instance = self.zk
            self.connect()
            self.disable_device()
            zk_instance.enroll_user(
                uid = user_id,
                temp_id = temp_id,
                user_id = str(user_id)
            )
            app_logger.info(f"User enrollment started: user_id={user_id}, temp_id={temp_id}")
        except Exception as e:
            app_logger.error(f"Error enrolling user {user_id}: {e}")
            raise
        finally:
            self.enable_device()
            
    def cancel_enroll_user(self):
        try:
            zk_instance = self.zk
            self.connect()
            self.zk.end_live_capture = True
            self.disable_device()
            zk_instance.cancel_capture()
            app_logger.info("User enrollment cancelled")
        except Exception as e:
            app_logger.error(f"Error cancelling enrollment: {e}")
            raise
        finally:
            self.enable_device()
    
    def delete_user_template(self, user_id, temp_id):
        try:
            zk_instance = self.zk
            self.connect()
            self.disable_device()
            zk_instance.delete_user_template(
                uid = user_id,
                temp_id = temp_id,
                user_id= str(user_id)
            )
            app_logger.info(f"Template deleted: user_id={user_id}, temp_id={temp_id}")
        except Exception as e:
            app_logger.error(f"Error deleting template for user {user_id}: {e}")
            raise
        finally:
            self.enable_device()
    
    def get_user_template(self, user_id, temp_id):
        try:
            zk_instance = self.zk
            self.connect()
            self.disable_device()
            template = zk_instance.get_user_template(
                uid = user_id,
                temp_id = temp_id,
                user_id = str(user_id)
            )
            if template:
                app_logger.info(f"Template retrieved: user_id={user_id}, temp_id={temp_id}")
            else:
                app_logger.warning(f"No template found: user_id={user_id}, temp_id={temp_id}")
            return template
        except Exception as e:
            app_logger.error(f"Error retrieving template for user {user_id}: {e}")
            raise
        finally:
            self.enable_device()



    def set_user_template(self, user_id, temp_id, template_bytes):
        try:
            self.connect()
            self.disable_device()

            # Get existing users
            users = self.zk.get_users()
            user_map = {str(u.user_id): u for u in users}

            # Create user if not found
            if str(user_id) not in user_map:
                self.zk.set_user(
                    uid=int(user_id),
                    user_id=str(user_id),
                    name=f"user_{user_id}"
                )
                users = self.zk.get_users()
                user_map = {str(u.user_id): u for u in users}

            user = user_map.get(str(user_id))
            if not user:
                raise Exception(f"User {user_id} not found on device.")

            # Construct Finger object
            finger = Finger(uid=user.uid, fid=temp_id, template=template_bytes, valid=True)

            # Restore with HR_save_usertemplates
            self.zk.HR_save_usertemplates([
                [user, [finger]]
            ])

            app_logger.info(f"Template restored | user_id={user_id}, finger={temp_id}, size={len(template_bytes)}")
            return True

        except Exception as e:
            app_logger.error(f"Failed to restore template | user={user_id}, finger={temp_id} | {e}")
            raise

        finally:
            self.enable_device()


    def get_user_by_id(self, user_id):
        """Helper method to get a specific user by ID"""
        try:
            users = self.get_all_users()
            user = next((u for u in users if str(u.user_id) == str(user_id)), None)
            return user
        except Exception as e:
            app_logger.error(f"Error finding user {user_id}: {e}")
            return None

    def user_exists(self, user_id):
        """Check if user exists on device"""
        try:
            return self.get_user_by_id(user_id) is not None
        except Exception as e:
            app_logger.error(f"Error checking user existence {user_id}: {e}")
            return False
    
    def connect(self):
        if self.zk.is_connect and self.zk.helper.test_ping():
            return

        retry_count = 0
        max_retries = 3
        
        while retry_count < max_retries:
            try:
                self.zk.connect()
                app_logger.info("Connected to ZK device successfully")
                return
            except Exception as e:
                retry_count += 1
                app_logger.warning(f"Failed to connect to ZK device. Attempt {retry_count}/{max_retries}. Error: {e}")
                if retry_count < max_retries:
                    time.sleep(min(6 * retry_count, 30))  # Exponential backoff with max 30s
                else:
                    app_logger.error(f"Failed to connect after {max_retries} attempts")
                    raise Exception(f"Could not connect to ZK device after {max_retries} attempts")

    def disconnect(self):
        try:
            if self.zk.is_connect:
                self.zk.disconnect()
                app_logger.info("Disconnected from ZK device")
        except Exception as e:
            app_logger.error(f"Error disconnecting from ZK device: {e}")

    def enable_device(self):
        try:
            self.zk.enable_device()
        except Exception as e:
            app_logger.error(f"Error enabling device: {e}")

    def disable_device(self):
        try:
            self.zk.disable_device()
        except Exception as e:
            app_logger.error(f"Error disabling device: {e}")

    def get_device_info(self):
        """Get device information"""
        try:
            self.connect()
            info = {
                'device_name': self.zk.get_device_name(),
                'firmware_version': self.zk.get_firmware_version(),
                'platform': self.zk.get_platform(),
                'device_time': self.zk.get_time(),
                'users_count': len(self.zk.get_users() or []),
                'templates_count': len(self.zk.get_templates() or [])
            }
            app_logger.info(f"Device info retrieved: {info}")
            return info
        except Exception as e:
            app_logger.error(f"Error getting device info: {e}")
            return None

    def get_attendance(self):
        try:
            self.connect()
            self.disable_device()
            records = self.zk.get_attendance()
            app_logger.info(f"Retrieved {len(records) if records else 0} attendance records")
            return records
        except Exception as e:
            app_logger.error(f"Error retrieving attendance records: {e}")
            raise
        finally:
            self.enable_device()
            


def get_zk_service():
    zk_service = ZkService(
        zk_class=ZK,
        ip=os.environ.get('DEVICE_IP'),
        port=int(os.environ.get('DEVICE_PORT', 4370)),
        verbose=bool(strtobool(os.getenv("FLASK_DEBUG", "false")))
    )
    return zk_service