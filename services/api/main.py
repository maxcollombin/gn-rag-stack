from fastapi import FastAPI
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer
import uvicorn
import requests
import json
import hashlib
from functools import lru_cache
import time
from concurrent.futures import ThreadPoolExecutor
import asyncio

app = FastAPI()
es = Elasticsearch("http://elasticsearch:9200")
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# Cache en mémoire pour les embeddings fréquents
embedding_cache = {}
response_cache = {}

# Pool de threads pour les appels parallèles
executor = ThreadPoolExecutor(max_workers=4)

@lru_cache(maxsize=100)
def get_embedding(query: str):
    """Cache des embeddings pour éviter la re-génération"""
    query_hash = hashlib.md5(query.encode()).hexdigest()
    if query_hash in embedding_cache:
        return embedding_cache[query_hash]
    
    vec = model.encode(query).tolist()
    embedding_cache[query_hash] = vec
    return vec

def search_geocat_optimized(query: str, num_results: int = 20, min_score: float = 0.0):
    """Recherche sémantique optimisées avec requête hybride et filtrage par score"""
    print(f"DEBUG: search_geocat_optimized called with num_results={num_results}, min_score={min_score}")
    vec = get_embedding(query)
    
    # Requête hybride : vectorielle + textuelle pour de meilleurs résultats
    resp = es.search(
        index="geonetwork",
        size=num_results,
        _source=["uuid", "title", "abstract", "embedding"],
        timeout="10s",
        query={
            "bool": {
                "should": [
                    # Recherche vectorielle (poids principal)
                    {
                        "script_score": {
                            "query": {"match_all": {}},
                            "script": {
                                "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                                "params": {"query_vector": vec}
                            },
                            "boost": 0.7
                        }
                    },
                    # Recherche textuelle (boost additionnel)
                    {
                        "multi_match": {
                            "query": query,
                            "fields": ["title^2", "abstract"],
                            "type": "best_fields",
                            "boost": 0.3
                        }
                    }
                ]
            }
        }
    )
    
    # Retourner les résultats avec les scores de pertinence et filtrage manuel
    results = []
    for hit in resp["hits"]["hits"]:
        score = hit["_score"]
        # Filtrage manuel par score minimum
        if score >= min_score:
            result = hit["_source"].copy()
            result["relevance_score"] = round(score, 3)  # Score de pertinence arrondi
            results.append(result)
    
    print(f"DEBUG: Found {len(results)} results with score >= {min_score}")
    return results

def generate_response_optimized(query: str, context_docs: list):
    """Génération optimisées avec cache et timeout adaptatif"""
    # Cache des réponses basé sur le hash de la query + contexte
    context_hash = hashlib.md5((query + str([doc['uuid'] for doc in context_docs])).encode()).hexdigest()
    
    if context_hash in response_cache:
        return response_cache[context_hash]
    
    # Contexte enrichi avec plus d'informations pertinentes
    context = "\n\n".join([
        f"*{doc['title']}*\n"
        f"Description : {doc['abstract'][:300]}{'...' if len(doc['abstract']) > 300 else ''}\n"
        f"Identifiant : {doc['uuid']}"
        for doc in context_docs[:5]  # Augmenté à 5 documents pour plus de contexte
    ])
    
    # Prompt optimisé pour de meilleurs résultats
    prompt = f"""Tu es un assistant spécialisé dans les géodonnées. Réponds de manière précise et structurée.

Informations disponibles :
{context}

Question : {query}

Instructions :
- Réponds directement à la question posée
- Utilise uniquement les informations fournies ci-dessus
- Structure ta réponse avec des paragraphes courts
- Indique clairement quand aucune information n'est disponible
- Reste factuel et évite les généralités

Réponse :"""

    try:
        start_time = time.time()
        response = requests.post(
            "http://ollama:11434/api/generate",
            json={
                "model": "llama3.2:latest", 
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,  # Légèrement plus créatif pour des réponses naturelles
                    "top_p": 0.95,       # Meilleur équilibre créativité/cohérence
                    "top_k": 50,         # Améliore la diversité du vocabulaire
                    "num_predict": 400,  # Plus de place pour des réponses détaillées
                    "repeat_penalty": 1.1 # Évite les répétitions
                }
            },
            timeout=45  # Timeout plus court
        )
        
        result = response.json().get("response", "Erreur de génération")
        generation_time = time.time() - start_time
        
        # Cache seulement les réponses rapides (< 30s)
        if generation_time < 30:
            response_cache[context_hash] = result
        
        return result
        
    except Exception as e:
        return f"Erreur génération: {e}"

@app.post("/rag")
def rag_search(request: dict):
    """Endpoint RAG optimisées: recherche + génération avec filtrage par pertinence"""
    query = request.get("query", "")
    num_results = request.get("num_results", 20)  # Par défaut 20 résultats
    min_score = request.get("min_score", 0.0)    # Score minimum de pertinence
    
    if not query:
        return {"error": "Query required"}
    
    start_time = time.time()
    
    # 1. Recherche sémantique optimisée avec filtrage
    docs = search_geocat_optimized(query, num_results, min_score)
    search_time = time.time() - start_time
    
    # 2. Génération avec contexte optimisée
    try:
        generation_start = time.time()
        response = generate_response_optimized(query, docs)
        generation_time = time.time() - generation_start
        total_time = time.time() - start_time
        
        return {
            "query": query,
            "response": response,
            "sources": docs,
            "status": "success",
            "performance": {
                "search_time": round(search_time, 2),
                "generation_time": round(generation_time, 2), 
                "total_time": round(total_time, 2)
            }
        }
    except Exception as e:
        # Si la génération échoue, on retourne quand même les sources
        return {
            "query": query,
            "response": f"La génération a échoué ({str(e)}), mais voici les sources trouvées :",
            "sources": docs,
            "status": "partial_success",
            "performance": {
                "search_time": round(search_time, 2),
                "total_time": round(time.time() - start_time, 2)
            }
        }

@app.get("/search")
def search(query: str, num_results: int = 20, min_score: float = 0.0):
    """Recherche vectorielle rapide avec filtrage par pertinence"""
    docs = search_geocat_optimized(query, num_results, min_score)
    return {"results": docs}

@app.get("/search-fast")
def search_fast(query: str):
    """Recherche ultra-rapide (vectoriel uniquement, pas de génération)"""
    vec = get_embedding(query)
    resp = es.search(
        index="geonetwork",
        size=20,
        _source=["uuid", "title", "abstract"],  # Pas d'embedding pour économiser la bande passante
        timeout="5s",
        query={
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                    "params": {"query_vector": vec}
                }
            }
        }
    )
    return {"results": [hit["_source"] for hit in resp["hits"]["hits"]]}

@app.get("/health")
def health():
    """Health check avec stats de cache"""
    return {
        "status": "healthy",
        "cache_stats": {
            "embedding_cache_size": len(embedding_cache),
            "response_cache_size": len(response_cache)
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
