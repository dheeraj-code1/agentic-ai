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


def get_answer(issue):

    prompt = f"""
    #role: you are senior customer assistant.

    #task: You need to classify the user issue only in techincal, return, billing.

    customer issue: {issue}

    #constranint:
    Only classify into these three category

    #output format:
    return single value category name

    #example:
    my phone is not working -> techincal

    #fallback
    if issue can not be classified any of above category, then return other
    """


    msg = { 
        "role":"user",
        "content":prompt
    }

    messages = [msg]

    response = cleint.chat.completions.create(model=model,messages=messages)

    print(response.choices[0].message.content)



issue = "my laptop is not working, i got stucked i want to return it"


get_answer(issue)