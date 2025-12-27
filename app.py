import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pptx import Presentation
import json
import os
import time

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Slide Monster Agent", page_icon="🦖", layout="wide")

# --- RECUPERO CREDENZIALI (SECRETS) ---
# Assicurati che nel file .streamlit/secrets.toml ci siano GOOGLE_API_KEY e GCP_SERVICE_ACCOUNT
try:
    # 1. Configura Gemini
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    
    # 2. Configura Google Drive & Slides
    service_account_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=[
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/presentations'
        ]
    )
    drive_service = build('drive', 'v3', credentials=creds)
    slides_service = build('slides', 'v1', credentials=creds)

except Exception as e:
    st.error(f"⚠️ Errore nei Secrets: {e}")
    st.stop()

# --- FUNZIONI DEL MOSTRO ---

def extract_text_from_pptx(file_obj):
    """Legge il testo brutale dal file PPTX caricato"""
    prs = Presentation(file_obj)
    full_text = []
    for slide in prs.slides:
        slide_text = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                slide_text.append(shape.text.strip())
        full_text.append(" | ".join(slide_text))
    return "\n---\n".join(full_text)

def brain_process(text):
    """Il cervello: Traduce, Riassume e Genera Prompt Immagini"""
    
    # Istruzioni precise per 1 Cover + 5 Slide (totale 6 editabili)
    prompt = """
    Sei un Senior Editor. Il tuo compito è trasformare una presentazione grezza in un format inglese perfetto.
    
    INPUT: Testo di una vecchia presentazione italiana.
    OUTPUT: Un JSON strutturato per 6 SLIDE (1 Cover + 5 Content).
    
    REGOLE:
    1. Traduci tutto in INGLESE (English US).
    2. Sottotitolo della Cover: deve essere uno slogan di marketing (max 10 parole).
    3. Slide Content (da 1 a 5): Sintetizza i concetti chiave.
    4. Image Prompts: Scrivi una descrizione visiva in inglese per generare l'immagine (es. "Cinematic photo of a team building a raft...").
    
    STRUTTURA JSON ESATTA:
    {
        "cover": {
            "title": "Titolo del Format",
            "subtitle": "Slogan breve",
            "image_prompt": "descrizione cover..."
        },
        "slides": [
            { "id": 1, "title": "...", "body": "...", "image_prompt": "..." },
            { "id": 2, "title": "...", "body": "...", "image_prompt": "..." },
            { "id": 3, "title": "...", "body": "...", "image_prompt": "..." },
            { "id": 4, "title": "...", "body": "...", "image_prompt": "..." },
            { "id": 5, "title": "...", "body": "...", "image_prompt": "..." }
        ]
    }
    """
    
    model = genai.GenerativeModel("gemini-1.5-flash") # Veloce ed economico
    try:
        response = model.generate_content(
            f"{prompt}\n\nMATERIALE SORGENTE:\n{text}",
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        st.error(f"Errore AI: {e}")
        return None

def find_image_element_id(presentation_id, alt_text_label):
    """Cerca nella presentazione l'ID dell'immagine che ha una certa etichetta (Alt Text)"""
    prs = slides_service.presentations().get(presentationId=presentation_id).execute()
    
    for slide in prs.get('slides', []):
        for element in slide.get('pageElements', []):
            # Controlla se l'elemento ha una descrizione (Alt Text) che corrisponde
            if 'description' in element and element['description'] == alt_text_label:
                return element['objectId']
    return None

def generate_image_url(prompt):
    """
    TRUCCO: Usa Pollinations.ai per generare immagini al volo tramite URL.
    Non richiede chiavi API e funziona per le slide!
    """
    clean_prompt = prompt.replace(" ", "%20")
    # Aggiungiamo un seed casuale per variare
    return f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1920&height=1080&nologo=true"

def worker_bot(template_id, folder_id, filename, ai_data):
    """L'operaio che assembla la slide su Drive"""
    
    # 1. COPIA IL TEMPLATE
    file_meta = {'name': filename, 'parents': [folder_id]}
    copy = drive_service.files().copy(fileId=template_id, body=file_meta).execute()
    new_prs_id = copy.get('id')
    
    requests = []
    
    # --- A. SOSTITUZIONE TESTI (Global replace) ---
    # COVER
    requests.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': ai_data['cover']['title']}})
    requests.append({'replaceAllText': {'containsText': {'text': '{{SUBTITLE}}'}, 'replaceText': ai_data['cover']['subtitle']}})
    
    # SLIDES 1-5
    for i, s in enumerate(ai_data['slides']):
        idx = i + 1 # 1 a 5
        # Titoli e Corpi
        requests.append({'replaceAllText': {'containsText': {'text': f'{{{{TITLE_{idx}}}}}'}, 'replaceText': s['title']}})
        requests.append({'replaceAllText': {'containsText': {'text': f'{{{{BODY_{idx}}}}}'}, 'replaceText': s['body']}})

    # Eseguiamo prima i testi
    if requests:
        slides_service.presentations().batchUpdate(presentationId=new_prs_id, body={'requests': requests}).execute()
        requests = [] # Puliamo per le immagini

    # --- B. SOSTITUZIONE IMMAGINI (Chirurgica) ---
    # Mappa delle sostituzioni: Etichetta -> Prompt
    image_map = { 'IMG_COVER': ai_data['cover']['image_prompt'] }
    for i, s in enumerate(ai_data['slides']):
        image_map[f'IMG_{i+1}'] = s['image_prompt']
        
    for label, prompt in image_map.items():
        # 1. Trova l'ID dell'immagine nel template che ha quell'etichetta
        element_id = find_image_element_id(new_prs_id, label)
        
        if element_id:
            # 2. Genera l'URL dell'immagine AI
            img_url = generate_image_url(prompt)
            
            # 3. Prepara la richiesta di sostituzione
            requests.append({
                'replaceImage': {
                    'imageObjectId': element_id,
                    'imageReplaceMethod': 'CENTER_CROP',
                    'url': img_url
                }
            })
    
    # Eseguiamo le immagini (se ce ne sono)
    if requests:
        slides_service.presentations().batchUpdate(presentationId=new_prs_id, body={'requests': requests}).execute()

    return new_prs_id

# --- INTERFACCIA GRAFICA ---

st.title("🦖 Slide Monster Agent")
st.markdown("### Il distruttore di PPT vecchi")
st.info("Logica: Aggiorna Slide 1-6. Ignora Slide 7-10. Genera testi in Inglese e Immagini AI.")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("⚙️ Setup")
    tmpl_id = st.text_input("ID Template Google Slide", placeholder="Copia l'ID dall'URL del template")
    dest_id = st.text_input("ID Cartella Drive Output", placeholder="ID della cartella dove salvare")
    st.markdown("---")
    st.markdown("**Controlla le Etichette nel Template:**")
    st.code("Cover: {{TITLE}}, {{SUBTITLE}}, IMG_COVER\nSlide 2: {{TITLE_1}}, {{BODY_1}}, IMG_1\n...\nSlide 6: {{TITLE_5}}, {{BODY_5}}, IMG_5")

with col2:
    st.subheader("📂 Caricamento (Batch)")
    files = st.file_uploader("Trascina qui i tuoi PPT (anche 50 alla volta)", accept_multiple_files=True, type=['pptx'])

    if st.button("🔥 ATTIVA IL MOSTRO", type="primary"):
        if not files or not tmpl_id or not dest_id:
            st.warning("Mancano dei dati (File, ID Template o ID Cartella).")
        else:
            bar = st.progress(0)
            logs = st.container()
            
            for i, f in enumerate(files):
                filename = f.name
                clean_name = os.path.splitext(filename)[0] + "_ENG"
                
                with logs:
                    st.write(f"**[{i+1}/{len(files)}]** Elaborazione: `{filename}`...")
                
                # 1. Estrazione
                text = extract_text_from_pptx(f)
                
                # 2. AI Brain
                ai_data = brain_process(text)
                if not ai_data:
                    st.error(f"Fallito: {filename}")
                    continue
                
                # 3. Drive Worker
                try:
                    res_id = worker_bot(tmpl_id, dest_id, clean_name, ai_data)
                    st.success(f"✅ Completato: {clean_name}")
                except Exception as e:
                    st.error(f"❌ Errore API Drive su {filename}: {e}")
                
                bar.progress((i + 1) / len(files))
            
            st.balloons()
            st.success("Tutto finito! Controlla la cartella su Drive.")
