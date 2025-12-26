import os
import json
import time

class MetadataCache:
    # Entries older than this will be cleaned up
    CACHE_TTL_DAYS = 30
    
    def __init__(self, cache_file):
        self.cache_file = cache_file
        self.cache = {}
        self.load()
        
    def load(self):
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r') as f:
                    self.cache = json.load(f)
                self._cleanup_old_entries()
            except (json.JSONDecodeError, OSError, IOError):
                self.cache = {}
                
    def save(self):
        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
        except (OSError, IOError):
            pass
    
    def _cleanup_old_entries(self):
        """Remove cache entries older than CACHE_TTL_DAYS."""
        if not self.cache:
            return
            
        cutoff = time.time() - (self.CACHE_TTL_DAYS * 86400)
        keys_to_remove = []
        
        for key, value in self.cache.items():
            # Key format: "path_size_mtime" - extract mtime
            try:
                parts = key.rsplit('_', 2)
                if len(parts) >= 3:
                    mtime = float(parts[-1])
                    if mtime < cutoff:
                        keys_to_remove.append(key)
            except (ValueError, TypeError):
                pass
        
        for key in keys_to_remove:
            del self.cache[key]
        
        if keys_to_remove:
            self.save()
            
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

