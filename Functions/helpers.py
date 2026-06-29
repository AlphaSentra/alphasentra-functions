"""
Helper functions
"""

import os
from urllib.parse import quote_plus
from logging_utils import log_error, log_info

try:
    from pymongo import MongoClient
    PYMONGO_AVAILABLE = True
except ImportError:
    PYMONGO_AVAILABLE = False
    MongoClient = None

class DatabaseManager:
    """
    Singleton class for MongoDB connection pooling and management.
    """
    _instance = None
    _client = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._client = None
        return cls._instance
    
    def get_client(self):
        """
        Get MongoDB client with connection pooling.
        Creates client if it doesn't exist.
        """
        if self._client is None:
            try:
                if not PYMONGO_AVAILABLE:
                    raise ImportError("pymongo not available")
                
                # Get MongoDB connection details from environment variables
                use_mongodb_srv = os.getenv("USE_MONGODB_SRV", "false").lower() == "true"
                mongodb_database = os.getenv("MONGODB_DATABASE", "alphasentra-core")
                mongodb_username = os.getenv("MONGODB_USERNAME")
                mongodb_password = os.getenv("MONGODB_PASSWORD")
                mongodb_auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin")
                
                # Construct MongoDB URI based on USE_MONGODB_SRV
                if use_mongodb_srv:
                    mongodb_srv = os.getenv("MONGODB_SRV")
                    if not mongodb_srv:
                        raise ValueError("MONGODB_SRV environment variable is required when USE_MONGODB_SRV is true")
                    mongodb_uri = f"{mongodb_srv}"
                else:
                    mongodb_host = os.getenv("MONGODB_HOST", "localhost")
                    mongodb_port = int(os.getenv("MONGODB_PORT", "27017"))
                    if mongodb_username and mongodb_password:
                        mongodb_uri = f"mongodb://{quote_plus(mongodb_username)}:{quote_plus(mongodb_password)}@{mongodb_host}:{mongodb_port}/{mongodb_database}?authSource={mongodb_auth_source}"
                    else:
                        mongodb_uri = f"mongodb://{mongodb_host}:{mongodb_port}/{mongodb_database}"
                
                # Create client with connection pooling
                self._client = MongoClient(
                    mongodb_uri,
                    maxPoolSize=10,
                    minPoolSize=2,
                    connectTimeoutMS=30000,
                    serverSelectionTimeoutMS=30000
                )
                
                # Test connection (silent - no logging)
                self._client.admin.command('ping')
                
            except Exception as e:
                log_error("Failed to create MongoDB client", "MONGODB_CONNECTION", e)
                self._client = None
                raise
        
        return self._client
    
    def close_connection(self):
        """Close MongoDB connection"""
        if self._client:
            self._client.close()
            self._client = None
            log_info("MongoDB connection closed")

