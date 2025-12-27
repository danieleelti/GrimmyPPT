import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pptx import Presentation
import json
import os
import re
import time

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Slide Monster Enterprise", page_icon="🏢", layout="wide")

# --- I TUOI NUOVI ID (DRIVE CONDIVISO) ---
DEFAULT_TEMPLATE_ID = "1BHac-ciWsMCxjtNrv8RxB68LyDi9cZrV6VMWEeXCw5A" 
DEFAULT_FOLDER_ID = "1wL1oxos7ISS03GzfW0db44XoAk3UocV0"

# --- LOGIN ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    
    if "gcp_service_account" in st.secrets and "json_content" in st.secrets["gcp_service_account"]:
        json_str = st.secrets["gcp_service_account"]["json_content"]
        service_account_info = json.loads(json_str)
    else:
        service_account_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/drive', 'https://www.googleapis.com/auth/presentations']
    )
    # Drive v3 è obbligatorio per i Drive Condivisi
    drive_service = build('drive', 'v3', credentials=creds)
    slides_service = build('slides', 'v1', credentials=creds)

except Exception as e:
    st.error(f"⚠️ Errore Secrets: {e}")
    st.stop()

# --- SIDEBAR ---
with st.sidebar:
    st.header("🧠 Configurazione")
    
    # Lista Modelli (Gemini 3 in cima)
    models = ["models/gemini-3-pro-preview", "models/gemini-1.5-pro", "models/gemini-1.5-flash"]
    selected_gemini = st.selectbox("Modello Attivo", models, index=0)
    
    st.divider()
    
    # Stili immagine
    image_style = st.selectbox(
        "Stile Immagini", 
        ["Imagen 4 (High Fidelity)", "Flux Realism", "Illustrazione 3D"], 
        index=0
    )

# --- FUNZIONI ---

def clean_json_text(text):
    text = text.strip()
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

