# GeoNetwork RAG Stack

Stack de recherche sémantique dans les catalogues de métadonnées GeoNetwork (configurable pour toute instance GeoNetwork).

## Démarrage rapide

```bash
# Démarrage simple (services seulement)
docker compose up -d

# Démarrage complet avec initialisation automatique
docker compose --profile init up -d

# Interface web : http://localhost:7860
```

## Services

| Service | Port | Description |
|---------|------|-------------|
| **Interface Web** | 7860 | Interface utilisateur Gradio |
| **API RAG** | 8000 | API FastAPI avec recherche hybride |
| **Elasticsearch** | 9200 | Base de données vectorielle |
| **Ollama** | 11434 | Serveur LLM (Llama 3.2) |

## Configuration

Le stack est entièrement configurable via les fichiers dans `/config` :

### Instance GeoNetwork
Copiez et adaptez le fichier exemple :
```bash
cp config/geonetwork-config.example.json config/geonetwork-config.json
```
Modifiez ensuite `name`, `base_url` et autres paramètres selon votre instance.

### Ingestion de métadonnées
Configurez les critères de sélection des métadonnées :
```bash
cp config/search-query.example.json config/search-query.json
```
Adaptez les `groupOwner` et critères selon vos besoins.

> **Astuce** : Consultez les fichiers `.example.json` pour voir toutes les options disponibles.

## Débogage

```bash
# Redémarrer un service
docker compose restart <service>

# Voir les logs
docker compose logs -f <service>

# Reset complet
docker compose down -v && docker compose --profile init up -d

# Vérifier les services
docker compose ps
```

## Architecture

- **Recherche hybride** : 70% vectorielle + 30% textuelle
- **LLM local** : Llama 3.2 via Ollama
- **Interface moderne** : Gradio avec filtrage par pertinence
- **Configuration externe** : Adaptable à toute instance GeoNetwork