alfred/

├── README.md

├── .gitignore

│

├── backend/

│   ├── main.py                 # FastAPI API entrypoint

│   ├── requirements.txt        # Python deps (FastAPI, SQLAlchemy, OpenAI, pgvector)

│   ├── db/

│   │   ├── models.py

│   │   ├── schema.sql

│   │   └── repo.py

│   ├── agents/

│   │   ├── watcher.py

│   │   ├── parser.py

│   │   ├── ranker.py

│   │   ├── tailor.py

│   │   └── apply.py

│   ├── rag/

│   │   ├── ingest.py

│   │   └── retriever.py

│   └── tests/

│       └── test\_api.py

│

├── frontend/

│   ├── package.json

│   ├── pages/

│   └── components/

│

├── infrastructure/

│   ├── docker-compose.yml      # Local dev stack (FastAPI + Postgres)

│   ├── local/

│   │   └── setup.sh

│   └── aws/

│       └── README.md           # Deployment notes (later)

│

└── docs/

&nbsp;   └── notes.md



