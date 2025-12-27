import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pptx import Presentation
import json
import os
import re

# --- ID PREDEFINITI (I TUOI) ---
DEFAULT_TEMPLATE_ID = "1BHac-ciWsMCxjtNrv8RxB68LyDi9cZrV6VMWEeXCw5A"
DEFAULT_FOLDER_ID = "1GGDGFQjAqck9Tdo30EZiLEo3CVJOlUKX"

# --- CONFIGURAZIONE ---
st.set_page_config(page_title="Slide Monster ITA", page_icon="🇮🇹", layout="wide")

# --- LOGIN ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    
    # Gestione sicura del Service Account
    if "gcp_service_account" in st.secrets and "json_content" in st.secrets["gcp_service_account"]:
        json_str = st.secrets["gcp_service_account"]["json_content"]
        service_account_info = json.loads(json_str)
    else:
        service_account_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/presentations']
    )
    drive_service = build('drive', 'v3', credentials=creds)
    slides_service = build('slides', 'v1', credentials=creds)

except Exception as e:
    st.error(f"⚠️ Errore Secrets: {e}")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("🧠 Configurazione ITA")
    # Cerchiamo di usare il modello Pro se c'è, altrimenti Flash
    models_list = ["models/gemini-1.5-pro-latest", "models/gemini-1.5-flash"]
    selected_gemini = st.selectbox("Modello AI", models_list, index=0)
    
    st.divider()
    st.header("🎨 Immagini")
    image_style = st.selectbox("Stile", ["Fotorealistico", "Illustrazione 3D", "Disegno"], index=0)

# --- FUNZIONI ---

def clean_json_text(text):
    """
    Pulisce la risposta dell'AI da eventuali caratteri markdown (```json ... ```)
    che causano l'errore 'JSON vuoto' o 'Decode error'.
    """
    text = text.strip()
    # Rimuove i blocchi markdown ```json e ```
    if text.startswith("```"):
        text = re.sub(r"^```(json)?", "", text, flags=re.MULTILINE)
        text = re.sub(r"```$", "", text, flags=re.MULTILINE)
    return text.strip()

def extract_text_from_pptx(file_obj):
    prs = Presentation(file_obj)
    full_text = []
    for slide in prs.slides:
        s_txt = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                s_txt.append(shape.text.strip())
        full_text.append(" | ".join(s_txt))
    return "\n---\n".join(full_text)

def brain_process(text, model, style):
    # Prompt ottimizzato per ITALIANO
    style_prompt = "photorealistic, cinematic lighting, 8k"
    if style == "Illustrazione 3D": style_prompt = "3d render, clay style, clean background"
    
    prompt = f"""
    Sei un Senior Copywriter italiano. Riscrivi i contenuti di questa presentazione.
    
    INPUT: Testo grezzo estratto da slide.
    OUTPUT: JSON per riempire un template (Cover + 5 slide).
    
    REGOLE:
    1. SCRIVI SOLO IN ITALIANO (Testi slide).
    2. Migliora il tono: rendilo professionale, energico e sintetico.
    3. Cover: Il sottotitolo deve essere uno slogan di marketing.
    4. Image Prompts: Scrivi le descrizioni delle immagini in INGLESE (per il generatore grafico).
       Stile immagini: {style_prompt}.
    
    STRUTTURA JSON TASSATIVA:
    {{
        "cover": {{ "title": "Titolo", "subtitle": "Slogan", "image_prompt": "..." }},
        "slides": [
            {{ "id": 1, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 2, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 3, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 4, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 5, "title": "...", "body": "...", "image_prompt": "..." }}
        ]
    }}
    """
    
    ai = genai.GenerativeModel(model)
    try:
        # Chiediamo esplicitamente JSON mode, ma puliamo comunque dopo per sicurezza
        resp = ai.generate_content(
            f"{prompt}\n\nTESTO SORGENTE:\n{text}", 
            generation_config={"response_mime_type": "application/json"}
        )
        
        # DEBUG: Se la risposta è vuota o bloccata
        if not resp.text:
            st.error("L'AI ha restituito una risposta vuota (forse bloccata dai filtri di sicurezza).")
            return None
            
        cleaned_text = clean_json_text(resp.text)
        return json.loads(cleaned_text)
        
    except Exception as e:
        st.error(f"Errore Interpretazione AI: {e}")
        # Mostriamo il testo grezzo per capire cosa è successo
        with st.expander("Vedi risposta grezza dell'AI (Debug)"):
            st.code(resp.text if 'resp' in locals() else "Nessuna risposta")
        return None

