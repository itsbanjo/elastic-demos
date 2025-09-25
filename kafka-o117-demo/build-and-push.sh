# build-and-push.sh
#!/bin/bash

# Configuration
DOCKER_REGISTRY="docker.io"  # Change to your registry
DOCKER_USERNAME="username"  # Replace with your Docker Hub username
IMAGE_NAME="iccp-simulator"
VERSION="v1.0.0"

echo "🔨 Building ICCP Simulator Docker Image"

# Build the image
docker build -t ${DOCKER_REGISTRY}/${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION} build/
docker build -t ${DOCKER_REGISTRY}/${DOCKER_USERNAME}/${IMAGE_NAME}:latest build/

echo "📤 Pushing to Docker Registry"

# Push both tags
docker push ${DOCKER_REGISTRY}/${DOCKER_USERNAME}/${IMAGE_NAME}:${VERSION}
docker push ${DOCKER_REGISTRY}/${DOCKER_USERNAME}/${IMAGE_NAME}:latest

echo "✅ Build and push complete!"
echo "🐳 Image: ${DOCKER_REGISTRY}/${DOCKER_USERNAME}/${IMAGE_NAME}:latest"