#!/bin/bash

# Set variables
ACR_NAME="celery"
RESOURCE_GROUP="app"
CONTAINER_NAME="redis-celery"
IMAGE_NAME="${ACR_NAME}.azurecr.io/redis-celery:latest"
REDIS_PASSWORD="vB2Ugfa35AuoUt75oQTLK5a7MGLWCmNVOAzCaBPJWXI="
REDIS_HOST="resolvemeq-cache.redis.cache.windows.net"
REDIS_PORT="6379"

# Deploy the container to Azure Container Instance
az container create \
  --resource-group ${RESOURCE_GROUP} \
  --name ${CONTAINER_NAME} \
  --image ${IMAGE_NAME} \
  --registry-login-server ${ACR_NAME}.azurecr.io \
  --registry-username ${ACR_NAME} \
  --registry-password $(az acr credential show --name ${ACR_NAME} --query "passwords[0].value" --output tsv) \
  --dns-name-label ${CONTAINER_NAME} \
  --ports ${REDIS_PORT} \
  --os-type Linux \
  --cpu 1 \
  --memory 1.5 \
  --environment-variables \
    REDIS_PASSWORD=${REDIS_PASSWORD} \
    REDIS_HOST=${REDIS_HOST} \
    REDIS_PORT=${REDIS_PORT} 