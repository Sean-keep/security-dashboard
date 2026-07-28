#!/bin/bash
set -e

echo "=== Setting up Security Dashboard V2 ==="

# Backend dependencies
echo "[1/4] Installing backend dependencies..."
cd /workspaces/security-dashboard/backend
pip install -r requirements.txt -q

# Frontend dependencies
echo "[2/4] Installing frontend dependencies..."
cd /workspaces/security-dashboard/frontend
npm install --legacy-peer-deps -q

# Create env file for backend
echo "[3/4] Creating backend .env..."
cat > /workspaces/security-dashboard/backend/.env << 'EOF'
SECRET_KEY=dev-secret-key-change-in-production
JWT_SECRET_KEY=dev-jwt-secret-change-in-production
MYSQL_HOST=YOUR_MYSQL_HOST
MYSQL_PORT=3306
MYSQL_USER=YOUR_MYSQL_USER
MYSQL_PASSWORD=YOUR_MYSQL_PASSWORD
MYSQL_DATABASE=security_dashboard
ES_HOST=YOUR_ES_HOST
ES_PORT=9200
ES_SCHEME=https
ES_USER=elastic
ES_PASSWORD=YOUR_ES_PASSWORD
ES_INDEX=online*nginx*
ES_VERIFY_CERTS=false
TZ=Asia/Shanghai
EOF

# Build frontend
echo "[4/4] Building frontend..."
cd /workspaces/security-dashboard/frontend
npm run build -q

echo ""
echo "=== Setup complete! ==="
echo ""
echo "⚠️  Before starting, update backend/.env with your MySQL and Elasticsearch credentials."
echo ""
echo "To start the backend:"
echo "  cd backend && uvicorn app.main:app --host 0.0.0.0 --port 5000 --reload"
echo ""
echo "To start the frontend (dev mode):"
echo "  cd frontend && npm run dev"
echo ""
echo "To preview the built frontend:"
echo "  cd frontend && npm run preview"
echo ""
