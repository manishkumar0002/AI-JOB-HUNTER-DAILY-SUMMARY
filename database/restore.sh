#!/bin/bash
# AI Job Hunter - Database Restore Script

# Load environment variables if .env exists
if [ -f ../.env ]; then
  export $(grep -v '^#' ../.env | xargs)
elif [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

DB_CONTAINER_NAME=${DB_CONTAINER_NAME:-job-hunter-db}
DB_USER=${POSTGRES_USER:-postgres}
DB_NAME=${POSTGRES_DB:-job_hunter}

if [ -z "$1" ]; then
  echo "Usage: $0 <path_to_backup_file.sql>"
  exit 1
fi

BACKUP_FILE=$1

if [ ! -f "$BACKUP_FILE" ]; then
  echo "Error: Backup file '$BACKUP_FILE' does not exist."
  exit 1
fi

echo "Restoring database '${DB_NAME}' in container '${DB_CONTAINER_NAME}' from file '${BACKUP_FILE}'..."

docker exec -i "$DB_CONTAINER_NAME" psql -U "$DB_USER" -d "$DB_NAME" < "$BACKUP_FILE"

if [ $? -eq 0 ]; then
  echo "Database restore completed successfully."
else
  echo "Database restore failed!"
  exit 1
fi
