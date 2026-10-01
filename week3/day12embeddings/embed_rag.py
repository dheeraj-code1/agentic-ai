import os 
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
import numpy as np
from sentence_transformers import SentenceTransformer


model = SentenceTransformer("all-MiniLM-L6-v2") #384

text = "Apple is fruit"

# res = model.encode(text)

# print(res.shape)

def consine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


t1 = "Apple is fruit"
t2 = "This is a test"

v1 = model.encode(t1)
v2 = model.encode(t2)

print(consine_similarity(v1, v2))