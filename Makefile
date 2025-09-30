.PHONY: help all db query store stream app up down logs clean clean-all setup-data pyiceberg examples list-examples run-task build

TASK_PATH ?= $(shell grep '^TASK_PATH=' .env 2>/dev/null | cut -d'=' -f2)

YELLOW=\033[33m
GREEN=\033[32m
BLUE=\033[34m
RED=\033[31m
NC=\033[0m

help:
	@echo "$(BLUE)DataPipe Docker Compose Management$(NC)"
	@echo ""
	@echo "$(YELLOW)Usage:$(NC)"
	@echo "  make <target> [TASK_PATH=<path>]"
	@echo ""
	@echo "$(YELLOW)Available Profiles:$(NC)"
	@echo "  $(GREEN)all$(NC)     - All services (db + query + store + stream + app)"
	@echo "  $(GREEN)db$(NC)      - Database services (postgres, pg-data)"
	@echo "  $(GREEN)query$(NC)   - Query services (iceberg-rest, coordinator, minio, minio-client)"
	@echo "  $(GREEN)store$(NC)   - Storage services (minio, minio-client)"
	@echo "  $(GREEN)stream$(NC)  - Streaming services (flink, kafka, solace)"
	@echo "  $(GREEN)app$(NC)     - Application services (datapipe, iceberg-rest)"
	@echo ""
	@echo "$(YELLOW)Commands:$(NC)"
	@awk 'BEGIN {FS = ":.*##"}; /^[a-zA-Z_-]+:.*##/ { printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2 }' $(MAKEFILE_LIST)
	@echo ""
	@echo "$(YELLOW)Examples:$(NC)"
	@echo "  make all                                    # Start all services"
	@echo "  make app TASK_PATH=txnpipe/flow.yaml       # Run app with specific task"
	@echo "  make run-task TASK_PATH=bicycles/flow.yaml # Run single task"
	@echo "  make examples                              # List all example files"

all: local-perm
	@echo "$(BLUE)Starting all services...$(NC)"
	docker-compose --profile all up -d

db: local-perm
	@echo "$(BLUE)Starting database services...$(NC)"
	docker-compose --profile db up -d

local-perm:
	@chmod 600 containers/postgres/certs/server.key 2>/dev/null || true
query:
	@echo "$(BLUE)Starting query services...$(NC)"
	docker-compose --profile query up -d

store:
	@echo "$(BLUE)Starting storage services...$(NC)"
	docker-compose --profile store up -d

stream:
	@echo "$(BLUE)Starting streaming services...$(NC)"
	docker-compose --profile stream up -d

app: local-perm
	@echo "$(BLUE)Starting application services...$(NC)"
	@if [ -z "$(TASK_PATH)" ]; then \
		echo "$(RED)Warning: TASK_PATH not set. Using default from .env$(NC)"; \
	else \
		echo "$(GREEN)Using TASK_PATH: $(TASK_PATH)$(NC)"; \
	fi
	TASK_PATH="$(TASK_PATH)" docker-compose --profile=store --profile=db --profile=app up -d

up: all

down:
	@echo "$(BLUE)Stopping all services...$(NC)"
	docker-compose --profile="*" down

stop: down

logs:
	docker-compose logs -f

logs-%:
	docker-compose --profile $* logs -f

clean:
	@echo "$(BLUE)Cleaning up all services and volumes...$(NC)"
	docker-compose --profile="*" down -v
	docker-compose down --remove-orphans

clean-all: clean	## Clean up all services, volumes, and persistent data folders
	@echo "$(BLUE)Removing persistent data folders...$(NC)"
	@if [ -d "./containers/postgres/data" ]; then \
		echo "$(YELLOW)Removing PostgreSQL data...$(NC)"; \
		rm -rf ./containers/postgres/data || sudo rm -rf ./containers/postgres/data; \
	fi
	@if [ -d "./containers/minio/data" ]; then \
		echo "$(YELLOW)Removing MinIO data...$(NC)"; \
		rm -rf ./containers/minio/data || sudo rm -rf ./containers/minio/data; \
	fi
	@if [ -d "./containers/kafka/data" ]; then \
		echo "$(YELLOW)Removing Kafka data...$(NC)"; \
		rm -rf ./containers/kafka/data || sudo rm -rf ./containers/kafka/data; \
	fi
	@if [ -d "./containers/solace/data" ]; then \
		echo "$(YELLOW)Removing Solace data...$(NC)"; \
		rm -rf ./containers/solace/data || sudo rm -rf ./containers/solace/data; \
	fi
	@echo "$(GREEN)Complete cleanup finished - all state removed$(NC)"

build:
	@echo "$(BLUE)Building datapipe image...$(NC)"
	docker build --no-cache -t datapipe:latest .

pyiceberg:
	@if [[ ! -d ~/.venv/pyiceberg ]]; then python3 -m venv ~/.venv/pyiceberg; fi; \
	source ~/.venv/pyiceberg/bin/activate && \
	if ! python -c "import pyiceberg" 2>/dev/null; then \
		echo "$(YELLOW)Installing pyiceberg...$(NC)"; \
		pip install pyiceberg; \
	fi

setup-data: store db pyiceberg
	@echo "$(BLUE)Setting up sample data...$(NC)"
	./setup-data.sh

run-task:
	@if [ -z "$(TASK_PATH)" ]; then \
		echo "$(RED)Error: TASK_PATH is required$(NC)"; \
		echo "Usage: make run-task TASK_PATH=path/to/task.yaml"; \
		exit 1; \
	fi
	$(eval CLEAN_TASK_PATH := $(shell echo "$(TASK_PATH)" | sed 's|^examples/||'))
	@if [ ! -f "examples/$(CLEAN_TASK_PATH)" ]; then \
		echo "$(RED)Error: Task file examples/$(CLEAN_TASK_PATH) not found$(NC)"; \
		exit 1; \
	fi
	@echo "$(GREEN)Running task: $(CLEAN_TASK_PATH)$(NC)"
	TASK_PATH="$(CLEAN_TASK_PATH)" docker-compose run --rm datapipe


examples:
	@echo "$(BLUE)Available Examples:$(NC)"
	@echo ""
	@echo "$(YELLOW)Flow Files:$(NC)"
	@find examples -name "flow.yaml" -type f | sed 's|examples/||' | sort | sed 's/^/  /'
	@echo ""
	@echo "$(YELLOW)Task Files:$(NC)"
	@find examples -path "*/tasks/*.yaml" -type f | sed 's|examples/||' | sort | sed 's/^/  /'
	@echo ""
	@echo "$(YELLOW)Dataset Files:$(NC)"
	@find examples -path "*/datasets/*.yaml" -type f | sed 's|examples/||' | sort | sed 's/^/  /'
	@echo ""
	@echo "$(YELLOW)Schema Files:$(NC)"
	@find examples -path "*/schemas/*.yaml" -type f | sed 's|examples/||' | sort | sed 's/^/  /'

list-examples: examples

1:
	@$(MAKE) run-task TASK_PATH=txnsharing/tasks/1-prepare-categories.yaml

1-prepare-categories: 1

1-prepare-categories-flink:
	@$(MAKE) run-task TASK_PATH=txnsharing/tasks/1-prepare-categories-flink.yaml

2:
	@$(MAKE) run-task TASK_PATH=txnsharing/tasks/2-prepare-merchants.yaml

2-prepare-merchants: 2

3:
	@$(MAKE) run-task TASK_PATH=txnsharing/tasks/3-share-raw-txns.yaml

3-share-transactions: 3

4:
	@$(MAKE) run-task TASK_PATH=txnsharing/tasks/4-update-categories.yaml

4-update-categories: 4

5:
	@$(MAKE) run-task TASK_PATH=txnsharing/tasks/5-update-merchants.yaml

5-update-merchants: 5

6:
	@$(MAKE) run-task TASK_PATH=txnpipe/tasks/load-raw-txn-data.yaml

6-save-transactions: 6

7:
	@$(MAKE) run-task TASK_PATH=txnpipe/tasks/load-balance-data.yaml

7-save-balances: 7

8:
	@$(MAKE) run-task TASK_PATH=txnpipe/tasks/create-monthly-balance-snapshot.yaml

8-monthly-balance: 8

10:
	@$(MAKE) run-task TASK_PATH=txnpipe/tasks/show-txns.yaml

10-print-transactions: 10

11:
	@$(MAKE) run-task TASK_PATH=bicycles/tasks/1-london-bicycles-data.yaml

11-bicycles-data: 11

0:
	@$(MAKE) run-task TASK_PATH=jira/tasks/1-prepare-jira-data.yaml

1-jira-data: 0

12:
	@$(MAKE) run-task TASK_PATH=spacex/tasks/12-rocket-launches.yaml

12-rocket-launches: 12

13:
	@$(MAKE) run-task TASK_PATH=spacex/tasks/13-rocket-launches-transform.yaml

13-rocket-launches: 13

14:
	@$(MAKE) run-task TASK_PATH=jira/tasks/14-fetch-jira-api-data.yaml

14-fetch-jira-data: 14

15:
	@$(MAKE) run-task TASK_PATH=jira/tasks/15-show-jira-parquet.yaml

15-show-jira-parquet: 15

16:
	@$(MAKE) run-task TASK_PATH=jdbc/tasks/16-load-iceberg-tables.yaml

16-load-iceberg-tables: 16

17:
	@$(MAKE) run-task TASK_PATH=jdbc/tasks/17-show-iceberg-table-info.yaml

17-show-iceberg-table-info: 17



dev-db:
	@$(MAKE) db

dev-query:
	@$(MAKE) db query

dev-all:
	@$(MAKE) all
	@echo "$(GREEN)All services started. Access points:$(NC)"
	@echo "  Trino:     http://localhost:8080"
	@echo "  MinIO:     http://localhost:9001 (admin/admin)"
	@echo "  Flink:     http://localhost:8081"
	@echo "  Kafka UI:  http://localhost:8080"
	@echo "  DataPipe:  http://localhost:8090"
	@echo "  Solace:    http://localhost:9040"

catalog-list: pyiceberg
	@source ~/.venv/pyiceberg/bin/activate && pyiceberg --uri http://localhost:8181 list

catalog-list-%: pyiceberg
	@source ~/.venv/pyiceberg/bin/activate && pyiceberg --uri http://localhost:8181 list $*

catalog-describe: pyiceberg
	@if [ -z "$(TABLE)" ]; then \
		echo "$(RED)Error: TABLE is required$(NC)"; \
		echo "Usage: make catalog-describe TABLE=namespace.table"; \
		exit 1; \
	fi
	@source ~/.venv/pyiceberg/bin/activate && pyiceberg --uri http://localhost:8181 describe $(TABLE)

catalog-drop: pyiceberg
	@if [ -z "$(TABLE)" ]; then \
		echo "$(RED)Error: TABLE is required$(NC)"; \
		echo "Usage: make catalog-drop TABLE=namespace.table"; \
		exit 1; \
	fi
	@echo "$(RED)Dropping table: $(TABLE)$(NC)"
	@read -p "Are you sure you want to drop $(TABLE)? [y/N]: " confirm && [ "$$confirm" = "y" ]
	@name=pyiceberg; source ~/.venv/$$name/bin/activate && pyiceberg --uri http://localhost:8181 drop table $(TABLE)

s3:
	@if [ -z "$(filter-out $@,$(MAKECMDGOALS))" ]; then \
		echo "$(RED)Error: S3 command is required$(NC)"; \
		echo "Usage: make s3 <command> [args...]"; \
		echo "Examples:"; \
		echo "  make s3 ls s3://warehouse"; \
		echo "  make s3 cp file.txt s3://warehouse/data/"; \
		echo "  make s3 mb s3://newbucket"; \
		echo "  make s3 rb s3://bucket"; \
		exit 1; \
	fi
	@echo "$(BLUE)Running S3 command: $(filter-out $@,$(MAKECMDGOALS))$(NC)"
	@AWS_ACCESS_KEY_ID=minioadmin AWS_SECRET_ACCESS_KEY=minioadmin aws --endpoint-url http://localhost:9000 s3 $(filter-out $@,$(MAKECMDGOALS))

%:
	@:

ps:
	docker-compose ps

status: ps

restart:
	@$(MAKE) down
	@$(MAKE) up

restart-%:
	docker-compose --profile $* restart
