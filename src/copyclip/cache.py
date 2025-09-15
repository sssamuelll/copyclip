import hashlib
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any

class SemanticCache:
    def __init__(self, cache_dir: str = ".copyclip_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.memory_cache = {}  # Cache en memoria para la sesión actual
        
    def _generate_key(self, content: str, operation: str, 
                      provider: str, model: str) -> str:
        """Genera una clave única para el contenido."""
        # Incluir metadatos en la clave para evitar colisiones
        key_content = f"{operation}:{provider}:{model}:{content}"
        return hashlib.sha256(key_content.encode()).hexdigest()
    
    def get(self, content: str, operation: str, 
            provider: str, model: str) -> Optional[str]:
        """Busca en el cache."""
        key = self._generate_key(content, operation, provider, model)
        
        # Primero buscar en memoria
        if key in self.memory_cache:
            print(f"[CACHE] Memory hit for {operation}", file=sys.stderr)
            return self.memory_cache[key]
        
        # Luego buscar en disco
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)
                    print(f"[CACHE] Disk hit for {operation}", file=sys.stderr)
                    self.memory_cache[key] = data['result']
                    return data['result']
            except Exception:
                pass
        
        return None
    
    def set(self, content: str, result: str, operation: str,
            provider: str, model: str):
        """Guarda en el cache."""
        key = self._generate_key(content, operation, provider, model)
        
        # Guardar en memoria
        self.memory_cache[key] = result
        
        # Guardar en disco
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump({
                    'operation': operation,
                    'provider': provider,
                    'model': model,
                    'content_hash': hashlib.sha256(content.encode()).hexdigest(),
                    'result': result,
                    'timestamp': time.time()
                }, f)
        except Exception as e:
            print(f"[CACHE] Failed to save: {e}", file=sys.stderr)

# Instancia global
semantic_cache = SemanticCache()