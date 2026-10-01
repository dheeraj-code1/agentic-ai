import os 

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue, MatchAny, PayloadSchemaType

from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from groq import Groq

load_dotenv()

QDRANT_URL = os.getenv("QDRANT_API_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

COLLECTION_NAME = "test_collection"
EMBEDDING_SIZE = 384


if client.collection_exists(COLLECTION_NAME):
    client.delete_collection(COLLECTION_NAME)
    print(f"collection {COLLECTION_NAME} deleted")



client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(
        size=EMBEDDING_SIZE,
        distance=Distance.COSINE,
    )
)

client.create_payload_index(
    collection_name=COLLECTION_NAME,
    field_name="category",
    field_schema=PayloadSchemaType.KEYWORD
)


documents = [
    {"text":"employee have 24 leaves per year", "category":"leave"},
    {"text":"employee can take 10 paid leaves in a year", "category":"leave"},
    {"text":"employee can take 10 unpaid leaves in a year", "category":"leave"},
    {"text":"employee can take 10 sick leaves in a year", "category":"leave"},
    {"text":"employee can take 10 casual leaves in a year", "category":"leave"},
    {"text":"employee can take 10 earned leaves in a year", "category":"leave"},
    {"text":"employee have gym allowance of 1000 per month", "category":"allowance"},
    {"text":"employee have medical allowance of 1000 per month", "category":"allowance"},
    {"text":"employee have travel allowance of 1000 per month", "category":"allowance"},
    {"text":"employee have food allowance of 1000 per month", "category":"allowance"},
    {"text":"employee have other allowance of 1000 per month", "category":"allowance"},
]


embedder = SentenceTransformer("all-MiniLM-L6-v2")

embeddings = [embedder.encode(doc["text"]) for doc in documents]


points = [ ]
for i, doc in enumerate(documents):
    point = PointStruct(
        id=i+1,
        vector=embeddings[i],
        payload=doc,
    )

    points.append(point)

client.upsert(points=points, collection_name=COLLECTION_NAME)

def search_with_filter(query:str, filter:Filter,top_k=3):
    query_embedding = embedder.encode(query)

    results = client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=top_k,
        with_payload=True,
        query_filter=filter,
    ).points

    return results

def search_without_filter(query:str, top_k=3):
    query_embedding = embedder.encode(query)

    results = client.search(
        collection_name=COLLECTION_NAME,
        query=query_embedding,
        limit=top_k,
    ).points



allowance_filter = Filter(
    must=[
        FieldCondition(
            key="category",
            match=MatchValue(value="allowance"),
        )
    ]
)

def ask_llm(question:str, context:str,client:Groq,model:str="openai/gpt-oss-20b"):
    system_prompt = f""" You are a helpful assistant that can answer questions about the following documents: {context} """

    system_message = {
        "role": "system",
        "content": system_prompt
    }

    user_message = {
        "role": "user",
        "content": question
    }

    messages = [system_message, user_message]

    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )

    return response.choices[0].message.content


groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

question = "how many types of allowance employee have?"
context = search_with_filter(question, allowance_filter)

context = "\n".join([doc.payload["text"] for doc in context])

print("--------------------------------")
print("Context:")
print(context)
print("--------------------------------")

response = ask_llm(question, context, groq_client)
print("--------------------------------")
print("Response:")
print(response)
print("--------------------------------")