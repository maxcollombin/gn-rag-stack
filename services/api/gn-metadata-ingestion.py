import requests
import time
import json
import os
from elasticsearch import Elasticsearch
from sentence_transformers import SentenceTransformer

# Chargement des configurations
def load_config():
    config_dir = "/app/config" if os.path.exists("/app/config") else "../../config"
    
    # Configuration principale
    with open(os.path.join(config_dir, "geonetwork-config.json"), 'r') as f:
        main_config = json.load(f)
    
    # Configuration de la requête
    with open(os.path.join(config_dir, "search-query.json"), 'r') as f:
        query_config = json.load(f)
    
    return main_config, query_config

# Chargement des configurations
MAIN_CONFIG, QUERY_CONFIG = load_config()

# Configuration extraite des fichiers
GEONETWORK_URL = MAIN_CONFIG["geonetwork"]["base_url"] + MAIN_CONFIG["geonetwork"]["search_endpoint"]
ES_INDEX = MAIN_CONFIG["elasticsearch"]["index_name"]
REQUEST_DELAY = MAIN_CONFIG["ingestion"]["request_delay"]
BATCH_SIZE = MAIN_CONFIG["ingestion"]["batch_size"]
TIMEOUT = MAIN_CONFIG["ingestion"]["timeout"]

# Headers respectueux pour identifier notre client
HEADERS = {
    'User-Agent': MAIN_CONFIG["geonetwork"]["user_agent"],
    'Content-Type': 'application/json'
}

es = Elasticsearch("http://elasticsearch:9200")
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

def create_index():
    try:
        # Vérifier si l'index existe déjà
        response = es.cat.indices(index=ES_INDEX, format="json")
        if response:
            print(f"L'index {ES_INDEX} existe déjà")
            return
    except:
        # L'index n'existe pas, on va le créer
        pass
    
    try:
        es.indices.create(
            index=ES_INDEX,
            mappings={
                "properties": {
                    "uuid": {"type": "keyword"},
                    "title": {"type": "text"},
                    "abstract": {"type": "text"},
                    "embedding": {"type": "dense_vector", "dims": 384}
                }
            }
        )
        print(f"Index {ES_INDEX} créé avec succès")
    except Exception as e:
        print(f"Erreur lors de la création de l'index: {e}")

def data_ingestion():
    """
    Ingestion des métadonnées GeoNetwork avec pagination et délais
    """
    print(f"Démarrage de l'ingestion des métadonnées - {MAIN_CONFIG['geonetwork']['name']}...")

    # Configuration pour être respectueux du serveur
    total_processed = 0
    batch_start = 0
    
    while True:
        # Construction de la requête basée sur le template
        body = QUERY_CONFIG["query_template"].copy()
        body["from"] = batch_start
        body["size"] = BATCH_SIZE

        print(f"Requête batch {batch_start//BATCH_SIZE + 1}: récupération de {BATCH_SIZE} enregistrements à partir de {batch_start}...")
        
        try:
            resp = requests.post(GEONETWORK_URL, json=body, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            
            hits = data.get("hits", {}).get("hits", [])
            total = data.get("hits", {}).get("total", {})
            if isinstance(total, dict):
                total_count = total.get("value", 0)
            else:
                total_count = total
                
            print(f"Nombre total de résultats disponibles : {total_count}")
            print(f"Reçu {len(hits)} enregistrements dans ce batch")
            
            if not hits:
                print("Aucun enregistrement supplémentaire trouvé. Fin de l'ingestion.")
                break
            
            # Traitement des enregistrements reçus
            batch_indexed = 0
            for i, hit in enumerate(hits):
                source = hit.get("_source", {})
                
                # Extraction des champs basée sur le mapping
                field_mapping = QUERY_CONFIG["field_mapping"]
                uuid = source.get(field_mapping["uuid"], "")
                
                # Extraction du titre avec gestion des objets imbriqués
                title_path = field_mapping["title"].split(".")
                title = source
                for part in title_path:
                    title = title.get(part, {}) if isinstance(title, dict) else ""
                title = title if isinstance(title, str) else ""
                
                # Extraction du résumé/abstract avec gestion des objets imbriqués
                abstract_path = field_mapping["abstract"].split(".")
                abstract = source
                for part in abstract_path:
                    abstract = abstract.get(part, {}) if isinstance(abstract, dict) else ""
                abstract = abstract if isinstance(abstract, str) else ""
                
                text = f"{title} {abstract}".strip()
                
                if text and uuid:  # S'assurer qu'on a du contenu et un UUID
                    print(f"  Indexation {batch_start + i + 1}: {title[:50]}...")
                    
                    try:
                        vec = model.encode(text).tolist()
                        
                        clean_doc = {
                            "uuid": uuid,
                            "title": title,
                            "abstract": abstract,
                            "embedding": vec
                        }
                        
                        es.index(index=ES_INDEX, document=clean_doc)
                        batch_indexed += 1
                        total_processed += 1
                        
                    except Exception as e:
                        print(f"  Erreur lors de l'indexation de {uuid}: {e}")
                        continue
                else:
                    print(f"  Ignoré (pas de contenu ou UUID manquant)")
            
            print(f"Batch terminé : {batch_indexed} enregistrements indexés")
            
            # Vérifier si on a traité tous les enregistrements
            if batch_start + len(hits) >= total_count:
                print("Tous les enregistrements ont été traités.")
                break
                
            # Préparer le batch suivant
            batch_start += BATCH_SIZE
            
            # Délai avant la prochaine requête
            print(f"Pause de {REQUEST_DELAY} secondes...")
            time.sleep(REQUEST_DELAY)
            
        except requests.exceptions.RequestException as e:
            print(f"Erreur lors de la requête HTTP : {e}")
            print("Arrêt de l'ingestion.")
            break
        except Exception as e:
            print(f"Erreur lors du traitement : {e}")
            print("Arrêt de l'ingestion.")
            break
    
    print(f"Ingestion terminée. {total_processed} enregistrements indexés au total.")

if __name__ == "__main__":
    print("Ingestion des métadonnées GeoNetwork")
    print("Caractéristiques :")
    print(f"- Traitement par lots de {BATCH_SIZE} enregistrements")
    print(f"- Délai de {REQUEST_DELAY} secondes entre les requêtes")
    print("- Headers User-Agent")
    
    create_index()
    data_ingestion()
    print("Fin de l'ingestion des métadonnées GeoNetwork")
