import os 
# structure it 
from pydantic import BaseModel

class JobD(BaseModel):
    role:str
    required_skills:list[str]
    preffered_skills:list[str]
    minimum_experience:str
    eduction_requirment: str
    responsibility: list[str]

schema = JobD.model_json_schema()


def jobD_parser(cleint,model,text):
    response_format = {
        "type":"json_object"
    }


    prompt_system = f"""
    You are an expert HR assistant. 

    Your job is to analyze the job description and extract structured information. Return only valid JSON matching this schema {schema}.

    Do not return the schema itself and do not return unnecessary fields like property, title, type. 
    Fill the schema with actual information extracted. 
    If minimum experience is not mentioned, make it null. 
    Do not invent information.
    """
    message_system = {
        "role":"system",
        "content":prompt_system
    }

    
    prompt= f"""
    Analyze the following job description:
    {text} 
    """

    message = {
        "role":"user",
        "content":prompt
        
    }

    messages = [message_system,message]


    response_format = {
        "type":"json_object"
    }
    resp = cleint.chat.completions.create(model=model,messages=messages,response_format=response_format)
    # print(resp.choices[0].message.content)

    return resp.choices[0].message.content