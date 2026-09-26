# AI Study Assistant

An AI-powered study assistant that combines **Retrieval-Augmented Generation (RAG)**, **Qdrant**, **n8n**, **MCP**, and an LLM to help students understand and manage their study materials.

The system can answer questions from uploaded study materials and perform automated actions such as saving summaries to Google Sheets, sending them by email, and generating PDF files.

---

## Overview

The AI Study Assistant follows this workflow:

User
↓
n8n AI Agent
↓
LLM
↓
Qdrant Vector Store
↓
Retrieve relevant study material
↓
Generate answer / summary
↓
MCP Tools
├── Google Sheets
├── Gmail
└── PDF

The main goal is to keep the study material as the source of knowledge while using MCP tools for external actions.

---

## Features

- Question answering from uploaded study materials
- Retrieval-Augmented Generation (RAG)
- Qdrant vector database for document retrieval
- AI Agent orchestration using n8n
- LLM integration through API
- MCP tool integration
- Save summaries to Google Sheets
- Send summaries by email
- Generate PDF summaries
- Conversation memory
- Multi-step tool calling

---

## Architecture

```text
                    ┌──────────────────┐
                    │      Student     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    n8n Chat      │
                    │      Trigger     │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │     AI Agent     │
                    └──────┬─────┬─────┘
                           │     │
              ┌────────────┘     └─────────────┐
              ▼                                ▼
      ┌────────────────┐               ┌──────────────┐
      │ Qdrant Vector  │               │ MCP Client   │
      │     Store      │               │    Tools     │
      └───────┬────────┘               └──────┬───────┘
              │                               │
              ▼                    ┌──────────┼──────────┐
      ┌────────────────┐           ▼          ▼          ▼
      │ Study Material │      Google Sheets  Gmail      PDF
      └────────────────┘


---

RAG Pipeline

The RAG pipeline is responsible for loading and retrieving information from study materials.

Google Drive
     ↓
Download Study Material
     ↓
Document Loader
     ↓
Embeddings
     ↓
Qdrant Vector Store
     ↓
Semantic Retrieval
     ↓
AI Agent

The retrieved documents are used as the knowledge source for answering study-related questions.


---

MCP Tools

The project uses MCP to allow the AI Agent to perform external actions.

1. Save Summary to Google Sheets

Stores the generated study summary in Google Sheets.

2. Send Summary by Email

Sends the generated summary to the configured email address.

3. Create Summary PDF

Creates a PDF containing the generated summary.

The same final summary can be passed to multiple MCP tools to keep the output consistent.


---

Technologies

Python

n8n

Qdrant

MCP

Large Language Models (LLMs)

Retrieval-Augmented Generation (RAG)

Google Drive

Google Sheets

Gmail

Ollama

Hugging Face Inference Providers



---

Project Structure

AI-Study-Assistant/
│
├── README.md
│
├── mcp-server/
│   ├── server.py
│   └── requirements.txt
│
├── n8n/
│   └── AI-Study-Assistant.json
│
└── rag/
    └── README.md


---

MCP Server

The MCP server provides the tools used by the AI Agent.

mcp-server/
├── server.py
└── requirements.txt

The server exposes MCP tools for:

Google Sheets

Email

PDF generation



---

n8n Workflow

The main automation workflow is located in:

n8n/AI-Study-Assistant.json

The workflow contains:

Chat Trigger

AI Agent

LLM

Simple Memory

Qdrant Vector Store

MCP Client



---

RAG

The RAG system stores embeddings of uploaded study materials in Qdrant.

The AI Agent retrieves relevant chunks from Qdrant before answering questions about the uploaded materials.

This helps reduce unsupported answers and keeps responses grounded in the provided study materials.


---

Example

A user can ask:

> From the uploaded paper, give me a short summary of the main idea, save it to Google Sheets, send it by email, and create a PDF.



The system performs:

User Request
     ↓
Qdrant Retrieval
     ↓
LLM generates final summary
     ↓
MCP
 ├── Save to Google Sheets
 ├── Send Email
 └── Create PDF


---

Setup

1. Clone the repository

git clone https://github.com/YOUR_USERNAME/AI-Study-Assistant.git
cd AI-Study-Assistant

2. Install MCP server dependencies

cd mcp-server
pip install -r requirements.txt

3. Configure credentials

Configure the required credentials for:

Google Drive

Google Sheets

Gmail

Qdrant

LLM provider


Do not commit API keys, OAuth tokens, or private credentials to the repository.

4. Import the n8n workflow

Import:

n8n/AI-Study-Assistant.json

into your n8n instance.

5. Configure the required credentials

Connect your own credentials inside n8n.


---

Security

Never upload sensitive credentials to GitHub.

The following files and information should remain private:

.env
token.json
API keys
Access tokens
OAuth credentials
Private keys
Google credentials

Use environment variables or n8n credentials instead.


---

Future Improvements

Support multiple study subjects

Add document management

Add citation generation

Add quiz generation

Add flashcard generation

Add study progress tracking

Add more MCP tools

Improve retrieval and reranking

Add a web-based student interface



---

Author

Mohamed Adel

High School Student - Gharbiya STEM School

Interested in:

Artificial Intelligence

Machine Learning

Deep Learning

Computer Vision

NLP

Generative AI

AI Research



---

License

This project is for educational and experimental purposes.

### الشكل النهائي على GitHub

```text
AI-Study-Assistant
│
├── README.md
│
├── mcp-server
│   ├── server.py
│   └── requirements.txt
│
├── n8n
│   └── AI-Study-Assistant.json
│
└── rag
    └── README.md
