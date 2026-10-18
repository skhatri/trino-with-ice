# Trino with Iceberg

DataPipe Docker Compose setup with Trino, Iceberg, and MinIO for streaming data lakehouse operations.

## Quick Start

### 1. Setup Environment
```bash
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
- **Trino**: http://localhost:7080 (query engine)
- **MinIO**: http://localhost:9001 (S3-compatible storage, admin/admin)
- **Flink**: http://localhost:8081 (stream processing)
- **Kafka UI**: http://localhost:7085 (message streaming)
- **Iceberg Catalog**: http://localhost:8181 (table catalog)

## Explore other commands
```bash
make help
```

## Repeatable Compose smoke check

Build the candidate Spark image from the DataPipe checkout first, then run:

```sh
make smoke-test
make smoke IMAGE=datapipe-spark:t1-candidate
# Explicit evidence directory and command timeout:
python3 smoke/compose_smoke.py --image datapipe-spark:t1-candidate \
  --output /tmp/datapipe-smoke-evidence --timeout 600
```

Requires Python 3.9+, GNU make, Docker Compose v2 and a responsive Docker daemon.
The candidate image must already exist locally; its image ID, dependency image IDs,
Git revision, commands and exit codes are retained in `report.json`. The output
folder must be new. Each command has a separate log, including failures/timeouts.
Evidence may contain demo credentials; keep the report directory local.

The selected existing target is `make 4` (`4-update-categories`), whose inline CSV
avoids external APIs and host seed data. Only PostgreSQL/seed, MinIO/init, Iceberg
REST and Trino are started before the one-shot DataPipe task. The finance schema
is created through Trino. Each of three cycles asserts exactly three persisted
`mcc/category` tuples, string/string/date column types, and a single process date.
The initial date must be today; subsequent upserts must preserve that original
date and must not append duplicates. The three expected pairs are `4111` →
`Transportation:Ride Sharing`, `5812` → `Food and Drinks:Restaurants`, and `5813`
→ `Food and Drinks:Fast Food`.

The first cycle uses fresh project-scoped volumes; cycles two and three restart
containers while retaining those volumes. The harness derives its configuration
from `docker-compose.yaml`, selects only required services, removes fixed names
and published ports, replaces persistent data mounts with owned volumes, and
mounts example/configuration inputs read-only. It copies PostgreSQL certificates
before changing container-side key permissions. Its isolated Trino config uses
HTTP within the private Compose network without password authentication, enables
native S3 access to MinIO, and loads only the Iceberg catalog. No host ports are
published. These overrides belong only to the smoke environment.

Cleanup always targets the unique `datapipe-smoke-*` project and removes its owned
volumes, including after failures. Developer data directories and other Compose
projects are untouched. Avoid interrupting cleanup; if interrupted, use the exact
project/file recorded in the report:

```sh
docker compose -p datapipe-smoke-<recorded-id> -f /path/to/evidence/compose.json down -v
```

`run-task` accepts `COMPOSE` (default `docker compose`) and `TASK_SERVICE`
(default `datapipe`) so the same numbered target runs against the isolated file.
The smoke check exits nonzero for command, readiness, timeout, task, output or
cleanup failures. Unit tests run without Docker and cover isolation, failure
propagation, query errors/pagination, exact rows, duplicate rows and schema/date
regressions. A unit-test pass alone is not evidence of three successful live
cycles; inspect `report.json` for `passed: true` and three passing cycles.
