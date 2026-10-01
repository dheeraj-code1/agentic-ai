from fastapi import FastAPI
from fastapi.responses import StreamingResponse

import os 
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel
import json


from read_file import read_resume
from jobD import jobD_parser
from resume_parser import resume_parser


load_dotenv()
my_api_key = os.getenv("GROQ_API_KEY")

if not my_api_key:
    raise ValueError('api key not found')

client = Groq(api_key=my_api_key)

model='openai/gpt-oss-20b'

resume_path = "/home/lp-399/Downloads/resume/pdfs/dheeraj_baghel_resume_12Sep.pdf"



file_path = "profile.json"
if not os.path.exists(file_path):
    with open(file_path, "w") as f:
        resume_text = read_resume(resume_path)
        raw_resume_text = resume_parser(client,model,resume_text)
        raw_resume_text = json.loads(raw_resume_text)
        json.dump(raw_resume_text, f)
   

# resume_text = read_resume(resume_path)
# raw_resume_text = resume_parser(client,model,resume_text)

personal_informations = f"""
Name: Dheeraj Baghel
Email: dheeraj.baghel@gmail.com
Phone: 9876543210


preferred location: Mumbai, Pune, Bangalore, Delhi, Gurgaon, Noida
Current Location: Noida
current salary: 10 LPA


Soft Skills:
Good communication skills
Good problem solving skills
Good team work skills
Good leadership skills
Good time management skills
Good decision making skills
Good decision making skills

"""



def ask_question(system_prompt:str,question:str):
    

    system_message = {
        "role":"system",
        "content": system_prompt
    }

    prompt = f"""
    Anwer the question:
    {question}
    """

    user_message = {
        "role":"user",
        "content": prompt
    }

    messages = [system_message,user_message]
    
    response = client.chat.completions.create(model=model,messages=messages,stream=True)

    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


class ChatRequest(BaseModel):
    question:str

app = FastAPI()


@app.get("/")
def home():
    return {"message": "HireMeAI"}


@app.post("/chat")
def chat(request:ChatRequest):
    with open(file_path, "r") as f:
        raw_resume_text = json.load(f)

    system_prompt = f"""
    You are an helpfull assistant
    Only answer if question is relevant to the resume or personal informations, hiring or any other information related to the resume.
    You are given a question and a resume and personal informations. You need to answer the question based on the resume.
    You also give answer of hr questions like why should we hire you based on the resume and personal informations.

    Here is the resume: {raw_resume_text}
    Here is the personal informations: {personal_informations}

 
    ## Constraints:
    Dont invent information. Dont mention anything that you have not provided.
    Give only information that is relevant to the question.
    


    ## Output format:
    all information should be in point-wise format.
    keep important and related information in the beginning.
    dont show that information in cronological order.
    do not use extra characters like * etc.

    ## Fallback:
    1. Question is not relevant to the resume or personal informations, hiring or any other information related to the resume, say "I am not sure about information related to this question, I am here to help you with information related to the resume and personal informations."
    2. If you are not sure about the answer, say "I am not sure about information related to this question, please conect with him on the email or phone number. Also provide the email and phone number in the answer."

    """
    return StreamingResponse(ask_question(system_prompt,request.question),media_type="text/event-stream")


@app.post("/chat_naukari")
def chat_naukari(request:ChatRequest):

    with open(file_path, "r") as f:
        raw_resume_text = json.load(f)
    system_prompt = f""" 
    You are expert in naukari.com and you are helpfull in filling naukari.com job application form.

    Only answer if question is relevant to the job application form.
    You are given a question and a job application form. You need to answer the question based on resume and personal informations.
    

    Here is the resume: {raw_resume_text}
    Here is the personal informations: {personal_informations}

    ## Constraints:
    Dont invent information. Dont mention anything that you have not provided.
    Give only information that is relevant to the question.


    ## Output format:
    Give answer in two/three words or short sentences.
    do not use extra characters like * etc.

    ## Fallback:
    1. Question is not relevant to the mentioned skills in resume or personal informations, try to give answer if thinks are related to his profile, means if skills is not in resume and asked in question try to give minimum information related to his profile."
    2. If you are not sure about the answer, say "Positively like he have less than one year experience"
    """

    return StreamingResponse(ask_question(system_prompt,request.question),media_type="text/event-stream")