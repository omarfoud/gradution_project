# Job Search API - Deployment Guide

## Overview
This is a FastAPI-based job search and recommendation system that uses FAISS for vector similarity search and SQLite for data storage.

## 📋 Prerequisites

### System Requirements
- **Python**: 3.9+
- **RAM**: Minimum 8GB (16GB recommended for large datasets)
- **Storage**: 10GB+ free space (for FAISS index and database)
- **GPU**: Optional (CUDA supported for faster embeddings)

### Required Files
- `job_descriptions.csv` - Job dataset
- `jobs.db` - SQLite database (created by ingest.py)
- `jobs.index` - FAISS vector index (created by ingest.py)

## 🚀 Quick Deployment

### Option 1: Docker (Recommended)

1. **Clone and Setup**
```bash
git clone <repository-url>
cd job-search-api
```

2. **Environment Configuration**
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. **Run with Docker Compose**
```bash
docker-compose up -d
```

4. **Access the Application**
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Frontend: http://localhost (via nginx)

### Option 2: Manual Deployment

1. **Install Dependencies**
```bash
pip install -r requirements.txt
```

2. **Setup Environment**
```bash
cp .env.example .env
# Edit .env with your settings
```

3. **Run Data Ingestion (First Time Only)**
```bash
python ingest.py
```

4. **Start the API Server**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## 🗄️ Database Setup

### Initial Data Ingestion
The system requires job data to be processed before use:

```bash
python ingest.py
```

This will:
- Load job descriptions from CSV
- Generate text embeddings using Sentence Transformers
- Create FAISS vector index for similarity search
- Populate SQLite database with structured job data

### Database Schema
```sql
CREATE TABLE jobs (
    faiss_id INTEGER PRIMARY KEY,
    job_id TEXT,
    title TEXT,
    company TEXT,
    description TEXT,
    skills TEXT,
    location TEXT,
    work_type TEXT,
    experience TEXT
);
```

## ⚙️ Configuration

### Environment Variables (.env)
```bash
# API Configuration
GEMINI_API_KEY=your_google_gemini_api_key_here
API_HOST=0.0.0.0
API_PORT=8000

# Database Configuration
DB_PATH=jobs.db
CSV_PATH=job_descriptions.csv
INDEX_PATH=jobs.index

# Model Configuration
MODEL_NAME=all-MiniLM-L6-v2
DEVICE=cpu  # Change to 'cuda' if GPU available

# Processing Configuration
CHUNK_SIZE=10000
MAX_CV_LENGTH=4000

# CORS Configuration
ALLOWED_ORIGINS=*
```

## 🔧 API Endpoints

### Core Endpoints
1. **POST /upload-cv** - Upload and store CV
2. **POST /recommend-matches** - Get job recommendations based on CV
3. **POST /analyze-job-id** - Analyze specific job against CV
4. **POST /search** - Search jobs with filters
5. **POST /chat** - Career advice chat

### API Documentation
Visit `http://localhost:8000/docs` for interactive API documentation.

## 🐳 Docker Configuration

### Dockerfile Features
- Multi-stage build for optimization
- Non-root user for security
- Health checks for monitoring
- Volume mounts for persistent data

### Docker Compose Services
- **job-search-api**: Main FastAPI application
- **nginx**: Reverse proxy and static file serving

## 🔒 Security Considerations

### API Keys
- Store Gemini API key in environment variables
- Never commit API keys to version control
- Use key management services in production

### CORS
- Configure allowed origins in production
- Remove wildcard (`*`) in production environments

### File Uploads
- CV files are processed in memory only
- No persistent storage of uploaded files
- File size limits enforced

## 📊 Monitoring & Logging

### Health Checks
```bash
curl http://localhost:8000/health
```

### Application Logs
- Docker logs: `docker-compose logs -f job-search-api`
- Manual deployment: Check console output

## 🚀 Production Deployment

### Scaling Considerations
1. **Horizontal Scaling**: Load balance multiple API instances
2. **Database**: Consider PostgreSQL for production
3. **Vector Storage**: Consider specialized vector databases
4. **Caching**: Redis for session management

### Performance Optimization
1. **GPU Acceleration**: Set `DEVICE=cuda` in production
2. **Batch Processing**: Optimize chunk sizes
3. **Memory Management**: Monitor FAISS index memory usage

## 🔍 Troubleshooting

### Common Issues

#### 1. Model Loading Errors
```bash
# Check model availability
python -c "from sentence_transformers import SentenceTransformer; print('OK')"
```

#### 2. Database Connection Issues
```bash
# Verify database file exists
ls -la jobs.db
```

#### 3. FAISS Index Issues
```bash
# Check index file
ls -la jobs.index
```

#### 4. Memory Issues
- Reduce `CHUNK_SIZE` in ingest.py
- Use smaller embedding model
- Increase system RAM

### Debug Mode
```bash
export DEBUG=true
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 📞 Support

### Backend Team Handoff
1. **Code Repository**: Provide Git access
2. **Documentation**: Share this DEPLOYMENT.md
3. **Environment Variables**: Provide .env template
4. **Data Files**: Share processed jobs.db and jobs.index
5. **API Documentation**: Direct to /docs endpoint

### Required Handoff Items
- ✅ Source code (main.py, ingest.py, etc.)
- ✅ requirements.txt
- ✅ Docker configuration
- ✅ Environment configuration
- ✅ Deployment documentation
- ✅ Processed data files (jobs.db, jobs.index)
- ✅ API testing interface (index.html)

## 🔄 Version Management

### Data Updates
To update job data:
1. Replace `job_descriptions.csv`
2. Run `python ingest.py` to reprocess
3. Restart the API service

### Code Updates
```bash
# Docker
docker-compose pull
docker-compose up -d

# Manual
git pull
pip install -r requirements.txt
# Restart service
```
