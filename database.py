from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import datetime

DATABASE_URL = "sqlite:///./iptv.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

class AppConfig(Base):
    __tablename__ = "config"
    id = Column(Integer, primary_key=True, index=True)
    host_url = Column(String, default="http://fastshare1.com:8080")
    is_syncing = Column(Boolean, default=False)
    sync_status_msg = Column(String, default="Idle")

class UserAccount(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    is_active = Column(Boolean, default=True)
    in_use = Column(Boolean, default=False)  # Track if currently used by a worker
    last_verified = Column(String, default="Not Verified") # New column to track verification status

class Category(Base):
    __tablename__ = "categories"
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    type = Column(String) # 'live', 'vod', 'series'

class StreamQueue(Base):
    __tablename__ = "stream_queue"
    id = Column(Integer, primary_key=True, index=True)
    stream_id = Column(String, index=True)
    stream_type = Column(String) # 'live', 'vod', 'series'
    name = Column(String)
    category_id = Column(String)
    extension = Column(String, nullable=True)
    play_url = Column(String)
    hidden_url = Column(String, nullable=True)
    status = Column(Integer, default=0) # 0: Pending, 1: Done, 2: Failed

Base.metadata.create_all(bind=engine)

def init_db():
    db = SessionLocal()
    # Init config
    if not db.query(AppConfig).first():
        db.add(AppConfig(host_url="http://fastshare1.com:8080", is_syncing=False, sync_status_msg="Idle"))
    
    # Init users if empty
    if db.query(UserAccount).count() == 0:
        default_users = [
            ("Perryhouse01", "Perryhouse02"),
        ("Noor9226291", "sherry123"),
        ("King2018299", "sherry123"),
        ("Ankur283637", "sherry123"),
        ("Wajiha00111", "Wajiha0022"),
        ("Vamshi16266", "sherry123"),
        ("Jackson28367", "sherry123"),
        ("Gurram29100", "sherry123"),
        ("Wajiha001", "Wajiha002"),
        ("Ranisis8248277", "sherry12345"),
        ("Naeem0012", "elitesubscription12"),
        ("Masroor17336", "sherry123"),
        ("Ranishergill277", "sherry123"),
        ("Mazhar283627", "sherry123"),
        ("Usafrnd282626", "sherry123"),
        ("Imranahmed1967", "sherry123"),
        ("Ather200123", "sherry123"),
        ("Hussnainmir282627", "sherry123"),
        ("Noman282627", "sherry123"),
        ("Sohail2688", "sherry123"),
        ("Rani78997", "sherry123"),
        ("zSTzdYmaB9", "eager2passage"),
        ("Yaha282627", "sherry123"),
        ("Zubair28267", "sherry123")
    ]
        for u, p in default_users:
            db.add(UserAccount(username=u, password=p))
    
    db.commit()
    db.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized.")
