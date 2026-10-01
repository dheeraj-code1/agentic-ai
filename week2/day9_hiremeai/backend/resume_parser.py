import os 
from pydantic import BaseModel


class Experience(BaseModel):
    company:str | None=None
    role:str  | None=None
    duration:str | None=None
    description:str | None=None
    skiils_used:list[str]=[]

class Resume(BaseModel):
    name:str | None=None
    email: str | None=None
    phone: str | None=None
    total_exp_year:str | None=None

    skills: list[str] = []
    experience: list[Experience] = []
    projects: list[str] = []
    certification: list[str] = []




def resume_parser(client,model_name,text):
    resume_schema = Resume.model_json_schema()
    system_prompt = f"""
    You are an expert resume parser. 

    1. Extract information. Different resumes use different headings (for example: experience, professional experience, work history, employment, internship all mean experience, so understand them accordingly. 

    2. Skills can be in a skills section, work experience, or internship section). 
    3. If total experience is not there, then calculate it from the experience section, if including internship or training experience then keep it to the total experience. 
    
    Return only valid JSON matching this schema {resume_schema}. Important rule: Do not invent information. 
    If any information is not there, return an empty.
    """

    system_message = {
        "role":"system",
        "content": system_prompt
    }


    prompt = f"""
    Parse the following resume:{text}
    """

    user_message = {
        "role":"user",
        "content": prompt
    }
 

    messages = [system_message,user_message]

    response_format = {
        "type":"json_object"
    }
    resp = client.chat.completions.create(model=model_name,messages=messages,response_format=response_format)
    # print(resp.choices[0].message.content)

    return resp.choices[0].message.content

