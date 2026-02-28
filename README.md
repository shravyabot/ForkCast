# 🍽️ Chef's Table — Autonomous Meal Planner & Grocery Orderer

An autonomous AI agent that takes your dietary preferences, searches for recipes, builds an optimized weekly meal plan with a dependency graph, checks real-time ingredient availability, adapts when items are out of stock, and places your grocery order — all without manual intervention.

## 🏗️ Architecture

```
User Input → Recipe Search (Tavily) → Meal Plan (OpenAI) → Dependency Graph (Neo4j)
         → Availability Check (Tavily) → Adapt if needed (OpenAI + Neo4j)
         → Consolidated Order → Place Order
```

## 🔧 Sponsor Tools Used

- **🔍 Tavily** — Real-time recipe search, grocery deals, and ingredient availability
- **🕸️ Neo4j** — Ingredient/recipe dependency graph for smart adaptation
- **🤖 OpenAI** — Meal planning, substitution reasoning, order optimization
- **☁️ Render** — Cloud deployment

## 🚀 Quick Start

### 1. Prerequisites

- Python 3.10+
- Neo4j instance (free Aura tier or local Docker)
- API keys: OpenAI, Tavily

### 2. Setup

```bash
cd chefs-table
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your API keys
```

### 3. Neo4j Setup (Docker — optional)

```bash
docker run -p7474:7474 -p7687:7687 -d \
  -e NEO4J_AUTH=neo4j/secretgraph \
  neo4j:latest
```

Or use [Neo4j Aura](https://neo4j.com/cloud/aura/) free tier.

### 4. Run

```bash
streamlit run app.py
```

## 📊 Features

- **Autonomous Planning** — Full pipeline runs without manual intervention
- **Shared Ingredient Optimization** — Minimizes waste by reusing ingredients across meals
- **Real-Time Adaptation** — Detects unavailable ingredients and auto-substitutes
- **Dependency Graph** — Visual representation of recipe-ingredient relationships
- **Smart Ordering** — Consolidated, store-optimized grocery order with savings tips
- **Simulated Checkout** — End-to-end order placement flow

## 🏛️ Project Structure

```
chefs-table/
├── app.py                     # Streamlit frontend
├── agents/
│   ├── orchestrator.py        # Main autonomous pipeline
│   ├── recipe_searcher.py     # Tavily recipe + deal search
│   ├── meal_planner.py        # OpenAI meal planning
│   ├── graph_manager.py       # Neo4j graph operations
│   ├── availability_checker.py # Real-time stock check
│   └── order_placer.py        # Grocery order + checkout
├── config.py                  # Environment configuration
├── requirements.txt
├── render.yaml                # Render deployment config
└── .env.example
```

## 📝 License

MIT
