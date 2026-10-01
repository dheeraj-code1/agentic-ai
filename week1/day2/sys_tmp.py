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
prompt='tell clothes company name'


message_system = {
    "role":"system",
    "content":"you are brand manager, please sugges name for my  companny, in oneword,suggest only one name"
}
message = {
    "role":role,
    "content":prompt
    
}

messages = [message_system,message]

resp = cleint.chat.completions.create(model=model,messages=messages,temperature=2)
print(resp.choices[0].message.content)