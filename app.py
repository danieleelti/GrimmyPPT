import streamlit as st
import google.generativeai as genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
import json

st.set_page_config(page_title="🧹 Drive Cleaner", layout="wide")
st.title("🧹 Service Account Cleaner")
st.markdown("Questo script controlla lo spazio del Robot e rimuove eventuali file 'fantasma' che bloccano l'upload.")

# --- LOGIN ---
try:
    if "gcp_service_account" in st.secrets and "json_content" in st.secrets["gcp_service_account"]:
        json_str = st.secrets["gcp_service_account"]["json_content"]
        service_account_info = json.loads(json_str)
    else:
        service_account_info = json.loads(st.secrets["GCP_SERVICE_ACCOUNT"])
    
    creds = service_account.Credentials.from_service_account_info(
        service_account_info,
        scopes=['https://www.googleapis.com/auth/drive']
    )
    drive_service = build('drive', 'v3', credentials=creds)
    st.success("✅ Robot connesso.")

except Exception as e:
    st.error(f"Errore Login: {e}")
    st.stop()

# --- ANALISI SPAZIO ---
if st.button("📊 CONTROLLA SPAZIO OCCUPATO"):
    try:
        # Chiediamo al Drive del Robot quanto è pieno
        about = drive_service.about().get(fields="storageQuota").execute()
        quota = about.get('storageQuota', {})
        
        usage = int(quota.get('usage', 0))
        limit = int(quota.get('limit', 15 * 1024 * 1024 * 1024)) # Default 15GB
        
        usage_mb = usage / (1024 * 1024)
        
        st.write("---")
        st.metric(label="Spazio Usato dal Robot", value=f"{usage_mb:.2f} MB")
        
        if usage > limit:
            st.error("🚨 QUOTA SUPERATA! Il robot è pieno.")
        elif usage > 0:
            st.warning("Il robot ha dei file in memoria (anche se non li vedi).")
        else:
            st.success("Il robot è vuoto. Se ricevi ancora errore 403, il problema è la cartella di destinazione.")

    except Exception as e:
        st.error(f"Errore controllo: {e}")

# --- PULIZIA ---
st.divider()
st.subheader("🗑️ Pulizia Forzata")
st.write("Se lo spazio sopra non è 0, premi qui per cancellare tutti i file posseduti dal robot.")

if st.button("🔥 CANCELLA TUTTI I FILE DEL ROBOT"):
    try:
        # 1. Trova tutti i file di proprietà del robot (non cancella i tuoi, solo i suoi)
        results = drive_service.files().list(
            q="'me' in owners and trashed = false",
            fields="files(id, name, size)"
        ).execute()
        items = results.get('files', [])

        if not items:
            st.info("Nessun file attivo trovato da cancellare.")
        else:
            st.write(f"Trovati {len(items)} file. Eliminazione in corso...")
            progress = st.progress(0)
            
            for i, file in enumerate(items):
                try:
                    drive_service.files().delete(fileId=file['id']).execute()
                except:
                    pass
                progress.progress((i + 1) / len(items))
            st.success("✅ File eliminati.")

        # 2. Svuota il Cestino (Spesso i file rimangono qui e occupano spazio)
        st.write("Svuotamento cestino...")
        try:
            drive_service.files().emptyTrash().execute()
            st.success("✅ Cestino svuotato.")
        except Exception as e:
            st.warning(f"Cestino già vuoto o errore: {e}")

        st.balloons()
        st.info("Ora riprova a lanciare l'app principale!")

    except Exception as e:
        st.error(f"Errore durante la pulizia: {e}")
