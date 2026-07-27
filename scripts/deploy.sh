#!/bin/bash
# Build and Deploy Script for Security Dashboard v2

set -e

echo "=== Security Dashboard v2 - Build & Deploy ==="

# Build backend image
echo ""
echo "📦 Building backend image..."
cd backend
docker build -f Dockerfile.prod -t security-dashboard-backend-v2:latest .

# Check if sec-mysql is running
echo ""
echo "🔍 Checking existing containers..."
if docker ps | grep -q sec-mysql; then
    echo "✅ sec-mysql is running"
else
    echo "❌ sec-mysql is not running. Please start it first."
    exit 1
fi

# Stop old backend if running
echo ""
echo "🛑 Stopping old backend if running..."
docker stop sec-backend 2>/dev/null || true
docker rm sec-backend 2>/dev/null || true

# Start new backend
echo ""
echo "🚀 Starting new backend..."
docker run -d \
    --name sec-backend \
    --network host \
    --restart unless-stopped \
    -e SECRET_KEY=sec-sys-2024-safe-key-v2 \
    -e JWT_SECRET_KEY=jwt-sec-key-2024-v2 \
    -e MYSQL_HOST=127.0.0.1 \
    -e MYSQL_PORT=3306 \
    -e MYSQL_USER=secuser \
    -e MYSQL_PASSWORD=SecPwd2024! \
    -e MYSQL_DATABASE=security_dashboard \
    -e ES_HOST=35.241.110.62 \
    -e ES_PORT=9200 \
    -e ES_SCHEME=https \
    -e ES_USER=elastic \
    -e ES_PASSWORD='+gQUm1G94_et=7PwnHj*' \
    -e ES_INDEX='online*nginx*' \
    -e ES_VERIFY_CERTS=false \
    security-dashboard-backend-v2:latest

# Wait for backend to start
echo ""
echo "⏳ Waiting for backend to start..."
sleep 5

# Health check
echo ""
echo "🏥 Health check..."
if curl -s http://localhost:5000/health | grep -q healthy; then
    echo "✅ Backend is healthy!"
else
    echo "❌ Backend health check failed"
    docker logs sec-backend --tail 50
    exit 1
fi

echo ""
echo "=== Deployment Complete ==="
echo "Backend: http://localhost:5000"
echo "API Docs: http://localhost:5000/api/docs"
echo "Login: admin / 123456"
