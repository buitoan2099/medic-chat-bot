
from qdrant_client import QdrantClient
from config import QDRANT_DIR, COLLECTION_NAME

client = QdrantClient(path=str(QDRANT_DIR))

try:
    info = client.get_collection(COLLECTION_NAME)

    print("=" * 40)
    print("KIỂM TRA EMBEDDING")
    print("=" * 40)

    print("Collection:", COLLECTION_NAME)
    print("Status:", info.status)
    print("Total points:", info.points_count)
    print("Vector size:", info.config.params.vectors.size)

    result = client.count(
        collection_name=COLLECTION_NAME,
        exact=True
    )

    print("Exact count:", result.count)

finally:
    client.close()
