import sys
import os
from pathlib import Path

# أضف المسار الرئيسي إلى sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# استورد تطبيق FastAPI من app.py
from app import app

# هذا السطر مهم لـ Vercel
handler = app
