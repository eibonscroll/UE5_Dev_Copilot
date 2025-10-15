from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from .settings import SETTINGS

class VectorDB:
    def __init__(self):
        self.client = QdrantClient(url=SETTINGS.qdrant_url)
        self.collection = SETTINGS.collection

    def ensure_collection(self, dim: int):
        if self.collection not in [c.name for c in self.client.get_collections().collections]:
            self.client.recreate_collection(
                collection_name=self.collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE)
            )

    def upsert(self, payloads, vectors):
        points = [{"id": i, "vector": vectors[i], "payload": payloads[i]} for i in range(len(payloads))]
        self.client.upsert(collection_name=self.collection, points=points)

    def search(self, query_vec, k=8, filter=None):
        return self.client.search(collection_name=self.collection, query_vector=query_vec, limit=k, query_filter=filter)
