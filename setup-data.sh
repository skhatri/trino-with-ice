#!/bin/bash

set -e

BLUE='\033[34m'
GREEN='\033[32m'
YELLOW='\033[33m'
NC='\033[0m'

echo -e "${BLUE}Setting up data for MinIO S3...${NC}"

UTC_DATE=$(date -u +%Y-%m-%d)
echo -e "${YELLOW}Using UTC date: ${UTC_DATE}${NC}"

mkdir -p dataset/london_bicycles/cycle-hire
mkdir -p dataset/london_bicycles/cycle-stations

echo -e "${BLUE}Downloading London bicycles cycle-hire data...${NC}"
if [[ ! -f dataset/london_bicycles/cycle-hire/000000000001.parquet ]]; then
  curl -L -o dataset/london_bicycles/cycle-hire/000000000001.parquet https://github.com/skhatri/app-data/raw/main/london_bicycles/cycle-hire/000000000001.parquet
fi;
if [[ ! -f dataset/london_bicycles/cycle-hire/000000000002.parquet ]]; then
  curl -L -o dataset/london_bicycles/cycle-hire/000000000002.parquet https://github.com/skhatri/app-data/raw/main/london_bicycles/cycle-hire/000000000002.parquet
fi;

echo -e "${BLUE}Downloading London bicycles cycle-stations data...${NC}"
if [[ ! -f dataset/london_bicycles/cycle-stations/000000000000.parquet ]]; then
  curl -L -o dataset/london_bicycles/cycle-stations/000000000000.parquet https://github.com/skhatri/app-data/raw/main/london_bicycles/cycle-stations/000000000000.parquet
fi;

echo -e "${BLUE}Waiting for MinIO to be ready...${NC}"
until curl -f http://localhost:9000/minio/health/live >/dev/null 2>&1; do
    echo -e "${YELLOW}Waiting for MinIO...${NC}"
    sleep 2
done

echo -e "${GREEN}MinIO is ready!${NC}"

export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export AWS_DEFAULT_REGION=us-east-1

echo -e "${BLUE}Uploading transactions.csv to S3...${NC}"
aws --endpoint-url http://localhost:9000 s3 cp dataset/transactions.csv s3://finance/ext-transactions/csv/date=${UTC_DATE}/

echo -e "${BLUE}Uploading London bicycles data to S3...${NC}"
aws --endpoint-url http://localhost:9000 s3 cp dataset/london_bicycles/ s3://finance/london_bicycles/ --recursive

echo -e "${BLUE}Verifying uploads...${NC}"
echo -e "${YELLOW}Finance bucket contents:${NC}"
aws --endpoint-url http://localhost:9000 s3 ls s3://finance/ --recursive

echo -e "${GREEN}Data setup completed successfully!${NC}"
