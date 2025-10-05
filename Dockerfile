# Dockerfile multi-stage pour GeoCAT RAG Stack
FROM python:3.11-slim as base

# Installer les dépendances système
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copier les requirements de base
COPY requirements/base.txt requirements/

# Stage pour le service API RAG
FROM base AS api

# Copier et installer les dépendances API
COPY requirements/api.txt requirements/
RUN pip install --no-cache-dir -r requirements/api.txt

# Copier les fichiers du service API
COPY services/api/ .

# Port pour l'API FastAPI
EXPOSE 8000

# Script d'entrée avec auto-ingestion
CMD sh -c "echo 'Démarrage du service API RAG...' && \
    echo 'Démarrage de l'\''API...' && \
    uvicorn main:app --host 0.0.0.0 --port 8000"

# Stage pour l'interface web
FROM base AS web

# Copier et installer les dépendances web
COPY requirements/web.txt requirements/
RUN pip install --no-cache-dir -r requirements/web.txt

# Copier les fichiers de l'interface web
COPY services/web/ .

# Port pour Gradio
EXPOSE 7860

# Script d'entrée avec attente des services
CMD sh -c "echo 'Démarrage de l'\''interface web...' && \
    echo 'Démarrage de Gradio...' && \
    python app.py"
