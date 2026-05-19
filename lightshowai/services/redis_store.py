import os
import redis

# decode_responses=False: Flask-Session stores pickled bytes and needs raw
# bytes back. Any future code that stores strings in Redis should decode
# explicitly on read: redis_client.get("some:key").decode("utf-8")
redis_client = redis.Redis(
    host=os.environ.get("REDIS_HOST", "127.0.0.1"),
    port=int(os.environ.get("REDIS_PORT", 6379)),
    username=os.environ.get("REDIS_USER") or None,
    password=os.environ.get("REDIS_PASSWORD") or None,
    decode_responses=False
)
