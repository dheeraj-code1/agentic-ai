import os 
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
from pydantic import BaseModel


from read_file import read_resume
from jobD import jobD_parser
from resume_parser import resume_parser

load_dotenv()


groq_api_key = os.getenv("GROQ_API_KEY")

if not groq_api_key:
    raise ValueError("api key not found")


client = Groq(api_key=groq_api_key)
model_name  = "openai/gpt-oss-20b"



resume_path = "/home/lp-399/Downloads/resume/pdfs/dheeraj_baghel_resume_12Sep.pdf"

job_description = """
Job Summary:
We are looking for a skilled Python Developer with strong experience in data handling, analysis,
and backend development. The ideal candidate should have hands-on experience in working
with large datasets, building data pipelines, and writing efficient, scalable Python code.

Key Responsibilities:
● Develop, test, and maintain scalable Python applications.
● Work with large datasets to extract, transform, and analyze data.
● Build and optimize data pipelines and workflows.
● Perform data cleaning, validation, and preprocessing.
● Collaborate with cross-functional teams including data analysts and engineers.
● Write reusable, efficient, and well-documented code.
● Integrate APIs and third-party services.
● Troubleshoot and debug data-related issues.

Required Skills:
● Strong proficiency in Python.
● Experience with data libraries like Pandas, NumPy.
● Hands-on experience with SQL and relational databases.
● Knowledge of data visualization tools (Matplotlib, Seaborn, or similar).
● Experience in building data pipelines or ETL processes.
● Familiarity with REST APIs and backend frameworks (Flask/Django is a plus).
● Understanding of data structures and algorithms.

Good to Have:
● Experience with big data tools (Spark, Hadoop).
● Knowledge of cloud platforms (AWS, Azure, or GCP).
● Exposure to machine learning libraries (Scikit-learn, TensorFlow, etc.).
● Experience with version control tools like Git.
"""


resume_text = read_resume(resume_path)
print(resume_text)

exit()

raw_job_description = jobD_parser(client,model_name,job_description)
raw_resume_text = resume_parser(client,model_name,resume_text)


import json 

class MatchScore(BaseModel):
    score:float
    details:dict

match_score_schema = MatchScore.model_json_schema()

prompt = f"""
You are an HR recruiter. 

Compare the candidate's resume with the job description. Here is the Job Description: {json.loads(raw_job_description)} and here is the Candidate's Resume: {json.loads(raw_resume_text)}. 

Compare both and give us a score. Return the Valid json output matching the {match_score_schema} schema. Provide the candidate's name, matching skills, missing important skills, whether experience requirements are met or not, overall match percentage from 0 to 100, and a short final verdict explaining why this candidate is being given this score.

"""

messages = [{
    "role":"user",
    "content":prompt
}]

response_format = {
    "type":"json_object"
}

response = client.chat.completions.create(model=model_name,messages=messages,response_format=response_format)
print(response.choices[0].message.content)