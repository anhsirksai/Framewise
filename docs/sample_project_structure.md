# Framewise Project Structure

```text
Framewise-HackerSquad/
|-- backend/
|   |-- app/
|   |   |-- agent.py                  # Strands agent and tool definitions
|   |   |-- context_graph_client.py    # Neo4j graph reads/writes
|   |   |-- routes.py                  # FastAPI endpoints
|   |   |-- twelvelabs_client.py       # TwelveLabs index/search/analyze/embed
|   |   |-- vector_client.py           # Neo4j vector search helpers
|   |   `-- memory.py                  # first-cut session memory
|   |-- scripts/
|   |   `-- ingest.py                  # local video -> intelligence graph
|   `-- tests/
|-- frontend/
|   |-- app/
|   |-- components/
|   |   |-- ChatInterface.tsx
|   |   |-- ContextGraphView.tsx
|   |   `-- VideoBrowser.tsx
|   `-- lib/
|-- cypher/
|   `-- schema.cypher                 # constraints, indexes, vector index notes
|-- data/
|   |-- videos/                       # local MP4s for hackathon ingestion
|   `-- ontology.yaml
|-- docs/
|   |-- ROADMAP.md
|   `-- video-intelligence-platform.html
|-- Makefile
|-- README.md
`-- docker-compose.yml
```

