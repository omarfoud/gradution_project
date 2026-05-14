# Database Setup Guide

## 📊 Database Architecture

### Hybrid Storage System
This project uses a **hybrid database approach**:
- **SQLite**: Structured job metadata and relationships
- **FAISS**: High-performance vector similarity search
- **CSV**: Raw data source for ingestion

## 🗄️ SQLite Database Schema

### Jobs Table Structure
```sql
CREATE TABLE jobs (
    faiss_id INTEGER PRIMARY KEY,      -- FAISS vector index reference
    job_id TEXT,                       -- Unique job identifier
    title TEXT,                        -- Job title
    company TEXT,                      -- Company name
    description TEXT,                  -- Full job description
    skills TEXT,                        -- Required skills
    location TEXT,                      -- Job location
    work_type TEXT,                     -- Remote/On-site/Hybrid
    experience TEXT                     -- Experience level
);
```

### Indexes for Performance
```sql
-- Recommended indexes for production
CREATE INDEX idx_job_id ON jobs(job_id);
CREATE INDEX idx_location ON jobs(location);
CREATE INDEX idx_company ON jobs(company);
CREATE INDEX idx_title ON jobs(title);
```

## 🔧 Database Setup Process

### Step 1: Prepare Data Source
Ensure `job_descriptions.csv` contains the following columns:
- Job Id
- Job Title
- Company
- Job Description
- skills
- location
- Work Type
- Experience

### Step 2: Run Ingestion Process
```bash
python ingest.py
```

**What the ingestion does:**
1. **Loads CSV data** in chunks (10,000 rows per batch)
2. **Creates text embeddings** using Sentence Transformers
3. **Builds FAISS index** for vector similarity search
4. **Populates SQLite** with structured job data
5. **Maps FAISS IDs** to SQLite records

### Step 3: Verify Database Creation
```bash
# Check SQLite database
sqlite3 jobs.db ".tables"
sqlite3 jobs.db "SELECT COUNT(*) FROM jobs;"

# Check FAISS index
python -c "import faiss; index = faiss.read_index('jobs.index'); print(f'Index contains {index.ntotal} vectors')"
```

## 📈 Database Performance

### Current Configuration
- **Records**: ~1.6M job descriptions
- **Embedding Dimension**: 384 (all-MiniLM-L6-v2)
- **FAISS Index Type**: IVFFlat with 1000 clusters
- **Chunk Processing**: 10,000 records per batch

### Performance Metrics
- **Vector Search**: <50ms for typical queries
- **SQL Queries**: <10ms for indexed lookups
- **Memory Usage**: ~2.5GB for FAISS index
- **Storage**: ~2.5GB index + ~700MB database

## 🔍 Database Operations

### Connection Management
```python
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Enable dict-like access
    return conn
```

### Hybrid Search Pattern
```python
def search_hybrid(query_text, k=10, location_filter=None):
    # 1. Vector search using FAISS
    vector = MODEL.encode([query_text])
    distances, indices = INDEX.search(vector, 500)
    
    # 2. Fetch matching records from SQLite
    results = []
    for idx in indices[0]:
        row = conn.execute("SELECT * FROM jobs WHERE faiss_id = ?", (int(idx),)).fetchone()
        if row and passes_filters(row):
            results.append(dict(row))
    
    return results
```

## 🚀 Production Database Setup

### Option 1: SQLite (Current)
**Pros:**
- Simple setup
- No external dependencies
- Good for read-heavy workloads

**Cons:**
- Limited concurrency
- Single machine only
- No built-in replication

### Option 2: PostgreSQL + pgvector (Upgrade Path)
```sql
-- PostgreSQL schema with vector support
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE jobs (
    id SERIAL PRIMARY KEY,
    job_id TEXT UNIQUE,
    title TEXT,
    company TEXT,
    description TEXT,
    skills TEXT,
    location TEXT,
    work_type TEXT,
    experience TEXT,
    embedding vector(384)  -- pgvector for embeddings
);

-- Vector similarity index
CREATE INDEX jobs_embedding_idx ON jobs USING ivfflat (embedding vector_cosine_ops);
```

### Option 3: External Vector Database
**Options:**
- Pinecone
- Weaviate
- Qdrant
- Milvus

**Migration Considerations:**
- API compatibility
- Embedding format
- Search performance
- Cost implications

