# wsgi.py
from dotenv import load_dotenv
from zkteco import create_app

load_dotenv()
app = create_app()
