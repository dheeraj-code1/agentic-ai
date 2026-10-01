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

# structure it 
from pydantic import BaseModel

class Ticket(BaseModel):
    name:str
    phn:str
    mail:str
    issue:str

schema = Ticket.model_json_schema()

response_format = {
    "type":"json_object"
}


prompt_system = f"""
Give me output strictly into this format.
{schema}
finally give me output in json format
"""
message_system = {
    "role":"system",
    "content":prompt_system
}

text = "This is dheeraj, my mail is dhee@gmail and phnone num 0303030 and i have issue asddddddddadadasda with my phn not working"
prompt= f"""
This is customer ticket, please extract personal information this.
{text} 
"""

message = {
    "role":role,
    "content":prompt
    
}

messages = [message_system,message]

resp = cleint.chat.completions.create(model=model,messages=messages,response_format=response_format)
print(resp.choices[0].message.content)