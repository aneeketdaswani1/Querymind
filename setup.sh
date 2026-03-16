#!/bin/bash

set -e

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
print_step() {
    echo -e "${BLUE}==>${NC} $1"
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

# Get the script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

print_step "QueryMind Setup Script"
echo ""

# Check prerequisites
print_step "Checking prerequisites..."

if ! command -v python3 &> /dev/null; then
    print_error "Python 3 is not installed"
    exit 1
fi
print_success "Python 3 found: $(python3 --version)"

if ! command -v docker &> /dev/null; then
    print_error "Docker is not installed"
    exit 1
fi
print_success "Docker found: $(docker --version)"

if ! command -v docker-compose &> /dev/null; then
    print_error "Docker Compose is not installed"
    exit 1
fi
print_success "Docker Compose found: $(docker-compose --version)"

echo ""

# Create virtual environment
print_step "Creating Python virtual environment..."
if [ -d "$SCRIPT_DIR/venv" ]; then
    print_success "Virtual environment already exists"
else
    python3 -m venv "$SCRIPT_DIR/venv"
    print_success "Virtual environment created"
fi

# Activate virtual environment
source "$SCRIPT_DIR/venv/bin/activate"
print_success "Virtual environment activated"

echo ""

# Upgrade pip, setuptools, wheel
print_step "Upgrading pip, setuptools, wheel..."
pip install --upgrade pip setuptools wheel -q
print_success "Package managers upgraded"

echo ""

# Install agent dependencies
print_step "Installing agent dependencies..."
pip install -r "$SCRIPT_DIR/agent/requirements.txt" -q
print_success "Agent dependencies installed"

# Install API dependencies
print_step "Installing API dependencies..."
pip install -r "$SCRIPT_DIR/api/requirements.txt" -q
print_success "API dependencies installed"

echo ""

# Copy .env.example to .env if it doesn't exist
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    print_step "Creating .env file from .env.example..."
    cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
    print_success ".env file created (update with your actual values)"
else
    print_success ".env file already exists"
fi

echo ""

# Start PostgreSQL and Redis with Docker Compose
print_step "Starting PostgreSQL and Redis containers..."

# Check if containers are already running
if docker ps | grep -q querymind-postgres; then
    print_success "PostgreSQL container already running"
else
    docker-compose -f "$SCRIPT_DIR/docker-compose.yml" up -d postgres redis
    print_success "PostgreSQL and Redis containers started"
    
    # Wait for PostgreSQL to be ready
    print_step "Waiting for PostgreSQL to be ready..."
    sleep 5
    
    # Retry loop for database connection
    RETRIES=30
    while [ $RETRIES -gt 0 ]; do
        if PGPASSWORD=querymind_password psql -h localhost -U querymind_user -d querymind -c "SELECT 1" &> /dev/null; then
            print_success "PostgreSQL is ready"
            break
        fi
        RETRIES=$((RETRIES - 1))
        if [ $RETRIES -eq 0 ]; then
            print_error "Could not connect to PostgreSQL after 30 attempts"
            exit 1
        fi
        sleep 1
    done
fi

echo ""

# Run seed scripts
print_step "Running database seed scripts..."

PGPASSWORD=querymind_password psql -h localhost -U querymind_user -d querymind < "$SCRIPT_DIR/data/seed_ecommerce.sql" > /dev/null 2>&1
print_success "E-commerce seed data loaded"

PGPASSWORD=querymind_password psql -h localhost -U querymind_user -d querymind < "$SCRIPT_DIR/data/seed_saas_metrics.sql" > /dev/null 2>&1
print_success "SaaS metrics seed data loaded"

echo ""
echo -e "${GREEN}================================${NC}"
echo -e "${GREEN}✓ Setup completed successfully!${NC}"
echo -e "${GREEN}================================${NC}"
echo ""
echo "Next steps:"
echo "1. Update .env file with your ANTHROPIC_API_KEY"
echo "2. Run the api:       cd api && uvicorn main:app --reload"
echo "3. Run the agent:     python -m agent.graph.graph"
echo "4. Run the frontend:  cd web && npm install && npm run dev"
echo ""
echo "PostgreSQL: localhost:5432 (user: querymind_user, password: querymind_password)"
echo "Redis:     localhost:6379"
echo ""
echo "To deactivate the virtual environment, run: deactivate"
echo "To stop containers, run:                   docker-compose down"