def brain_process(text, model_name, style):
    style_prompt = "photorealistic, cinematic lighting, 8k"
    if "Imagen 4" in style:
        style_prompt = "award winning photography, Imagen 4 style, hyper-realistic, 8k resolution"
    elif "3D" in style: 
        style_prompt = "3d render, clay style, clean background"
    
    prompt = f"""
    Sei un Senior Copywriter italiano. Riscrivi i contenuti di questa presentazione.
    INPUT: Testo grezzo estratto da slide.
    OUTPUT: JSON per riempire un template (Cover + 5 slide).
    REGOLE: SCRIVI SOLO IN ITALIANO. Cover: Sottotitolo = slogan.
    Image Prompts: Descrizioni in INGLESE. Stile: {style_prompt}.
    STRUTTURA JSON:
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
    
    ai = genai.GenerativeModel(model_name)
    try:
        resp = ai.generate_content(f"{prompt}\n\nTESTO:\n{text}", generation_config={"response_mime_type": "application/json"})
        if not resp.text: return None
        return json.loads(clean_json_text(resp.text))
    except Exception as e:
        st.error(f"Errore Modello ({model_name}): {e}")
        return None

def generate_image_url(prompt, style_choice):
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

def worker_bot(template_id, folder_id, filename, ai_data, style_choice):
    try:
        # COPIA FILE: Qui avviene la magia del Drive Condiviso
        file_body = {'name': filename, 'parents': [folder_id]}
        
        copy = drive_service.files().copy(
            fileId=template_id, 
            body=file_body, 
            supportsAllDrives=True  # <--- QUESTO RISOLVE IL PROBLEMA DI QUOTA
        ).execute()
        
        new_id = copy.get('id')
        
    except Exception as e:
        err = str(e)
        if "storageQuotaExceeded" in err:
            st.error("❌ ERRORE QUOTA: Anche nel Drive Condiviso? Assicurati che il robot sia 'Gestore dei contenuti' e non solo 'Collaboratore'.")
        else:
            st.error(f"❌ Errore Drive Copy: {e}")
        return None
    
    # DA QUI IN POI, IL FILE ESISTE ED È MODIFICABILE
    reqs = []
    if 'cover' in ai_data:
        reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': ai_data['cover'].get('title', 'Titolo')}})
        reqs.append({'replaceAllText': {'containsText': {'text': '{{SUBTITLE}}'}, 'replaceText': ai_data['cover'].get('subtitle', '')}})
    
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']):
            idx = i + 1
            reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{TITLE_{idx}}}}}'}, 'replaceText': s.get('title', '')}})
            reqs.append({'replaceAllText': {'containsText': {'text': f'{{{{BODY_{idx}}}}}'}, 'replaceText': s.get('body', '')}})
            
    # Eseguiamo prima i testi per non mischiare le richieste
    if reqs:
        try:
            slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs}).execute()
        except Exception as e:
             st.warning(f"⚠️ Errore minore nei testi: {e}")

    # --- GESTIONE IMMAGINI CON CONTROLLO DI SICUREZZA ---
    reqs_img = []
    img_map = {}
    if 'cover' in ai_data: img_map['IMG_COVER'] = ai_data['cover'].get('image_prompt', '')
    if 'slides' in ai_data:
        for i, s in enumerate(ai_data['slides']): img_map[f'IMG_{i+1}'] = s.get('image_prompt', '')
        
    for label, prompt in img_map.items():
        if prompt and prompt.strip():
            el_id = find_image_element_id(new_id, label)
            if el_id:
                # 1. Genera l'URL
                url = generate_image_url(prompt, style_choice)
                
                # 2. CONTROLLO DI SICUREZZA: L'URL è valido? (Evita Errore 400)
                # Se l'URL è vuoto o non inizia con http/https, Google si blocca.
                if url and url.strip().startswith(('http://', 'https://')):
                    reqs_img.append({
                        'replaceImage': {
                            'imageObjectId': el_id,
                            'imageReplaceMethod': 'CENTER_CROP',
                            'url': url
                        }
                    })
                else:
                    # Se l'URL è rotto, saltiamo questa immagine ma non blocchiamo tutto.
                    # (Opzionale: potremmo aggiungere un toast qui)
                    pass 

    # Eseguiamo le immagini valide
    if reqs_img:
        try:
            # Breve pausa per non sovraccaricare l'API delle immagini
            time.sleep(1) 
            slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs_img}).execute()
        except Exception as e:
             st.error(f"❌ Errore inserimento immagini (Google ha rifiutato anche gli URL validi): {e}")
        
    return new_id

# --- INTERFACCIA ---
st.title("🦖 Slide Monster (Shared Drive)")
st.caption("Versione ottimizzata per Drive Condivisi Aziendali con controllo URL")

col1, col2 = st.columns([1, 2])
with col1:
    st.info("Configurazione Attiva")
    tmpl = st.text_input("ID Template", value=DEFAULT_TEMPLATE_ID)
    fold = st.text_input("ID Cartella Output", value=DEFAULT_FOLDER_ID)
    st.success(f"🤖 Brain: {selected_gemini}")

with col2:
    uploaded = st.file_uploader("Carica PPT", accept_multiple_files=True, type=['pptx'])
    if st.button("🚀 ELABORA (ITA)", type="primary"):
        if uploaded:
            bar = st.progress(0)
            log = st.container()
            for i, f in enumerate(uploaded):
                fname = f.name.replace(".pptx", "") + "_ITA"
                try:
                    txt = extract_text_from_pptx(f)
                    
                    with log: st.write(f"🧠 Analisi **{fname}**...")
                    data = brain_process(txt, selected_gemini, image_style)
                    
                    if data:
                        with log: st.write(f"💾 Salvataggio e generazione immagini...")
                        res = worker_bot(tmpl, fold, fname, data, image_style)
                        if res: 
                            st.toast(f"✅ Fatto: {fname}")
                            log.success(f"✅ Completato: {fname}")
                    else:
                        log.error(f"Errore AI su {fname}")
                except Exception as e:
                    log.error(f"Critico: {e}")
                bar.progress((i+1)/len(uploaded))
            st.success("Tutto finito!")
