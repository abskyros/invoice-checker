import streamlit as st
import pandas as pd
import io
from imap_tools import MailBox, AND
from datetime import datetime, timedelta

# --- ΡΥΘΜΙΣΕΙΣ ---
EMAIL_USER = "abf.skyros@gmail.com"
EMAIL_PASS = st.secrets["EMAIL_PASS"] 
SENDER_EMAIL = "Notifications@WeDoConnect.com"

# Ρύθμιση της σελίδας
st.set_page_config(page_title="Έλεγχος Τιμολογίων", layout="centered")

def get_week_range(date_obj):
    start_of_week = date_obj - timedelta(days=date_obj.weekday()) 
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week

def find_header_and_load(file_content, is_excel=False):
    try:
        if is_excel:
            df_raw = pd.read_excel(io.BytesIO(file_content), header=None)
        else:
            try:
                df_raw = pd.read_csv(io.BytesIO(file_content), header=None)
            except:
                df_raw = pd.read_csv(io.BytesIO(file_content), header=None, encoding='cp1253')

        header_row_index = -1
        for i in range(min(30, len(df_raw))):
            row_values = df_raw.iloc[i].astype(str).values
            row_str = " ".join(row_values).upper()
            if "ΤΥΠΟΣ" in row_str and "ΗΜΕΡΟΜΗΝΙΑ" in row_str:
                header_row_index = i
                break
        
        if header_row_index == -1: return None
        df_raw.columns = df_raw.iloc[header_row_index]
        return df_raw.iloc[header_row_index + 1:].reset_index(drop=True)
    except: return None

# Cache για να μην κατεβάζει τα emails κάθε φορά που πατάς ένα κουμπί, 
# αλλά μόνο όταν πατάς "Ανανέωση Δεδομένων"
@st.cache_data(ttl=600) 
def load_data():
    all_data = pd.DataFrame()
    status_text = st.empty()
    status_text.text("⏳ Σύνδεση στο Email και λήψη δεδομένων...")
    
    try:
        with MailBox('imap.gmail.com').login(EMAIL_USER, EMAIL_PASS) as mailbox:
            # Ψάχνουμε τα τελευταία 40 emails
            for msg in mailbox.fetch(AND(from_=SENDER_EMAIL), limit=40, reverse=True):
                for att in msg.attachments:
                    if att.filename.endswith(('.xlsx', '.csv')):
                        df = find_header_and_load(att.payload, att.filename.endswith('.xlsx'))
                        if df is not None:
                            # Καθαρισμός
                            df.columns = df.columns.astype(str).str.strip()
                            col_date = 'ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'
                            col_value = 'ΣΥΝΟΛΙΚΗ ΑΞΙΑ'
                            
                            if col_date in df.columns and col_value in df.columns:
                                df[col_date] = pd.to_datetime(df[col_date], errors='coerce')
                                df = df.dropna(subset=[col_date])
                                
                                if df[col_value].dtype == object:
                                    df[col_value] = df[col_value].astype(str).str.replace('€', '').str.replace(',', '.')
                                df[col_value] = pd.to_numeric(df[col_value], errors='coerce').fillna(0)
                                
                                all_data = pd.concat([all_data, df], ignore_index=True)
        
        status_text.text("✅ Τα δεδομένα φορτώθηκαν!")
        return all_data
    except Exception as e:
        status_text.error(f"Σφάλμα: {e}")
        return pd.DataFrame()

# --- ΤΟ ΚΥΡΙΩΣ ΠΡΟΓΡΑΜΜΑ (UI) ---
st.title("📊 Έλεγχος Τιμολογίων")

if st.button("🔄 Ανανέωση Δεδομένων"):
    st.cache_data.clear()

df = load_data()

if not df.empty:
    st.divider()
    
    # Επιλογή Ημερομηνίας με ωραίο ημερολόγιο
    selected_date = st.date_input("Επίλεξε μια ημερομηνία μέσα στην εβδομάδα που σε ενδιαφέρει:", datetime.now())
    
    # Μετατροπή date σε datetime για τους υπολογισμούς
    target_date = datetime.combine(selected_date, datetime.min.time())
    
    start_week, end_week = get_week_range(target_date)
    start_week = start_week.replace(hour=0, minute=0, second=0)
    end_week = end_week.replace(hour=23, minute=59, second=59)
    
    st.subheader(f"📅 Εβδομάδα: {start_week.strftime('%d/%m')} - {end_week.strftime('%d/%m/%Y')}")

    # Φιλτράρισμα
    mask = (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'] >= start_week) & (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'] <= end_week)
    weekly_df = df.loc[mask]

    if weekly_df.empty:
        st.warning("Δεν βρέθηκαν παραστατικά για αυτή την εβδομάδα.")
    else:
        # Υπολογισμοί
        total_invoices = 0.0
        total_credits = 0.0
        
        # Ομαδοποίηση για προβολή
        sums = weekly_df.groupby('ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ')['ΣΥΝΟΛΙΚΗ ΑΞΙΑ'].sum().reset_index()
        
        st.write("Αναλυτικά:")
        # Εμφάνιση πίνακα
        st.dataframe(sums.style.format({"ΣΥΝΟΛΙΚΗ ΑΞΙΑ": "{:.2f} €"}), use_container_width=True)

        for _, row in sums.iterrows():
            if "ΠΙΣΤΩΤΙΚΟ" in row['ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'].upper():
                total_credits += row['ΣΥΝΟΛΙΚΗ ΑΞΙΑ']
            else:
                total_invoices += row['ΣΥΝΟΛΙΚΗ ΑΞΙΑ']

        final_total = total_invoices - total_credits

        st.divider()
        col1, col2, col3 = st.columns(3)
        col1.metric("Τιμολόγια", f"{total_invoices:.2f} €")
        col2.metric("Πιστωτικά", f"-{total_credits:.2f} €")
        col3.metric("ΚΑΘΑΡΟ ΣΥΝΟΛΟ", f"{final_total:.2f} €", delta_color="normal")
else:
    st.error("Δεν βρέθηκαν δεδομένα.")

