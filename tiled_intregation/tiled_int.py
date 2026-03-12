from tiled.client import from_uri

client = from_uri("http://127.0.0.1:8000")
print(list(client))

