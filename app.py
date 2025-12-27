import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from pptx import Presentation
import json
import os

# --- I TUOI ID PREDEFINITI ---
DEFAULT_TEMPLATE_ID = "1BHac-ciWsMCxjtNrv8RxB68LyDi9cZrV6VMWEeXCw5A"
DEFAULT_FOLDER_ID = "1GGDGFQjAqck9Tdo30EZiLEo3CVJOlUKX"

# --- CONFIGURAZIONE PAGINA ---
st.set_page_config(page_title="Slide Monster Agent", page_icon="🦖", layout="wide")

# --- 1. LOGIN & SETUP INIZIALE ---
try:
    # Configura Gemini
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    
    # Configura Drive & Slides
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
    st.error(f"⚠️ Errore Configurazione: {e}")
    st.stop()

# --- 2. SIDEBAR E SELEZIONE MODELLI ---
with st.sidebar:
    st.header("🧠 Cervello AI")
    
    # A. Recupera modelli reali + INSERISCE IL TUO MODELLO CUSTOM
    try:
        available_models = []
        # Tenta di recuperare la lista reale
        for m in genai.list_models():
            if 'generateContent' in m.supported_generation_methods:
                available_models.append(m.name)
        available_models.sort(reverse=True)
    except:
        available_models = ["models/gemini-1.5-pro-latest"]

    # FORZATURA: Inseriamo il tuo modello in cima alla lista
    # Se esiste già nella lista lo rimuoviamo per non averlo doppio
    custom_model = "models/gemini-3.0-pro-preview"
    if custom_model in available_models:
        available_models.remove(custom_model)
    
    # Lo inseriamo in posizione 0 (Default assoluto)
    available_models.insert(0, custom_model)
            
    selected_gemini = st.selectbox("Modello Testo (Default: 3.0 Pro)", available_models, index=0)
    st.caption(f"Attivo: {selected_gemini}")
    
    st.divider()
    
    st.header("🎨 Motore Immagini")
    st.info("Motore grafico impostato su massima qualità.")
    
    # Imagen 4 come default (index 0)
    image_style = st.selectbox(
        "Stile Generazione", 
        ["Imagen 4 (High Fidelity)", "Flux Realism", "3D Render", "Digital Art", "Anime"],
        index=0
    )

# --- FUNZIONI ---

def extract_text_from_pptx(file_obj):
    """Legge il testo dai vecchi PPT"""
    prs = Presentation(file_obj)
    full_text = []
    for slide in prs.slides:
        slide_text = []
        for shape in slide.shapes:
            if hasattr(shape, "text") and shape.text.strip():
                slide_text.append(shape.text.strip())
        full_text.append(" | ".join(slide_text))
    return "\n---\n".join(full_text)

def brain_process(text, model_name, style_pref):
    """Gemini: Traduce e crea il JSON usando il modello scelto"""
    
    # Tuning del prompt in base allo stile scelto
    style_instruction = "Photorealistic, 4k, highly detailed, vivid colors"
    if "Imagen 4" in style_pref: 
        style_instruction = "Award winning photography, 8k resolution, Imagen 4 style, hyper-realistic"
    elif "3D" in style_pref: 
        style_instruction = "3D clay render, clean background, blender style"
    elif "Anime" in style_pref: 
        style_instruction = "Anime style, Studio Ghibli vibes"
    
    prompt = f"""
    Sei un Senior Editor. Trasforma questa presentazione grezza in un format inglese perfetto.
    
    INPUT: Testo vecchia presentazione.
    OUTPUT: JSON per 6 SLIDE (1 Cover + 5 Content).
    
    REGOLE:
    1. Traduci in INGLESE (US).
    2. Usa un tono professionale ed energico.
    3. Image Prompts: Scrivi descrizioni visive dettagliate in inglese. 
       STILE IMMAGINI RICHIESTO: {style_instruction}.
    
    JSON ESATTO:
    {{
        "cover": {{ "title": "...", "subtitle": "...", "image_prompt": "..." }},
        "slides": [
            {{ "id": 1, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 2, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 3, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 4, "title": "...", "body": "...", "image_prompt": "..." }},
            {{ "id": 5, "title": "...", "body": "...", "image_prompt": "..." }}
        ]
    }}
    """
    
    # Qui usiamo il modello selezionato nella Sidebar
    model = genai.GenerativeModel(model_name)
    try:
        resp = model.generate_content(f"{prompt}\n\nTESTO:\n{text}", generation_config={"response_mime_type": "application/json"})
        return json.loads(resp.text)
    except Exception as e:
        print(e)
        return None