## 📊 Database Monitoring

### Performance Queries
```sql
-- Check database size
SELECT 
    name,
    COUNT(*) as record_count,
    ROUND(SUM(LENGTH(description)) / 1024.0 / 1024.0, 2) as size_mb
FROM jobs 
GROUP BY name;

-- Search performance by location
SELECT location, COUNT(*) as job_count
FROM jobs 
GROUP BY location 
ORDER BY job_count DESC 
LIMIT 10;
```

### FAISS Index Monitoring
```python
import faiss
import psutil

# Index statistics
index = faiss.read_index('jobs.index')
print(f"Total vectors: {index.ntotal}")
print(f"Index type: {type(index).__name__}")
print(f"Dimension: {index.d}")

# Memory usage
process = psutil.Process()
print(f"Memory usage: {process.memory_info().rss / 1024 / 1024:.1f} MB")
```

## 🔄 Database Maintenance

### Data Updates
```bash
# 1. Update CSV file
# 2. Re-run ingestion
python ingest.py

# 3. Restart API service
docker-compose restart job-search-api
```

### Backup Procedures
```bash
# SQLite backup
cp jobs.db jobs_backup_$(date +%Y%m%d).db

# FAISS index backup
cp jobs.index jobs.index.backup

# Full backup
tar -czf database_backup_$(date +%Y%m%d).tar.gz jobs.db jobs.index job_descriptions.csv
```

### Database Optimization
```sql
-- SQLite optimization
PRAGMA optimize;
VACUUM;
ANALYZE;
```

## 🔧 Database Configuration

### Environment Variables
```bash
# Database paths
DB_PATH=jobs.db
INDEX_PATH=jobs.index
CSV_PATH=job_descriptions.csv

# Processing settings
CHUNK_SIZE=10000
BATCH_SIZE=64
MAX_CV_LENGTH=4000
```

### Advanced Configuration
```python
# FAISS index parameters
NLIST = 1000  # Number of clusters
NPROBE = 20   # Search clusters to check
METRIC = faiss.METRIC_INNER_PRODUCT
```

## 🚨 Troubleshooting

### Common Database Issues

#### 1. Database Lock Error
```bash
# Check for locked processes
lsof jobs.db

# Fix: Restart application
docker-compose restart
```

#### 2. FAISS Index Corruption
```bash
# Verify index integrity
python -c "import faiss; faiss.read_index('jobs.index')"

# Rebuild if corrupted
python ingest.py
```

#### 3. Memory Issues
```python
# Reduce chunk size in ingest.py
CHUNK_SIZE = 5000  # Reduce from 10000

# Use smaller embedding model
MODEL_NAME = "all-MiniLM-L6-v2"  # 384 dimensions
```

#### 4. Slow Search Performance
```python
# Optimize FAISS search parameters
INDEX.nprobe = 10  # Increase for better recall

# Add database indexes
sqlite3 jobs.db "CREATE INDEX idx_location ON jobs(location);"
```

## 📋 Database Handoff Checklist

### For Backend Team:

#### ✅ Required Files
- `jobs.db` - SQLite database with job records
- `jobs.index` - FAISS vector index for similarity search
- `job_descriptions.csv` - Source data file
- `ingest.py` - Data ingestion script

#### ✅ Configuration
- Database connection strings
- FAISS index parameters
- Chunk processing settings
- Memory optimization settings

#### ✅ Access Credentials
- Database file permissions
- API keys for external services
- Environment variable templates

#### ✅ Documentation
- Database schema documentation
- Ingestion process instructions
- Performance optimization guide
- Backup and recovery procedures

#### ✅ Monitoring Setup
- Database performance metrics
- Index health checks
- Memory usage monitoring
- Query performance tracking

## 🔄 Future Database Enhancements

### Planned Improvements
1. **PostgreSQL Migration**: For better concurrency
2. **Read Replicas**: For improved query performance
3. **Partitioning**: For large dataset management
4. **Caching Layer**: Redis for frequent queries
5. **Real-time Updates**: Streaming data ingestion

### Scaling Strategy
1. **Vertical Scaling**: More RAM, faster storage
2. **Horizontal Scaling**: Multiple API instances
3. **Database Sharding**: Geographic distribution
4. **Microservices**: Separate search and metadata services
