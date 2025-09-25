# Trino with Iceberg

DataPipe Docker Compose setup with Trino, Iceberg, and MinIO for streaming data lakehouse operations.

## Quick Start

### 1. Setup Environment
```bash
make store
make setup-data
```
Starts storage services and loads sample data into MinIO.

### 2. Verify Storage
```bash
make s3 ls s3://
```
Lists S3 buckets to verify MinIO is running and data is loaded.

### 3. Check Catalog
```bash
make catalog-list
```
Lists all namespaces and tables in the Iceberg catalog.

### 4. Run Data Pipeline Tasks
```bash
make 1  # Prepare categories
make 2  # Prepare merchants
make 3  # Share raw transactions
make 4  # Perform a merge

# Continue with make 5, make 6, etc.

make 11 # Process Bicycle Hire data
make 12 # Process SpaceX Http data

```
Runs numbered data processing tasks in sequence. Each task processes and transforms data through the pipeline.

### 5. Cleanup
```bash
make clean-all
```
Stops all services and removes all persistent data (PostgreSQL, MinIO, Kafka, Solace).

## Available Services
- **Trino**: http://localhost:8080 (query engine)
- **MinIO**: http://localhost:9001 (S3-compatible storage, admin/admin)
- **Flink**: http://localhost:8081 (stream processing)
- **Kafka UI**: http://localhost:8080 (message streaming)

## Explore other commands
```bash
make help
```
