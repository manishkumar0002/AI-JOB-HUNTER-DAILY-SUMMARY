#!/bin/bash
# AI Job Hunter - Database Backup Script

# Load environment variables if .env exists in the parent directory
if [ -f ../.env ]; then
  export $(grep -v '^#' ../.env | xargs)
elif [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

DB_CONTAINER_NAME=${DB_CONTAINER_NAME:-job-hunter-db}
DB_USER=${POSTGRES_USER:-postgres}
DB_NAME=${POSTGRES_DB:-job_hunter}
BACKUP_DIR=$(dirname "$0")
DATE=$(date +%Y_%m_%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/backup_${DATE}.sql"

echo "Backing up database '${DB_NAME}' from container '${DB_CONTAINER_NAME}'..."
docker exec -t "$DB_CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" > "$BACKUP_FILE"

if [ $? -eq 0 ]; then
  echo "Backup successfully created: ${BACKUP_FILE}"
else
  echo "Backup failed! Please check if the Docker container is running."
  exit 1
fi