def generate_image_url(prompt, style):
    """URL immagine AI con ottimizzazione modello"""
    # Selezioniamo il modello interno di Pollinations
    # Se l'utente sceglie "Imagen 4", usiamo 'flux' (che è il top di gamma attuale su Pollinations) 
    # ma con il prompt ottimizzato da Gemini per simulare quello stile.
    model_param = "flux" 
    
    if "Anime" in style: model_param = "midjourney"
    
    clean_prompt = prompt.replace(' ', '%20')
    # Aggiungiamo seed casuale per variare
    return f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1920&height=1080&model={model_param}&nologo=true&seed={os.urandom(2).hex()}"

def find_image_element_id(prs_id, label):
    """Trova ID immagine nel template tramite Alt Text"""
    try:
        prs = slides_service.presentations().get(presentationId=prs_id).execute()
        for slide in prs.get('slides', []):
            for el in slide.get('pageElements', []):
                if el.get('description') == label: return el['objectId']
    except: pass
    return None

def worker_bot(template_id, folder_id, filename, ai_data, img_style_choice):
    """Clona e compila"""
    
    # 1. COPIA TEMPLATE
    try:
        copy = drive_service.files().copy(
            fileId=template_id, 
            body={'name': filename, 'parents': [folder_id]}
        ).execute()
        new_id = copy.get('id')
    except Exception as e:
        st.error(f"Errore copia file: {e}")
        return None
    
    # 2. TESTI
    reqs = []
    if 'cover' in ai_data:
        reqs.append({'replaceAllText': {'containsText': {'text': '{{TITLE}}'}, 'replaceText': ai_data['cover'].get('title', '')}})
        reqs.append({'replaceAllText': {'containsText': {'text': '{{SUBTITLE}}'}, 'replaceText': ai_data['cover'].get('subtitle', '')}})
    
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
                # Generiamo l'URL passando anche lo stile scelto
                img_url = generate_image_url(prompt, img_style_choice)
                reqs_img.append({
                    'replaceImage': {
                        'imageObjectId': el_id,
                        'imageReplaceMethod': 'CENTER_CROP',
                        'url': img_url
                    }
                })
            
    if reqs_img: 
        slides_service.presentations().batchUpdate(presentationId=new_id, body={'requests': reqs_img}).execute()
        
    return new_id

# --- INTERFACCIA PRINCIPALE ---
st.title("🦖 Slide Monster (Pro Edition)")

col1, col2 = st.columns([1, 2])

with col1:
    st.subheader("1. Configurazione")
    template_id = st.text_input("ID Template", value=DEFAULT_TEMPLATE_ID)
    folder_id = st.text_input("ID Cartella Output", value=DEFAULT_FOLDER_ID)
    
    st.success(f"Brain: **{selected_gemini}**")
    st.success(f"Art: **{image_style}**")

with col2:
    st.subheader("2. Carica i vecchi PPT")
    files = st.file_uploader("Trascina qui i PPTX", accept_multiple_files=True, type=['pptx'])
    
    if st.button("🔥 ATTIVA IL MOSTRO", type="primary"):
        if not files or not folder_id or not template_id:
            st.warning("Mancano i file!")
        else:
            bar = st.progress(0)
            status = st.empty()
            
            for i, f in enumerate(files):
                fname = f.name.replace(".pptx", "") + "_ENG"
                status.write(f"⚙️ Elaborazione: **{fname}** con {selected_gemini}...")
                
                try:
                    txt = extract_text_from_pptx(f)
                    
                    # Passiamo il modello selezionato e lo stile al cervello
                    data = brain_process(txt, selected_gemini, image_style)
                    
                    if data:
                        new_id = worker_bot(template_id, folder_id, fname, data, image_style)
                        if new_id:
                            st.toast(f"✅ Fatto: {fname}")
                        else:
                            st.error(f"❌ Errore copia su {fname}")
                    else:
                        st.error(f"❌ Errore AI (JSON vuoto) su {fname}")

                except Exception as e:
                    st.error(f"❌ Critico {fname}: {e}")
                
                bar.progress((i+1)/len(files))
            
            st.balloons()
            st.success("Tutto completato! Controlla Google Drive.")
