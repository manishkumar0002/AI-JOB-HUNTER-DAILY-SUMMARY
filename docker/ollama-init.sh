#!/bin/bash
# AI Job Hunter - Ollama Init Script

OLLAMA_HOST_URL="http://ollama:11434"
MODEL_NAME=${OLLAMA_MODEL:-gemma2:2b}

echo "Waiting for Ollama service to start at ${OLLAMA_HOST_URL}..."
until curl -s -o /dev/null -w "%{http_code}" "${OLLAMA_HOST_URL}/api/tags" | grep -q "200"; do
  sleep 2
done

echo "Ollama is ready. Checking if model '${MODEL_NAME}' is loaded..."

# Check if model already exists
if curl -s "${OLLAMA_HOST_URL}/api/tags" | grep -q "${MODEL_NAME}"; then
  echo "Model '${MODEL_NAME}' already pulled."
else
  echo "Model '${MODEL_NAME}' not found. Pulling model '${MODEL_NAME}'..."
  curl -X POST "${OLLAMA_HOST_URL}/api/pull" -d "{\"name\": \"${MODEL_NAME}\"}"
  echo ""
  echo "Model '${MODEL_NAME}' pulled successfully."
fi

echo "Ollama initialization complete. Exiting."
