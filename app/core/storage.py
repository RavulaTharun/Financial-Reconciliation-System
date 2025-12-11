import os
import json
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    import chromadb
    from chromadb.config import Settings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

class VectorStore:
    def __init__(self, collection_name: str = "reconciliation"):
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        if CHROMA_AVAILABLE:
            self._init_chroma()
    
    def _init_chroma(self):
        persist_dir = "chroma_db"
        os.makedirs(persist_dir, exist_ok=True)
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )
    
    def add_documents(self, documents: List[str], metadatas: List[Dict], ids: List[str]):
        if self.collection is None:
            return
        self.collection.add(
            documents=documents,
            metadatas=metadatas,
            ids=ids
        )
    
    def query(self, query_text: str, n_results: int = 5) -> Dict[str, Any]:
        if self.collection is None:
            return {"documents": [], "metadatas": [], "distances": []}
        results = self.collection.query(
            query_texts=[query_text],
            n_results=n_results
        )
        return results
    
    def clear(self):
        if self.client is not None:
            try:
                self.client.delete_collection(self.collection_name)
                self.collection = self.client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"}
                )
            except Exception:
                pass

class RunStorage:
    def __init__(self):
        self.runs: Dict[str, Dict[str, Any]] = {}
    
    def create_run(self, run_id: str) -> Dict[str, Any]:
        run_data = {
            "run_id": run_id,
            "status": "initialized",
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "progress": 0,
            "current_step": "",
            "steps_completed": [],
            "counts": {},
            "errors": [],
            "output_files": []
        }
        self.runs[run_id] = run_data
        return run_data
    
    def update_run(self, run_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        if run_id not in self.runs:
            return None
        self.runs[run_id].update(kwargs)
        self.runs[run_id]["updated_at"] = datetime.now().isoformat()
        return self.runs[run_id]
    
    def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        return self.runs.get(run_id)
    
    def get_all_runs(self) -> List[Dict[str, Any]]:
        return list(self.runs.values())

run_storage = RunStorage()
