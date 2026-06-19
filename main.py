from fastapi import FastAPI, BackgroundTasks, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
import asyncio
import os

from database import SessionLocal, AppConfig, UserAccount, StreamQueue, Category
import scraper

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Reset status on startup
    db = SessionLocal()
    config = db.query(AppConfig).first()
    if config:
        config.is_syncing = False
        config.sync_status_msg = "Idle"
        db.commit()
    db.close()
    yield

app = FastAPI(title="IPTV Multi-Account Scraper", lifespan=lifespan)

# Create data dir if not exists
os.makedirs("data", exist_ok=True)
app.mount("/data", StaticFiles(directory="data"), name="data")

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Models ---
class ConfigUpdate(BaseModel):
    host_url: str

class UserCreate(BaseModel):
    username: str
    password: str

# --- Endpoints ---
@app.get("/")
def read_root():
    return FileResponse("static/index.html")

@app.get("/api/status")
def get_status(db: Session = Depends(get_db)):
    config = db.query(AppConfig).first()
    
    total = db.query(StreamQueue).count()
    done = db.query(StreamQueue).filter(StreamQueue.status == 1).count()
    failed = db.query(StreamQueue).filter(StreamQueue.status == 2).count()
    pending = db.query(StreamQueue).filter(StreamQueue.status.in_([0, 3])).count()
    
    return {
        "host_url": config.host_url if config else "",
        "is_syncing": config.is_syncing if config else False,
        "sync_status_msg": config.sync_status_msg if config else "Not initialized",
        "stats": {
            "total": total,
            "done": done,
            "failed": failed,
            "pending": pending
        }
    }

@app.post("/api/config")
def update_config(data: ConfigUpdate, db: Session = Depends(get_db)):
    config = db.query(AppConfig).first()
    config.host_url = data.host_url
    db.commit()
    return {"status": "success"}

@app.get("/api/users")
def get_users(db: Session = Depends(get_db)):
    users = db.query(UserAccount).all()
    return [{"id": u.id, "username": u.username, "password": u.password, "is_active": u.is_active, "last_verified": u.last_verified} for u in users]

@app.post("/api/users/verify")
def verify_users(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    config = db.query(AppConfig).first()
    if config.is_syncing:
        return JSONResponse(status_code=400, content={"error": "Cannot verify while syncing"})
        
    config.sync_status_msg = "Verifying..."
    db.commit()
    
    def run_verify_task():
        asyncio.run(scraper.verify_all_workers())
        
    background_tasks.add_task(run_verify_task)
    return {"status": "started"}

@app.post("/api/users")
def add_user(user: UserCreate, db: Session = Depends(get_db)):
    db.add(UserAccount(username=user.username, password=user.password))
    db.commit()
    return {"status": "success"}

@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    db.query(UserAccount).filter(UserAccount.id == user_id).delete()
    db.commit()
    return {"status": "success"}

@app.post("/api/users/{user_id}/toggle")
def toggle_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(UserAccount).filter(UserAccount.id == user_id).first()
    user.is_active = not user.is_active
    db.commit()
    return {"status": "success"}

@app.post("/api/sync/start")
def start_sync(background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    config = db.query(AppConfig).first()
    if config.is_syncing:
        return JSONResponse(status_code=400, content={"error": "Sync already in progress"})
        
    config.is_syncing = True
    config.sync_status_msg = "Starting..."
    db.commit()
    
    # Run sync in background
    def run_sync_task():
        asyncio.run(scraper.run_sync())
        
    background_tasks.add_task(run_sync_task)
    return {"status": "started"}

@app.post("/api/sync/stop")
def stop_sync(db: Session = Depends(get_db)):
    config = db.query(AppConfig).first()
    config.is_syncing = False
    config.sync_status_msg = "Paused by user"
    db.commit()
    return {"status": "stopped"}

@app.post("/api/sync/reset")
def reset_sync(db: Session = Depends(get_db)):
    config = db.query(AppConfig).first()
    if config.is_syncing:
        return JSONResponse(status_code=400, content={"error": "Cannot reset while syncing"})
        
    # We only delete the StreamQueue. Users, Config, and Categories remain untouched.
    db.query(StreamQueue).delete()
    db.commit()
    return {"status": "reset"}

@app.get("/api/exports")
def get_exports():
    files = []
    if os.path.exists("data/live.json"):
        files.append({"name": "Live Streams", "url": "/data/live.json", "size": os.path.getsize("data/live.json")})
    if os.path.exists("data/vod.json"):
        files.append({"name": "VOD Streams", "url": "/data/vod.json", "size": os.path.getsize("data/vod.json")})
    return files
