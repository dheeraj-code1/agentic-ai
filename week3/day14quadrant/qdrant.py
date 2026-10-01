import os 

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from groq import Groq

load_dotenv()

QDRANT_URL = os.getenv("QUARTERANT_API_URL")
QDRANT_API_KEY = os.getenv("QUARTERANT_API_KEY")

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

COLLECTION_NAME = "test_collection"
EMBEDDING_SIZE = 384



client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(
        size=EMBEDDING_SIZE,
        distance=Distance.COSINE,
    )
)