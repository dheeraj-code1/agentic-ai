import os
import json
from ytscraper import chunks_path, get_ytube_playlist_chunks

from dotenv import load_dotenv
from groq import Groq

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

from sentence_transformers import SentenceTransformer


load_dotenv()

QDRANT_URL = os.getenv("QDRANT_API_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

COLLECTION_NAME = "ytube_playlist_chunks"
EMBEDDING_SIZE = 384

if not client.collection_exists(COLLECTION_NAME):
    client.create_collection(
        collection_name=COLLECTION_NAME,
        vectors_config=VectorParams(
            size=EMBEDDING_SIZE,
            distance=Distance.COSINE,
        ),
    )

embedder = SentenceTransformer("all-MiniLM-L6-v2")
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
model = "openai/gpt-oss-20b"


def embed_documents(documents: list[dict]) -> list[dict]:
    embeddings = embedder.encode(documents, show_progress_bar=True)
    return embeddings


def create_qdrant_points(documents: list[dict]):

    to_be_embedded_documents = [doc["text"] for doc in documents]
    embeddings = embed_documents(to_be_embedded_documents)

    points = []
    for i, doc in enumerate(documents):
        embedding = embeddings[i]
        points.append(PointStruct(id=i+1, vector=embedding, payload={"text": doc["text"], "url": doc["url"]}))

    return points

def upsert_qdrant_points(path):
    with open(path, "r", encoding="utf-8") as f:
        documents = [json.loads(line) for line in f if line.strip()]
    if not documents:
        print("No chunks to upsert")
        return
    points = create_qdrant_points(documents)
    client.upsert(collection_name=COLLECTION_NAME, points=points)

def search_qdrant(query:str, top_k=3):
    query_embedding = embedder.encode(query)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=top_k,
    ).points
    return results

def ask_llm(query:str, top_k=3):
    results = search_qdrant(query, top_k)
    lines = []
    for result in results:
        text = result.payload["text"]
        url = result.payload.get("url", "")
        if isinstance(text, dict):
            url = text.get("url", url)
            text = text.get("text", "")
        lines.append(f"{text} (ref: {url})")
    context = "\n".join(lines)
    print("-------------------------------------------------")
    print(context)
    print("-------------------------------------------------")
    system_prompt = f"""
    You are a helpful assistant that can answer questions based on the given context.

    #Task
    Based on the context, you need to answer the question, also need to provide url of relevant video from the context.

    #Context
    {context}

    #Output Format
    - Answer: <answer> (small summary of the answer)~
    - URL: <url> (give it as for reference to the video)

    #Constraints
     - Only answer based on context provided.
     - Do not hallucinate.
     - Do not provide any other information than the answer.
     
    #Fallback
    If you are not able to answer the question based on the context, you need to say "This topic is not covered in the provided video playlist" and provide url of relevant video from the context.
    """

    system_message = {
        "role":"system",
        "content":system_prompt,
    }
    user_message = {
        "role":"user",
        "content":f"Answer the Question: {query}",
    }
    messages = [system_message, user_message]
    response = groq_client.chat.completions.create(
        model=model,
        messages=messages,
    )

    return response.choices[0].message.content

if __name__ == "__main__":
    playlist = "https://www.youtube.com/playlist?list=PLbJhGqY-mq47k_WLUtzVjmarUm1EuXPj2"
    output = chunks_path(playlist)
    # get_ytube_playlist_chunks(playlist, langs=["en", "hi"])
    upsert_qdrant_points(output)
    answer = ask_llm("what is prefix sum algorithm?")
    print("-------------------------------------------------")
    print("Answer:")
    print(answer)
    print("-------------------------------------------------")