import os 
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq


load_dotenv()
my_api_key = os.getenv("GROQ_API_KEY")

if not my_api_key:
    raise ValueError('api key not found')

cleint = Groq(api_key=my_api_key)

model='openai/gpt-oss-20b'
role = 'user'
prompt='who am i'

message = {
    "role":role,
    "content":prompt
    
}

messages = [message]

resp = cleint.chat.completions.create(model=model,messages=messages)
print(resp)