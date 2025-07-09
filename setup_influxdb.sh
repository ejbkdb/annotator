#!/bin/bash

# InfluxDB Docker Setup Script
# This script sets up InfluxDB with Docker/Podman for the annotator project

set -e  # Exit on any error

echo "🚀 Setting up InfluxDB for annotator project..."

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're using Docker or Podman
if command -v docker &> /dev/null && docker info &> /dev/null; then
    CONTAINER_CMD="docker"
    COMPOSE_CMD="docker compose"
    print_status "Using Docker"
elif command -v podman &> /dev/null; then
    CONTAINER_CMD="podman"
    COMPOSE_CMD="docker compose"  # podman-compose via docker alias
    print_status "Using Podman"
else
    print_error "Neither Docker nor Podman found. Please install one of them."
    exit 1
fi

# Create docker-compose.yml if it doesn't exist
if [ ! -f "docker-compose.yml" ]; then
    print_status "Creating docker-compose.yml..."
    cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  influxdb:
    image: influxdb:2.7
    container_name: influxdb_annotator
    ports:
      - "8086:8086"
    volumes:
      - ./influxdb_data:/var/lib/influxdb2:Z
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=admin
      - DOCKER_INFLUXDB_INIT_PASSWORD=password123
      - DOCKER_INFLUXDB_INIT_ORG=my-org
      - DOCKER_INFLUXDB_INIT_BUCKET=default_audio
      - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=my-super-secret-token
EOF
    print_status "docker-compose.yml created"
else
    print_status "docker-compose.yml already exists"
fi

# Stop any existing containers
print_status "Stopping any existing containers..."
$COMPOSE_CMD down 2>/dev/null || true

# Clean up existing data directory if it exists
if [ -d "./influxdb_data" ]; then
    print_warning "Removing existing influxdb_data directory..."
    rm -rf ./influxdb_data
fi

# Create the data directory
print_status "Creating influxdb_data directory..."
mkdir -p ./influxdb_data

# Set permissions based on container runtime
if [ "$CONTAINER_CMD" = "podman" ]; then
    print_status "Setting up permissions for Podman..."
    
    # Try different permission approaches for Podman
    # Method 1: Use podman unshare if available
    if command -v podman &> /dev/null; then
        print_status "Using podman unshare to set correct ownership..."
        podman unshare chown -R 999:999 ./influxdb_data || {
            print_warning "podman unshare failed, trying alternative methods..."
            
            # Method 2: Set SELinux context for RHEL/CentOS/Fedora
            if command -v getenforce &> /dev/null && [ "$(getenforce)" != "Disabled" ]; then
                print_status "Setting SELinux context..."
                sudo chcon -Rt svirt_sandbox_file_t ./influxdb_data || print_warning "SELinux context setting failed"
            fi
            
            # Method 3: Set broader permissions
            print_status "Setting directory permissions..."
            sudo chmod -R 777 ./influxdb_data || print_warning "chmod failed"
        }
    fi
else
    # Docker setup
    print_status "Setting up permissions for Docker..."
    sudo chown -R 1000:1000 ./influxdb_data || print_warning "chown failed"
    sudo chmod -R 755 ./influxdb_data || print_warning "chmod failed"
fi

# Start the container
print_status "Starting InfluxDB container..."
$COMPOSE_CMD up -d

# Wait a moment for the container to start
sleep 3

# Check if container is running
if $CONTAINER_CMD ps --format "table {{.Names}}" | grep -q "influxdb_annotator"; then
    print_status "✅ InfluxDB container is running successfully!"
else
    print_error "❌ Container failed to start. Checking logs..."
    $COMPOSE_CMD logs influxdb
    
    # Try alternative fixes
    print_status "Trying alternative configuration..."
    
    # Update docker-compose.yml to run as root if permissions are still an issue
    cat > docker-compose.yml << 'EOF'
version: '3.8'
services:
  influxdb:
    image: influxdb:2.7
    container_name: influxdb_annotator
    user: "0:0"
    ports:
      - "8086:8086"
    volumes:
      - ./influxdb_data:/var/lib/influxdb2
    environment:
      - DOCKER_INFLUXDB_INIT_MODE=setup
      - DOCKER_INFLUXDB_INIT_USERNAME=admin
      - DOCKER_INFLUXDB_INIT_PASSWORD=password123
      - DOCKER_INFLUXDB_INIT_ORG=my-org
      - DOCKER_INFLUXDB_INIT_BUCKET=default_audio
      - DOCKER_INFLUXDB_INIT_ADMIN_TOKEN=my-super-secret-token
EOF
    
    print_status "Retrying with root user..."
    $COMPOSE_CMD down
    $COMPOSE_CMD up -d
    sleep 3
    
    if $CONTAINER_CMD ps --format "table {{.Names}}" | grep -q "influxdb_annotator"; then
        print_status "✅ InfluxDB container is now running!"
    else
        print_error "❌ Container still failed to start. Please check logs manually:"
        echo "Run: $COMPOSE_CMD logs influxdb"
        exit 1
    fi
fi

# Display connection info
print_status "🎉 Setup complete!"
echo ""
echo "InfluxDB is now running and accessible at:"
echo "  URL: http://localhost:8086"
echo "  Username: admin"
echo "  Password: password123"
echo "  Organization: my-org"
echo "  Bucket: default_audio"
echo "  Token: my-super-secret-token"
echo ""
echo "Data is stored in: $(pwd)/influxdb_data"
echo ""
echo "To stop: $COMPOSE_CMD down"
echo "To restart: $COMPOSE_CMD up -d"
echo "To view logs: $COMPOSE_CMD logs influxdb"