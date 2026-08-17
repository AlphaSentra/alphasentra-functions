import os
from typing import Optional
from urllib.parse import quote_plus
from pymongo import MongoClient
from pymongo.errors import PyMongoError

import Functions.logging_utils as _logging_utils

try:
    from pymongo import MongoClient as _MongoClient
    _PYMONGO_AVAILABLE = True
except ImportError:
    _PYMONGO_AVAILABLE = False
    _MongoClient = None


class DatabaseManager:
    _instance = None
    _client = None
    _logs_client = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._client = None
            cls._logs_client = None
        return cls._instance

    def get_client(self):
        if self._client is None:
            try:
                if not _PYMONGO_AVAILABLE:
                    raise ImportError("pymongo not available")

                use_mongodb_srv = os.getenv("USE_MONGODB_SRV", "false").lower() == "true"
                mongodb_database = os.getenv("MONGODB_DATABASE", "alphasentra-core")
                mongodb_username = os.getenv("MONGODB_USERNAME")
                mongodb_password = os.getenv("MONGODB_PASSWORD")
                mongodb_auth_source = os.getenv("MONGODB_AUTH_SOURCE", "admin")

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

                self._client = _MongoClient(
                    mongodb_uri,
                    maxPoolSize=10,
                    minPoolSize=2,
                    connectTimeoutMS=30000,
                    serverSelectionTimeoutMS=30000,
                )
                self._client.admin.command("ping")
            except Exception as e:
                _logging_utils.log_error("Failed to create MongoDB client", "MONGODB_CONNECTION", e)
                self._client = None
                raise

        return self._client

    def get_logs_client(self):
        if self._logs_client is None:
            try:
                if not _PYMONGO_AVAILABLE:
                    raise ImportError("pymongo not available")

                logs_uri = os.getenv("MONGODB_URI_LOGS")
                logs_database = os.getenv("MONGODB_DATABASE_LOGS", "alphasentra-logs")
                if not logs_uri:
                    raise ValueError("MONGODB_URI_LOGS environment variable is required")

                self._logs_client = _MongoClient(
                    logs_uri,
                    maxPoolSize=10,
                    minPoolSize=2,
                    connectTimeoutMS=30000,
                    serverSelectionTimeoutMS=30000,
                )
                self._logs_client.admin.command("ping")
                self._logs_db_name = logs_database
            except Exception as e:
                _logging_utils.log_error("Failed to create MongoDB logs client", "MONGODB_CONNECTION", e)
                self._logs_client = None
                self._logs_db_name = None
                raise

        return self._logs_client, self._logs_db_name

    def close_connection(self):
        if self._client:
            self._client.close()
            self._client = None
            _logging_utils.log_info("MongoDB connection closed")
        if self._logs_client:
            self._logs_client.close()
            self._logs_client = None
            _logging_utils.log_info("MongoDB logs connection closed")


def get_client():
    return DatabaseManager().get_client()


def get_logs_client():
    return DatabaseManager().get_logs_client()


def close_connection():
    DatabaseManager().close_connection()
