import os 
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
from time import sleep

load_dotenv()
my_api_key = os.getenv("GROQ_API_KEY")

if not my_api_key:
    raise ValueError('api key not found')

client = Groq(api_key=my_api_key)

model='openai/gpt-oss-20b'



JOB_DESCRIPTION = """
Job description

Position: GCP Data Engineer

Experience: 2 to 5 years

Location: Hyderabad

Employment Type: Full-Time


Roles & Responsibilities


Design and develop scalable data warehouse solutions using BigQuery.
Build and optimize ETL/ELT pipelines using Dataflow, Dataproc, and Cloud Composer.
Develop complex SQL queries, views, stored procedures, and data transformations.
Integrate data from various on-premises and cloud data sources.
Implement batch and streaming data ingestion using Pub/Sub and Dataflow.
Optimize BigQuery performance, partitioning, clustering, and query costs.
Design dimensional data models, star schemas, and fact/dimension tables.
Ensure data quality, governance, security, and compliance standards.
Implement Infrastructure as Code (IaC) using Terraform.
Monitor and troubleshoot production data pipelines.
Work closely with Data Analysts, BI Developers, and Data Scientists.
Automate deployments and data workflows using CI/CD pipelines.
Support cloud migration and modernization initiatives.
"""

RESUME_TEXT = """
Dheeraj Baghel
Phone: 7037117999
Email: dheeraj25062003@gmail.com
LinkedIn: linkedin.com/in/dheeraj-baghel-51b568209
GitHub: github.com/dheeraj-code1
Location: Noida, India
Skills
Languages: Python, SQL, C/C++
Data Engineering: ETL/ELT, PySpark, Apache Spark, Apache Kafka, Data Ingestion, Data Modeling, Incremental Loading,
Schema Design, Data Validation, Parquet
Cloud: AWS (S3, Lambda, Glue, Athena, ECS, Kinesis), GCP (BigQuery, GCS, Cloud Run, Pub/Sub)
Databases: MySQL, ClickHouse, MongoDB, Redis
Frameworks and APIs: FastAPI, Flask, Pandas, Scrapy, BeautifulSoup, LangChain
Tools: Cursor, Docker, Git, Linux, Playwright, Frida, HTTP Toolkit
Education
DayalBagh Educational Institute, Agra
2021-2025
B.Tech in Electrical Engineering, Specialization: Computer Science
8.8 CGPA (Top 10%)
Experience
MfilterIt --- Ad-tech and E-commerce Data Intelligence
Feb 2025 -- Present
Software Development Engineer
- Built and maintained web and mobile scraping pipelines across 15+ e-commerce platforms using Python, Frida, Charles
Proxy, HTTP Toolkit, proxy rotation, and retry logic, reaching 99%+ scrape success.
- Built and maintained PySpark ETL pipelines on AWS (Lambda, S3, ECS) and GCP (BigQuery, GCS) that process 20M+
records daily, reducing pipeline runtime by 35%.
- Built REST APIs in FastAPI and Flask that serve processed data to 5+ downstream teams at sub-200ms average response
latency.
Six Dee Netad Solutions Pvt Ltd
April 2024 -- August 2024
R&D Trainee
- Built an automation tool that detects and blocks fraudulent IP traffic in Bing Ads campaigns, reducing manual monitoring by
70% and improving invalid traffic (IVT) prevention accuracy.
Projects
Centralized Data Acquisition Platform
Python, FastAPI/Flask, MySQL, GCP Cloud Run, AWS Lambda
- Built an event-driven acquisition platform that extracts product data from 15+ e-commerce platforms using cron event
generation, batching services, Cloud Run Jobs, and AWS Lambda collectors, processing 20M+ URLs/day at 99% job success
rate.
- Built Cloud Run job-trigger polling and FastAPI APIs for async worker status and file upload, loaded completed outputs
into MySQL through a file-ingestion service, and added proxy rotation and session/cookie management for multi-platform
collection.
Batch Data Processing Pipeline
Python, FastAPI/Flask, MySQL, GCP Cloud Run
- Built a cron-triggered batch pipeline that transforms raw collected data into analytics-ready records (20M+/day) using a
status-polling scheduler and parallel Cloud Run Jobs for cleaning, derived-metric computation, and MySQL load, with REST
APIs serving results to an internal dashboard.
AI Video Intelligence Pipeline
May 2026
Python, LangChain, LangGraph, Groq, ChromaDB, faster-whisper
GitHub: github.com/dheeraj-code1/video-rag-assistant
- Built an agentic video RAG pipeline using LangChain, LangGraph, Groq, ChromaDB, and faster-whisper with map-reduce
summarization and hybrid retrieval, producing summaries, action items, and insights from YouTube and local media.

"""


def ask_llm(system_prompt, user_prompt):
    system_message = {
        "role":"system",
        "content":system_prompt
    }

    user_message = {
        "role":"user",
        "content":user_prompt
    }

    messages = [system_message, user_message]
    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content


def step1_extract_skills_from_jd():
    system_prompt="""
    You are senior Hr assistant. You are given a job description and you need to extract the skills from the job description.
    """

    
    user_prompt = f"""
    Please extract the skills from the job description:
    {JOB_DESCRIPTION}
    """

    return ask_llm(system_prompt, user_prompt)

def step2_extract_skills_from_resume():
    system_prompt="""
    You are senior Hr assistant. You are given a resume and you need to extract the skills from the resume.
    """

    user_prompt = f"""
    Please extract the skills from the resume:
    {RESUME_TEXT}
    """

    return ask_llm(system_prompt, user_prompt)

def step3_match_skills(candidate,jd):
    system_prompt="""
    You are senior Hr assistant. You are given a job description and a resume and you need to match the skills from the job description and the resume.
    Generate a match score between 1 and 100 based on the skills from the job description and the resume. Output should be match score and small candidate verdict.
    """



    user_prompt = f"""
    Please generate  a match score for the job description and the resume:
    {candidate}
    {jd}
    """

    return ask_llm(system_prompt, user_prompt)



def main():
    jd = step1_extract_skills_from_jd()
    sleep(2)
    resume = step2_extract_skills_from_resume()
    sleep(2)
    match_score = step3_match_skills(resume,jd)
    print(match_score)

if __name__ == "__main__":
    main()