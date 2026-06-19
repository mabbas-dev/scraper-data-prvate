import asyncio
import aiohttp
from database import SessionLocal, AppConfig, UserAccount, Category, StreamQueue
from sqlalchemy.orm import Session
import json
import os
import random

async def fetch_api(session, host_url, username, password, action=None):
    params = {"username": username, "password": password}
    if action:
        params["action"] = action
    url = f"{host_url}/player_api.php"
    
    try:
        async with session.get(url, params=params, timeout=15) as resp:
            if resp.status == 200:
                text = await resp.text()
                if not text.strip():
                    return []
                return json.loads(text)
            elif resp.status == 419:
                return {"error": "blocked_419"}
            elif resp.status == 403:
                return {"error": "blocked_403"}
    except Exception as e:
        print(f"Error fetching API {action}: {e}")
    return []

async def verify_single_worker(session, host_url, user):
    """Check if a user account is valid by attempting to fetch the server info"""
    data = await fetch_api(session, host_url, user.username, user.password)
    
    if isinstance(data, dict):
        if 'error' in data:
            if data['error'] == 'blocked_419':
                return user.id, "Blocked by Firewall (419)"
            if data['error'] == 'blocked_403':
                return user.id, "Blocked by Cloudflare (403)"
                
        if 'user_info' in data:
            status = data['user_info'].get('status', 'Active')
            return user.id, f"Valid ({status})"
            
    return user.id, "Invalid / Expired"

async def verify_all_workers():
    db = SessionLocal()
    config = db.query(AppConfig).first()
    users = db.query(UserAccount).all()
    
    if not config or not users:
        db.close()
        return
        
    config.sync_status_msg = "Verifying workers..."
    db.commit()
    
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}) as session:
        results = []
        # Process strictly ONE BY ONE (Sequentially) to avoid DDoS detection
        for u in users:
            res = await verify_single_worker(session, config.host_url, u)
            results.append(res)
            # Add a long, human-like delay between each login attempt (2 to 4 seconds)
            await asyncio.sleep(random.uniform(2.0, 4.0))
            
        # Update db with results
        for user_id, status_msg in results:
            u = db.query(UserAccount).filter(UserAccount.id == user_id).first()
            if u:
                u.last_verified = status_msg
                if "Invalid" in status_msg:
                    u.is_active = False
                    
        # Reset the verifying status msg when done
        config.sync_status_msg = "Idle"
        db.commit()
        
    db.close()
    return results

async def populate_queue():
    db = SessionLocal()
    config = db.query(AppConfig).first()
    user = db.query(UserAccount).filter(UserAccount.is_active == True).first()
    
    if not config or not user:
        db.close()
        return False
        
    config.is_syncing = True
    config.sync_status_msg = "Fetching master lists..."
    db.commit()
    
    # Check if queue already has pending items (Resume functionality)
    pending_count = db.query(StreamQueue).filter(StreamQueue.status == 0).count()
    if pending_count > 0:
        config.sync_status_msg = f"Resuming {pending_count} items..."
        db.commit()
        db.close()
        return True
        
    # Otherwise, fetch lists
    async with aiohttp.ClientSession(headers={'User-Agent': 'Mozilla/5.0'}) as session:
        # Add random human-like delays between massive API pulls so we don't trigger the firewall
        live_cats = await fetch_api(session, config.host_url, user.username, user.password, "get_live_categories")
        await asyncio.sleep(random.uniform(1.0, 2.5))
        
        vod_cats = await fetch_api(session, config.host_url, user.username, user.password, "get_vod_categories")
        await asyncio.sleep(random.uniform(1.0, 2.5))
        
        series_cats = await fetch_api(session, config.host_url, user.username, user.password, "get_series_categories")
        await asyncio.sleep(random.uniform(1.0, 2.5))
        
        # Save categories
        db.query(Category).delete()
        for cat in (live_cats if isinstance(live_cats, list) else []):
            db.add(Category(id=str(cat.get('category_id')), name=cat.get('category_name'), type='live'))
        for cat in (vod_cats if isinstance(vod_cats, list) else []):
            db.add(Category(id=str(cat.get('category_id')), name=cat.get('category_name'), type='vod'))
        for cat in (series_cats if isinstance(series_cats, list) else []):
            db.add(Category(id=str(cat.get('category_id')), name=cat.get('category_name'), type='series'))
        db.commit()
        
        # Streams
        config.sync_status_msg = "Fetching stream lists..."
        db.commit()
        
        live_streams = await fetch_api(session, config.host_url, user.username, user.password, "get_live_streams")
        await asyncio.sleep(random.uniform(2.0, 4.0)) # Longer delay for massive lists
        
        vod_streams = await fetch_api(session, config.host_url, user.username, user.password, "get_vod_streams")
        # For series, it usually just provides base info.
        
        db.query(StreamQueue).delete()
        
        # Add Live
        for s in (live_streams if isinstance(live_streams, list) else []):
            db.add(StreamQueue(
                stream_id=str(s.get('stream_id')),
                stream_type='live',
                name=s.get('name', 'Unknown').strip(),
                category_id=str(s.get('category_id')),
                play_url="" # Removed hardcoded URL here, generated dynamically by worker
            ))
            
        # Add VOD
        for s in (vod_streams if isinstance(vod_streams, list) else []):
            ext = s.get('container_extension', 'mp4')
            db.add(StreamQueue(
                stream_id=str(s.get('stream_id')),
                stream_type='vod',
                name=s.get('name', 'Unknown').strip(),
                category_id=str(s.get('category_id')),
                extension=ext,
                play_url="" # Removed hardcoded URL here, generated dynamically by worker
            ))
            
        db.commit()
        config.sync_status_msg = "Starting async workers..."
        db.commit()
        db.close()
        return True

