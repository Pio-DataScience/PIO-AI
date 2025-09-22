# 🏦 PIO-AI AML Database Engine - Complete Documentation

## 📋 Table of Contents

1. [System Overview](#-system-overview)
2. [Architecture & Components](#-architecture--components)
3. [Installation & Setup](#-installation--setup)
4. [Configuration](#-configuration)
5. [Script Execution Order](#-script-execution-order)
6. [Core Services](#-core-services)
7. [API Endpoints](#-api-endpoints)
8. [Advanced Features](#-advanced-features)
9. [Chat Interface](#-chat-interface)
10. [Example Interactions](#-example-interactions)
11. [Troubleshooting](#-troubleshooting)
12. [Performance Optimization](#-performance-optimization)
13. [Development Workflow](#-development-workflow)

---

## 🎯 System Overview

The **PIO-AI AML Database Engine** is a production-grade AI-powered Retrieval-Augmented Generation (RAG) system specifically designed for Anti-Money Laundering (AML) database analysis and compliance monitoring. It combines multiple advanced indexing strategies, semantic search, and large language models to provide intelligent insights into complex financial data structures.

### 🏗️ Core Philosophy

- **Multi-Modal Intelligence**: Combines symbolic analysis (AST), graph relationships, full-text search (BM25), and semantic embeddings (BGE/FAISS)
- **Production-Ready**: Built for enterprise-scale AML compliance with robust error handling and monitoring
- **Extensible Architecture**: Modular design allows easy integration of new data sources and AI models
- **Compliance-First**: Designed with financial regulations and data privacy in mind

### 🔧 Key Capabilities

1. **Intelligent Code Analysis**: Deep understanding of Python codebases through AST parsing
2. **Relationship Mapping**: Graph-based analysis of database schema relationships
3. **Semantic Search**: BGE-large-en-v1.5 embeddings for contextual understanding
4. **Hybrid Retrieval**: Combines multiple search strategies for optimal results
5. **Interactive Chat**: Natural language interface for database exploration
6. **API-First Design**: RESTful APIs for system integration
7. **Real-time Analytics**: Live insights into AML data patterns

---

## 🏛️ Architecture & Components

### 📁 Project Structure

```
PIO-AI/
├── 📄 README.md                    # Main documentation
├── 📄 SYSTEM_RECAP.md             # Development history
├── 📄 README_DEV.md               # Developer guide
├── 🔧 config/                     # Configuration files
│   ├── app.yaml                   # Application settings
│   ├── database.yaml              # Database configuration
│   ├── chunking.yaml              # Document chunking settings
│   └── .env                       # Environment variables
├── 📦 warehouse/                   # Data storage
│   ├── manifest.yaml              # Project definitions
│   ├── catalog.db                 # Database metadata
│   ├── vectors/                   # Vector embeddings
│   └── db/oracle/                 # Oracle schema exports
├── 🗂️ indexes/                    # Search indexes
│   ├── symbols/                   # AST symbol tables
│   ├── graph/                     # Relationship graphs
│   ├── bm25/                      # Full-text indexes
│   ├── faiss_code/               # Code embeddings
│   └── faiss_text/               # Text embeddings
├── 🛠️ services/                   # Core business logic
│   ├── ingest/                    # Data ingestion
│   ├── indexer/                   # Index builders
│   ├── retriever/                 # Search orchestration
│   ├── llm/                       # Language model integration
│   ├── api/                       # REST API server
│   ├── tools_api/                 # Utility functions
│   └── db/                        # Database abstractions
├── 📜 scripts/                    # Automation scripts
│   ├── setup.py                  # Environment setup
│   ├── chat.py                   # Interactive CLI
│   ├── 0X_*.py                   # Processing pipeline
│   └── 4X_*.py                   # Advanced features
└── 🧪 tests/                      # Test suites
```

---

## 💡 Example Chat Interactions

### 1. Database Schema Exploration
```
User: "Show me all tables related to customer risk assessment"