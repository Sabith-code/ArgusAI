import os
import logging
from typing import Optional, Tuple
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.collection import Collection

load_dotenv()

logger = logging.getLogger(__name__)

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "brand_reputation")
MONGODB_COLLECTION = os.getenv("MONGODB_COLLECTION", "mentions")

_client: Optional[MongoClient] = None

def get_db_client() -> MongoClient:
    """Return a singleton MongoClient instance connected to MONGODB_URI."""
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=5000)
    return _client

def get_db(db_name: Optional[str] = None) -> Database:
    """Return the specified or default MongoDB Database instance."""
    client = get_db_client()
    target_db = db_name or MONGODB_DATABASE
    return client[target_db]

def get_mentions_collection(collection_name: Optional[str] = None, db_name: Optional[str] = None) -> Collection:
    """Return the specified or default mentions Collection instance."""
    db = get_db(db_name)
    target_coll = collection_name or MONGODB_COLLECTION
    return db[target_coll]

def check_connection() -> Tuple[bool, str, dict]:
    """
    Ping MongoDB server and return connection status, server info / version, or error message.
    """
    try:
        client = get_db_client()
        # Ping the server
        server_info = client.server_info()
        version = server_info.get("version", "unknown")
        return True, version, server_info
    except Exception as e:
        return False, str(e), {}
