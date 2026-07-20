# ============================================================
# 🎬 MoUsE AI - الخادم الرئيسي (app.py)
# ============================================================

import os
import base64
import uuid
import httpx
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
import asyncio

# ==================== الإعدادات ====================
AGNES_API_KEY = "sk-0wjJtBOBSLAvGBky3GGotI93cUoksPUZoZnmMc2yVkUSFfON"
AGNES_BASE_URL = "https://apihub.agnes-ai.com/v1"
MAX_TIMEOUT = 300
OUTPUT_DIR = "/tmp"

# ==================== تطبيق FastAPI ====================
app = FastAPI(
    title="🎬 MoUsE AI API",
    description="توليد فيديوهات احترافية بالذكاء الاصطناعي",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==================== دوال مساعدة ====================
def encode_image_to_base64(image_bytes: bytes) -> str:
    return base64.b64encode(image_bytes).decode('utf-8')

async def generate_video_agnes(prompt: str, image_base64: str = None):
    """توليد فيديو باستخدام Agnes AI"""
    
    create_url = f"{AGNES_BASE_URL}/videos"
    headers = {
        "Authorization": f"Bearer {AGNES_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "agnes-video-v2.0-image-to-video" if image_base64 else "agnes-video-v2.0",
        "prompt": prompt,
        "width": 1152,
        "height": 768,
        "num_frames": 121,
        "frame_rate": 24
    }
    
    # رفع الصورة إذا وجدت
    if image_base64:
        upload_url = f"{AGNES_BASE_URL}/upload"
        upload_headers = {"Authorization": f"Bearer {AGNES_API_KEY}"}
        image_bytes = base64.b64decode(image_base64)
        files = {'file': ('image.jpg', image_bytes, 'image/jpeg')}
        
        async with httpx.AsyncClient(timeout=60) as client:
            upload_response = await client.post(upload_url, files=files, headers=upload_headers)
        
        if upload_response.status_code != 200:
            raise Exception(f"فشل رفع الصورة: {upload_response.text}")
        
        upload_result = upload_response.json()
        image_url = upload_result.get("url")
        if image_url:
            payload["image_url"] = image_url
        else:
            raise Exception("لم يتم استلام رابط الصورة")
    
    # إنشاء مهمة الفيديو
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(create_url, json=payload, headers=headers)
    
    if response.status_code != 200:
        raise Exception(f"فشل إنشاء الفيديو: {response.text}")
    
    result = response.json()
    video_id = result.get("video_id") or result.get("id")
    if not video_id:
        raise Exception("لم يتم استلام معرف الفيديو")
    
    # الاستعلام عن النتيجة
    status_url = f"{AGNES_BASE_URL}/agnesapi?video_id={video_id}"
    status_headers = {"Authorization": f"Bearer {AGNES_API_KEY}"}
    
    for attempt in range(30):  # 30 * 10 = 5 دقائق
        await asyncio.sleep(10)
        async with httpx.AsyncClient(timeout=30) as client:
            status_response = await client.get(status_url, headers=status_headers)
        
        if status_response.status_code != 200:
            continue
        
        status_data = status_response.json()
        video_url = status_data.get("video_url") or status_data.get("url")
        
        if video_url:
            async with httpx.AsyncClient(timeout=60) as client:
                video_response = await client.get(video_url)
            if video_response.status_code == 200:
                return video_response
    
    raise Exception("انتهى وقت الانتظار لتوليد الفيديو (5 دقائق)")

# ==================== نقاط النهاية ====================
@app.get("/")
async def root():
    return {
        "status": "active",
        "name": "🎬 MoUsE AI",
        "version": "2.0.0",
        "model": "agnes-video-v2.0",
        "docs": "/docs",
        "api_key_configured": bool(AGNES_API_KEY)
    }

@app.get("/status")
async def status():
    return {
        "api_key_configured": bool(AGNES_API_KEY),
        "api_key_preview": AGNES_API_KEY[:10] + "..." if AGNES_API_KEY else "None",
        "model": "agnes-video-v2.0",
        "max_timeout": MAX_TIMEOUT,
        "ready": bool(AGNES_API_KEY)
    }

@app.post("/generate")
async def generate(
    prompt: str = Form(..., description="وصف الفيديو"),
    image: UploadFile = File(None, description="صورة مرجعية اختيارية")
):
    if not prompt or len(prompt) < 5:
        raise HTTPException(status_code=400, detail="النص يجب أن يكون 5 أحرف على الأقل")
    
    if not AGNES_API_KEY:
        raise HTTPException(status_code=500, detail="مفتاح Agnes AI غير مفعل")
    
    image_base64 = None
    if image:
        try:
            contents = await image.read()
            if len(contents) > 10 * 1024 * 1024:
                raise HTTPException(status_code=400, detail="الصورة كبيرة جداً (الحد الأقصى 10 ميجابايت)")
            image_base64 = encode_image_to_base64(contents)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"خطأ في معالجة الصورة: {str(e)}")
    
    try:
        response = await generate_video_agnes(prompt, image_base64)
        
        if response.status_code != 200:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"خطأ في خدمة Agnes AI: {response.text[:200]}"
            )
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"video_{timestamp}_{uuid.uuid4().hex[:6]}.mp4"
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        with open(filepath, "wb") as f:
            f.write(response.content)
        
        return FileResponse(
            filepath,
            media_type="video/mp4",
            filename=filename,
            headers={
                "X-Video-Generated": "true",
                "X-Video-Duration": "5 seconds (approx)",
                "X-Model": "agnes-video-v2.0"
            }
        )
        
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="انتهى الوقت. قد يكون النموذج يستغرق وقتاً أطول من المتوقع."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"خطأ غير متوقع: {str(e)}")