def generate_image_url(prompt):
    # Usa Flux via Pollinations
    clean_prompt = prompt.replace(' ', '%20')
    seed = os.urandom(2).hex()
    return f"[https://image.pollinations.ai/prompt/](https://image.pollinations.ai/prompt/){clean_prompt}?width=1920&height=1080&model=flux&nologo=true&seed={seed}"

def find_image_element_id(prs_id, label):
    try:
        prs = slides_service.presentations().get(presentationId=prs_id).execute()
        for slide in prs.get('slides', []):
            for el in slide.get('pageElements', []):
                if el.get('description') == label: return el['objectId']
    except: pass
    return None

def worker_bot(template_id, folder_id, filename, ai_data):
    # 1. COPIA FILE
    try:
        file_meta = {'name': filename, 'parents': [folder_id]}
        copy = drive_service.files().copy(fileId=template_id, body=file_meta).execute()
        new_id = copy.get('id')
    except Exception as e:
        st.error(f"❌ ERRORE DRIVE: Impossibile creare il file. Controlla che 'slide-bot' sia EDITOR della cartella {folder_id}.\nErrore: {e}")
        return None
    
    # 2. SOSTITUZIONE TESTI
    reqs = []
    # Cover
    if 'cover' in ai_data:
        reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': ai_data['cover'].get('title', 'Titolo')}})
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
    if 'cover' in ai_data: img_map['IMG_COVER'] = ai_data['cover'].get('image_prompt', '')
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']): img_map[f'IMG_{i+1}'] = s.get('image_prompt', '')
        
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
st.title("🇮🇹 Slide Monster (ITA - Robust)")

col1, col2 = st.columns([1, 2])

with col1:
    st.info("Configurazione Attiva")
    tmpl = st.text_input("ID Template", value=DEFAULT_TEMPLATE_ID)
    fold = st.text_input("ID Cartella", value=DEFAULT_FOLDER_ID)

with col2:
    uploaded = st.file_uploader("Carica PPT (Genera file _ITA)", accept_multiple_files=True, type=['pptx'])
    
    if st.button("🚀 ELABORA (Versione Italiana)", type="primary"):
        if not uploaded:
            st.warning("Carica i file!")
        else:
            bar = st.progress(0)
            log_box = st.container()
            
            for i, f in enumerate(uploaded):
                # Nome file finale: Originale + _ITA
                fname = f.name.replace(".pptx", "") + "_ITA"
                
                with log_box:
                    st.write(f"▶️ **{fname}**: Analisi in corso...")
                
                try:
                    # 1. Estrazione
                    txt = extract_text_from_pptx(f)
                    
                    # 2. AI
                    data = brain_process(txt, selected_gemini, image_style)
                    
                    if data:
                        # 3. Drive
                        res_id = worker_bot(tmpl, fold, fname, data)
                        if res_id:
                            st.toast(f"✅ Fatto: {fname}")
                            with log_box:
                                st.success(f"✅ **{fname}** salvato su Drive!")
                        else:
                            with log_box:
                                st.error(f"❌ Errore salvataggio {fname}")
                    else:
                        with log_box:
                            st.error(f"❌ Errore AI su {fname} (Vedi dettagli sopra)")
                            
                except Exception as e:
                    st.error(f"Errore Critico: {e}")
                
                bar.progress((i+1)/len(uploaded))
            
            st.success("Tutto finito!")
