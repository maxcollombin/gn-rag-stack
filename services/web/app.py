import gradio as gr
import requests
import json
import os

# Chargement de la configuration
def load_config():
    """Charger la configuration GeoNetwork"""
    config_path = "/app/config/geonetwork-config.json"
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    else:
        # Configuration par défaut
        return {
            "geonetwork": {
                "name": "GeoNetwork",
                "base_url": "https://www.geocat.ch/geonetwork"
            }
        }

CONFIG = load_config()
GEONETWORK_NAME = CONFIG["geonetwork"]["name"]
GEONETWORK_BASE_URL = CONFIG["geonetwork"]["base_url"]

def rag_search(query, min_score=0.0):
    """Fonction de recherche RAG avec indicateurs de statut et filtrage par pertinence"""
    if not query:
        return "Veuillez saisir une question", gr.update(visible=False), gr.update(value=[], visible=False), gr.update()
    
    try:
        # Phase 1: Recherche sémantique
        initial_status = "**Recherche en cours...**\n\n"
        initial_status += "Recherche sémantique dans la base de métadonnées"
        
        response = requests.post(
            "http://api:8000/rag",
            json={
                "query": query,
                "min_score": min_score  # Ajout du filtrage par score
            },
            timeout=120  # Timeout augmenté à 2 minutes
        )
        
        if response.status_code == 200:
            result = response.json()
            
            # Formatage de la réponse
            answer = result["response"]
            
            # Gestion du statut
            if result.get("status") == "partial_success":
                answer = answer
            
            # Calcul du score maximum des résultats pour adapter le slider
            max_score = 0.0
            if result["sources"]:
                max_score = max(source.get('relevance_score', 0) for source in result["sources"])
                # Arrondir vers le haut pour avoir une valeur propre
                max_score = round(max_score + 0.5, 1)
            
            # Formatage des sources sous forme de tableau
            sources_data = []
            for i, source in enumerate(result["sources"][:15], 1):  # Afficher jusqu'à 15 sources
                score = source.get('relevance_score', 0)
                
                # Création du lien cliquable générique
                uuid = source['uuid']
                # Construction de l'URL basée sur la configuration
                metadata_url = f"{GEONETWORK_BASE_URL.replace('/geonetwork', '')}/datahub/dataset/{uuid}"
                link = f'<a href="{metadata_url}" target="_blank" style="color: #1976d2; text-decoration: underline; cursor: pointer;">Consulter la fiche de métadonnées</a>'
                
                sources_data.append([
                    i,  # Rang
                    source['title'],  # Nom
                    link,  # Lien
                    round(score, 2)  # Score numérique seulement
                ])
            
            # Message de succès final
            final_answer = f"{answer}"
            if min_score > 0:
                final_answer += f"\n\n*Résultats filtrés avec un score minimum de {min_score}*"
            
            # Mise à jour du slider avec le score maximum trouvé
            slider_update = gr.update(maximum=max(max_score, 1.0), value=min_score)
            
            return final_answer, gr.update(visible=True), gr.update(value=sources_data, visible=True), slider_update
        else:
            error_msg = f"**Erreur HTTP {response.status_code}**"
            return error_msg, gr.update(visible=False), gr.update(value=[], visible=False), gr.update()
            
    except requests.exceptions.Timeout:
        error_msg = "**Timeout** - La recherche prend plus de 2 minutes"
        return error_msg, gr.update(visible=False), gr.update(value=[], visible=False), gr.update()
    except requests.exceptions.ConnectionError:
        error_msg = "**Erreur de connexion**"
        return error_msg, gr.update(visible=False), gr.update(value=[], visible=False), gr.update()
    except Exception as e:
        error_msg = f"**Erreur :** {e}"
        return error_msg, gr.update(visible=False), gr.update(value=[], visible=False), gr.update()

# Interface Gradio
with gr.Blocks(title=f"Recherche de géodonnées - {GEONETWORK_NAME}", theme=gr.themes.Soft()) as demo:
    gr.Markdown(f"# Recherche de géodonnées - {GEONETWORK_NAME}")
    gr.Markdown("Posez vos questions sur les géodonnées disponibles")

    query_input = gr.Textbox(
        label="Votre question",
        placeholder="Ex. Où trouver des informations sur les zones à risque naturel ?",
        lines=2
    )
    
    # Nouveau slider pour le filtrage par pertinence
    min_score_slider = gr.Slider(
        minimum=0.0,
        maximum=5.0,
        value=0.0,
        step=0.1,
        label="Score minimum de pertinence",
        info="Filtrer les résultats en fonction de leur pertinence (max adapté automatiquement)"
    )
    
    search_btn = gr.Button("Lancer la recherche", variant="primary")
    
    answer_output = gr.Markdown(label="Réponse")
    
    # Titre conditionnel pour les sources (visible seulement après recherche)
    sources_title = gr.Markdown("## Fiches de métadonnées associées", visible=False)
    
    sources_output = gr.Dataframe(
        headers=["Rang", "Nom", "Lien", "Score"],
        datatype=["number", "str", "html", "number"],
        interactive=False,
        max_height=400,
        visible=False
    )
    
    # Événements
    search_btn.click(
        fn=rag_search,
        inputs=[query_input, min_score_slider],
        outputs=[answer_output, sources_title, sources_output, min_score_slider]
    )

if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
