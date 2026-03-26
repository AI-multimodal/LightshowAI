from tiled.client import from_uri

client = from_uri("http://127.0.0.1:8000")
print(list(client))
print(client.items()[0])


for file_name in client:
	entry = client[file_name]
	print(f"\n--- {file_name} ---")
	print("Type:", type(entry))
	print("Metadata:", entry.metadata)
    
    # Read the data as a DataFrame
	df = entry.read()
	print(df.head())


subs = []