async def worker(worker_id, user_account):
    print(f"Worker {worker_id} started with account {user_account.username}")
    db = SessionLocal()
    config = db.query(AppConfig).first()
    host_url = config.host_url
    
    # VLC User-Agent to trigger actual redirect
    async with aiohttp.ClientSession(headers={'User-Agent': 'VLC/3.0.18'}) as session:
        while True:
            # Check if sync is cancelled
            config = db.query(AppConfig).first()
            if not config.is_syncing:
                break
                
            # Get a pending item
            item = db.query(StreamQueue).filter(StreamQueue.status == 0).first()
            if not item:
                break # Queue empty
                
            # Mark as processing (status=3 temporarily to avoid duplicate workers picking it)
            item.status = 3
            db.commit()
            
            # Construct user-specific URL
            if item.stream_type == 'live':
                test_url = f"{host_url}/{user_account.username}/{user_account.password}/{item.stream_id}"
            else:
                test_url = f"{host_url}/movie/{user_account.username}/{user_account.password}/{item.stream_id}.{item.extension}"
                
            # Resolve
            resolved_url = None
            try:
                # Use allow_redirects=True to find final URL
                async with session.head(test_url, allow_redirects=True, timeout=10) as resp:
                    resolved_url = str(resp.url)
            except Exception as e:
                # If head fails, try get but abort quickly
                try:
                    async with session.get(test_url, allow_redirects=True, timeout=10) as resp:
                        resolved_url = str(resp.url)
                except Exception as ex:
                    pass
                    
            if resolved_url:
                item.hidden_url = resolved_url
                item.status = 1 # Done
            else:
                item.status = 2 # Failed
                
            db.commit()
            
            # Very important: Add a human-like delay so we don't act like a DDoS bot
            # The server will allow requests if they look like a real player switching channels
            await asyncio.sleep(random.uniform(0.5, 1.5))
            
    db.close()
    print(f"Worker {worker_id} finished.")

async def run_sync():
    ready = await populate_queue()
    if not ready:
        return
        
    db = SessionLocal()
    users = db.query(UserAccount).filter(UserAccount.is_active == True).all()
    
    if not users:
        config = db.query(AppConfig).first()
        config.is_syncing = False
        config.sync_status_msg = "No active users found."
        db.commit()
        db.close()
        return
        
    # Start one worker per active user account
    workers = []
    for i, user in enumerate(users):
        workers.append(asyncio.create_task(worker(i, user)))
        
    # Wait for all workers to finish
    await asyncio.gather(*workers)
    
    # Update status
    config = db.query(AppConfig).first()
    config.is_syncing = False
    config.sync_status_msg = "Idle (Last sync completed)"
    db.commit()
    db.close()
    
    export_json()

def export_json():
    db = SessionLocal()
    os.makedirs("data", exist_ok=True)
    
    categories = {c.id: c.name for c in db.query(Category).all()}
    
    # Group by category name instead of a single giant list
    live_export = {}
    vod_export = {}
    
    streams = db.query(StreamQueue).filter(StreamQueue.status == 1).all()
    for s in streams:
        cat_name = categories.get(s.category_id, "Uncategorized")
        
        entry = {
            "id": s.stream_id,
            "name": s.name,
            "resolved_url": s.hidden_url
        }
        
        if s.stream_type == 'live':
            if cat_name not in live_export:
                live_export[cat_name] = []
            live_export[cat_name].append(entry)
        else:
            if cat_name not in vod_export:
                vod_export[cat_name] = []
            vod_export[cat_name].append(entry)
            
    with open("data/live.json", "w", encoding="utf-8") as f:
        json.dump(live_export, f, indent=4, ensure_ascii=False)
        
    with open("data/vod.json", "w", encoding="utf-8") as f:
        json.dump(vod_export, f, indent=4, ensure_ascii=False)
        
    db.close()

if __name__ == "__main__":
    asyncio.run(run_sync())
