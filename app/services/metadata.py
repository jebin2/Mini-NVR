import os
import json

class MetadataCache:
    def __init__(self, cache_file):
        self.cache_file = cache_file
        self.cache = {}
        self.load()
        
    def load(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    self.cache = json.load(f)
            except:
                self.cache = {}
                
    def save(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except:
            pass
            
    def get_duration(self, path, size, mtime):
        # Key: path + size + mtime (in case file is replaced)
        key = f"{path}_{size}_{mtime}"
        return self.cache.get(key)
        
    def set_duration(self, path, size, mtime, duration):
        key = f"{path}_{size}_{mtime}"
        self.cache[key] = duration
        # Save on every write is safe for low concurrency app, 
        # but could be optimized to save periodically if needed.
        self.save()
