import os 
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
import numpy as np
from sentence_transformers import SentenceTransformer

load_dotenv()
my_api_key = os.getenv("GROQ_API_KEY")

if not my_api_key:
    raise ValueError('api key not found')

client = Groq(api_key=my_api_key)

model='openai/gpt-oss-20b'



embedder = SentenceTransformer("all-MiniLM-L6-v2") #384

documents = [
    "employee have 24 leaves per year"
    "employee can take 10 paid leaves in a year"
    "employee can take 10 unpaid leaves in a year"
    "employee can take 10 sick leaves in a year"
    "employee can take 10 casual leaves in a year"
    "employee can take 10 earned leaves in a year"
    "employee can take 10 earned leaves in a year"
    "employee have gym allowance of 1000 per month"
    "employee have medical allowance of 1000 per month"
    "employee have travel allowance of 1000 per month"
    "employee have food allowance of 1000 per month"
    "employee have other allowance of 1000 per month"
    "employee have other allowance of 1000 per month"
]

def consine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def ask_llm(question:str, context:str):
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
        temperature=0.0
    )

    return response.choices[0].message.content


embeddings_documents = embedder.encode(documents)

query = "how time employee  have for long vacation?"

query_embedding = embedder.encode(query)

def retrieve(query_embedding):
    scores = [[consine_similarity(query_embedding, embedding), i] for i, embedding in enumerate(embeddings_documents)]

    scores.sort(key=lambda x:x[0], reverse=True)

    idx = scores[0][1]
    print(f"Retrieved document: {documents[idx]}")
    return documents[idx]


context = retrieve(query_embedding)

answer = ask_llm(query, context)

print(answer)