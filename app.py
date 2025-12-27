import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pptx import Presentation
import json
import os

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Slide Monster Agent", page_icon="🦖", layout="wide")

# --- LOGIN SICURO (FIX DEFINITIVO) ---
try:
    # 1. Configura Gemini
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    
    # 2. Configura Google Drive & Slides
    # Qui sta la modifica: legge la nuova struttura sicura del secrets.toml
    if "gcp_service_account" in st.secrets and "json_content" in st.secrets["gcp_service_account"]:
        # Caso Nuovo (Sicuro)
        json_str = st.secrets["gcp_service_account"]["json_content"]
        service_account_info = json.loads(json_str)
    else:
        # Caso Vecchio (Fallback, se dovesse servire)
        service_account_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/presentations']
    )
    drive_service = build('drive', 'v3', credentials=creds)
    slides_service = build('slides', 'v1', credentials=creds)

except Exception as e:
    st.error(f"⚠️ Errore Configurazione Secrets: {e}")
    st.warning("Controlla che in .streamlit/secrets.toml ci sia la sezione [gcp_service_account]")
    st.stop()

# --- FUNZIONI DEL MOSTRO ---

def extract_text_from_pptx(file_obj):
    """Legge il testo dai vecchi PPT caricati"""
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
    """Gemini: Traduce e crea il JSON per il Template"""
    prompt = """
    Sei un Senior Editor. Trasforma questa presentazione grezza in un format inglese perfetto.
    
    INPUT: Testo vecchia presentazione.
    OUTPUT: JSON per 6 SLIDE (1 Cover + 5 Content).
    
    REGOLE:
    1. Traduci in INGLESE (US).
    2. Cover: Sottotitolo = slogan breve.
    3. Slide 1-5: Sintetizza i punti chiave.
    4. Image Prompts: Descrizione visiva in inglese.
    
    JSON ESATTO:
    {
        "cover": { "title": "...", "subtitle": "...", "image_prompt": "..." },
        "slides": [
            { "id": 1, "title": "...", "body": "...", "image_prompt": "..." },
            { "id": 2, "title": "...", "body": "...", "image_prompt": "..." },
            { "id": 3, "title": "...", "body": "...", "image_prompt": "..." },
            { "id": 4, "title": "...", "body": "...", "image_prompt": "..." },
            { "id": 5, "title": "...", "body": "...", "image_prompt": "..." }
        ]
    }
    """
    model = genai.GenerativeModel("gemini-1.5-flash")
    try:
        resp = model.generate_content(f"{prompt}\n\nTESTO:\n{text}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except: return None

def generate_image_url(prompt):
    """URL immagine AI (Pollinations)"""
    return f"https://image.pollinations.ai/prompt/{prompt.replace(' ', '%20')}?width=1920&height=1080&nologo=true"

def find_image_element_id(prs_id, label):
    """Trova ID immagine nel template tramite Alt Text"""
    try:
        prs = slides_service.presentations().get(presentationId=prs_id).execute()
        for slide in prs.get('slides', []):
            for el in slide.get('pageElements', []):
                if el.get('description') == label: return el['objectId']
    except: pass
    return None

def worker_bot(template_id, folder_id, filename, ai_data):
    """Clona il template esistente e lo compila"""
    
    # 1. COPIA IL TEMPLATE GIÀ PRONTO SU DRIVE
    try:
        copy = drive_service.files().copy(
            fileId=template_id, 
            body={'name': filename, 'parents': [folder_id]}
        ).execute()
        new_id = copy.get('id')
    except Exception as e:
        st.error(f"Errore copia file (Controlla che il Service Account abbia accesso alla cartella e al template!): {e}")
        return None
    
    # 2. TESTI
    reqs = []
    # Cover
    if 'cover' in ai_data:
        reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': ai_data['cover'].get('title', '')}})
        reqs.append({'replaceAllText': {'containsText': {'text': '{{SUBTITLE}}'}, 'replaceText': ai_data['cover'].get('subtitle', '')}})
    
    # Slides
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']):
            idx = i + 1
            reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{TITLE_{idx}}}}}'}, 'replaceText': s.get('title', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{BODY_{idx}}}}}'}, 'replaceText': s.get('body', '')}})
    
    if reqs: 
        slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs}).execute()

    # 3. IMMAGINI
    reqs_img = []
    img_map = {}
    if 'cover' in ai_data:
        img_map['IMG_COVER'] = ai_data['cover'].get('image_prompt', '')
    
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']): 
            img_map[f'IMG_{i+1}'] = s.get('image_prompt', '')
    
    for label, prompt in img_map.items():
        if prompt:
            el_id = find_image_element_id(new_id, label)
            if el_id:
                reqs_img.append({
                    'replaceImage': {
                        'imageObjectId': el_id,
                        'imageReplaceMethod': 'CENTER_CROP',
                        'url': generate_image_url(prompt)
                    }
                })
            
    if reqs_img: 
        slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs_img}).execute()
        
    return new_id

# --- INTERFACCIA ---
st.title("🦖 Slide Monster (Google Native)")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. Configurazione Drive")
    st.info("Incolla qui gli ID presi dagli URL di Drive")
    
    template_id = st.text_input("ID Template Google Slide", placeholder="es. 1AbCdEfG...")
    folder_id = st.text_input("ID Cartella Output", placeholder="es. 1XyZ...")

with col2:
    st.subheader("2. Carica i vecchi PPT")
    files = st.file_uploader("Trascina qui i PPTX da convertire", accept_multiple_files=True, type=['pptx'])
    
    if st.button("🔥 ATTIVA IL MOSTRO", type="primary"):
        if not files or not folder_id or not template_id:
            st.warning("Mancano ID Template, ID Cartella o i File!")
        else:
            bar = st.progress(0)
            status = st.empty()
            
            for i, f in enumerate(files):
                fname = f.name.replace(".pptx", "") + "_ENG"
                status.write(f"⚙️ Lavoro su: **{fname}**...")
                
                try:
                    # Estrazione
                    txt = extract_text_from_pptx(f)
                    # AI
                    data = brain_process(txt)
                    
                    if data:
                        # Qui usiamo il template_id che hai incollato
                        new_id = worker_bot(template_id, folder_id, fname, data)
                        if new_id:
                            st.toast(f"Fatto: {fname}")
                        else:
                            st.error(f"Errore generazione su {fname}")
                except Exception as e:
                    st.error(f"Errore critico su {fname}: {e}")
                
                bar.progress((i+1)/len(files))
            
            st.balloons()
            st.success("Tutto completato! Controlla Google Drive.")
