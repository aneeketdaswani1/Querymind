# QueryMind - AI Data Analyst Agent

## Overview

QueryMind is an AI Data Analyst Agent that converts natural language questions into SQL queries, executes them safely against PostgreSQL databases, visualizes results interactively, and explains insights in plain English.

## Features

- **Natural Language to SQL**: Converts user questions into executable SQL queries using Claude LLM
- **Safety First**: All generated queries validated through a safety checker to prevent dangerous operations
- **Interactive Visualizations**: Automatically recommends and generates appropriate charts for query results
- **Intelligent Insights**: Provides natural language summaries and analysis of query results
- **Multi-turn Conversations**: Maintains conversation context for follow-up questions
- **Schema-aware Generation**: LLM has full context of your database schema for accurate queries

## Tech Stack

### Agent
- **Python 3.11+**
- **LangGraph**: Agentic workflow orchestration
- **LangChain**: LLM integration framework
- **Pydantic v2**: Data validation and schemas
- **Anthropic Claude**: Language model via langchain-anthropic
- **structlog**: Structured logging

### API
- **FastAPI**: Modern async web framework
- **SQLAlchemy 2.0**: Database ORM
- **PostgreSQL 16**: Primary database (read-only user)
- **Redis**: Conversation state caching
- **psycopg2**: PostgreSQL driver

### Frontend
- **Next.js 14**: React framework with App Router
- **TypeScript**: Type-safe components
- **Tailwind CSS**: Utility-first styling
- **Recharts**: Data visualization library

## Project Structure

```
querymind/
├── agent/                 # LangGraph agent
│   ├── core/             # Core components
│   │   ├── schema_loader.py
│   │   ├── sql_generator.py
│   │   ├── safety_checker.py
│   │   ├── query_executor.py
│   │   ├── viz_recommender.py
│   │   ├── insight_narrator.py
│   │   └── input_sanitizer.py
│   ├── graph/            # LangGraph definitions
│   │   ├── state.py
│   │   ├── nodes.py
│   │   └── graph.py
│   ├── prompts/          # System prompts & few-shot examples
│   │   ├── system.py
│   │   └── few_shot.py
│   ├── eval/             # Evaluation utilities
│   │   ├── evaluate.py
│   │   └── test_questions.json
│   ├── config.py         # Configuration
│   └── requirements.txt   # Python dependencies
│
├── api/                  # FastAPI backend
│   ├── main.py          # Application entry point
│   ├── routers/         # API routes
│   │   ├── query.py
│   │   ├── schema.py
│   │   └── feedback.py
│   ├── services/        # Business logic
│   │   └── conversation.py
│   ├── schemas/         # Pydantic models
│   └── requirements.txt
│
├── web/                 # Next.js frontend (to be created)
│
├── data/                # Database seeds
│   ├── seed_ecommerce.sql
│   └── seed_saas_metrics.sql
│
├── docker-compose.yml   # Docker services
├── .env.example         # Environment template
├── .gitignore          # Git ignore rules
└── README.md           # This file
```

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 18+ (for frontend)
- Docker & Docker Compose
- PostgreSQL 16
- Anthropic API key

### Environment Setup

1. Clone the repository
2. Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

3. Update `.env` with your actual values:

```env
AGENT_DATABASE_URL=postgresql://querymind_readonly:querymind_readonly_password@localhost:5432/querymind
APP_DATABASE_URL=postgresql://querymind_app:querymind_app_password@localhost:5432/querymind
# Backward-compatible alias
DATABASE_URL=postgresql://querymind_app:querymind_app_password@localhost:5432/querymind
ANTHROPIC_API_KEY=your-anthropic-key
REDIS_URL=redis://localhost:6379
```

### Running with Docker Compose

```bash
docker-compose up -d
```

This starts:
- PostgreSQL 16
- Redis
- FastAPI backend (port 8000)
- Next.js frontend (port 3000)

### Manual Setup (Development)

#### Agent & API

```bash
# Install agent dependencies
cd agent
pip install -r requirements.txt

# Install API dependencies
cd ../api
pip install -r requirements.txt
```

#### Frontend

```bash
cd ../web
npm install
npm run dev
```

## Usage

1. **Start the services**:
   ```bash
   docker-compose up -d
   ```

2. **Access the frontend**: http://localhost:3000

3. **Ask natural language questions** about your data:
   - "How many orders were placed in the last month?"
   - "What are the top 5 products by revenue?"
   - "Show me user growth trends over time"

4. **View results**: Queries auto-generate visualizations and insights

## API Endpoints

### Query Execution
- `POST /api/query` - Submit a natural language question
- `GET /api/query/{id}` - Get query results
- `GET /api/query/{id}/status` - Check execution status

### Schema Information
- `GET /api/schema` - Get full database schema
- `GET /api/schema/tables` - List all tables
- `GET /api/schema/tables/{name}` - Get table details

### Feedback
- `POST /api/feedback` - Submit feedback on results

## Configuration

All configuration is managed through environment variables in `.env`. See `.env.example` for available options.

Key settings:
- `AGENT_DATABASE_URL`: PostgreSQL connection used for agent SQL execution (read-only user)
- `APP_DATABASE_URL`: Separate PostgreSQL connection for non-agent application concerns
- `DATABASE_URL`: Backward-compatible alias to `AGENT_DATABASE_URL`
- `ANTHROPIC_API_KEY`: Claude API key
- `REDIS_URL`: Redis connection for conversation state
- `LOG_LEVEL`: structlog level (INFO, DEBUG, etc.)

## Safety & Security

- **Read-only database user**: All queries execute against a PostgreSQL user with SELECT-only permissions
- **Role separation**: Distinct DB users for admin/bootstrap, app operations, and agent read-only execution
- **SQL validation**: Generated queries validated through SafetyChecker before execution
- **Input sanitization**: User inputs sanitized to prevent SQL injection
- **No data modification**: Agent explicitly prevented from generating INSERT/UPDATE/DELETE queries

## Testing

### Agent Tests
```bash
cd agent
pytest
```

### API Tests
```bash
cd api
pytest
```

### Agent Evaluation
```bash
cd agent
python eval/evaluate.py
```

## Development

### Adding New Database Seeds

1. Create SQL files in `/data/` directory
2. Name pattern: `seed_<database_name>.sql`
3. Include schema creation and sample data
4. Update docker-compose.yml to run seed on startup

### Extending the Agent

The agent uses LangGraph's StateGraph pattern. To add new capabilities:

1. Create new node in `agent/graph/nodes.py`
2. Add logic in corresponding `agent/core/` module
3. Connect node in `agent/graph/graph.py`
4. Update state schema in `agent/graph/state.py`

### Frontend Development

Frontend is a Next.js app with TypeScript and Recharts:

```bash
cd web
npm run dev      # Start dev server
npm run build    # Production build
npm run lint     # Run ESLint
```

## License

Proprietary - QueryMind

## Support

For issues and questions, please open an issue in the repository.
