import streamlit as st
import pandas as pd
import io
from imap_tools import MailBox, AND
from datetime import datetime, timedelta

# --- ΡΥΘΜΙΣΕΙΣ ---
EMAIL_USER = "abf.skyros@gmail.com"
EMAIL_PASS = st.secrets["EMAIL_PASS"] 
SENDER_EMAIL = "Notifications@WeDoConnect.com" # Επαναφορά στο ακριβές email για σίγουρη αναζήτηση

st.set_page_config(page_title="Έλεγχος Τιμολογίων", layout="centered", page_icon="📊")

def get_week_range(date_obj):
    start_of_week = date_obj - timedelta(days=date_obj.weekday()) 
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week

def find_header_and_load(file_content, is_excel=False):
    """Ψάχνει να βρει τη σωστή γραμμή με τους τίτλους μέσα στο αρχείο"""
    try:
        if is_excel:
            df_raw = pd.read_excel(io.BytesIO(file_content), header=None)
        else:
            try:
                df_raw = pd.read_csv(io.BytesIO(file_content), header=None, sep=',')
            except:
                df_raw = pd.read_csv(io.BytesIO(file_content), header=None, encoding='cp1253', sep=';')

        header_row_index = -1
        # Ψάχνουμε τις πρώτες 40 γραμμές για τις λέξεις-κλειδιά
        for i in range(min(40, len(df_raw))):
            row_str = " ".join(df_raw.iloc[i].astype(str).values).upper()
            if "ΤΥΠΟΣ" in row_str and "ΗΜΕΡΟΜΗΝΙΑ" in row_str:
                header_row_index = i
                break
        
        if header_row_index == -1: 
            return None
            
        df_raw.columns = df_raw.iloc[header_row_index]
        df_final = df_raw.iloc[header_row_index + 1:].reset_index(drop=True)
        return df_final
    except: 
        return None

@st.cache_data(ttl=600) 
def load_data():
    all_data = pd.DataFrame()
    status_text = st.empty()
    status_text.info("⏳ Λήψη και σάρωση δεδομένων από το Email...")
    
    try:
        with MailBox('imap.gmail.com').login(EMAIL_USER, EMAIL_PASS) as mailbox:
            # Ψάχνουμε τα τελευταία 100 emails με βάση το ακριβές email
            for msg in mailbox.fetch(AND(from_=SENDER_EMAIL), limit=100, reverse=True):
                for att in msg.attachments:
                    if att.filename.endswith(('.xlsx', '.csv', '.xls')):
                        df = find_header_and_load(att.payload, is_excel=not att.filename.endswith('.csv'))
                        
                        if df is not None:
                            # Καθαρισμός στηλών (αφαίρεση κενών κλπ)
                            df.columns = df.columns.astype(str).str.strip().str.upper()
                            
                            # Ψάχνουμε τις σωστές στήλες ακόμα κι αν τις έχουν ονομάσει λίγο διαφορετικά
                            col_date = next((c for c in df.columns if 'ΗΜΕΡΟΜΗΝΙΑ' in c), None)
                            col_value = next((c for c in df.columns if 'ΑΞΙΑ' in c or 'ΣΥΝΟΛΟ' in c), None)
                            col_type = next((c for c in df.columns if 'ΤΥΠΟΣ' in c), None)
                            
                            if col_date and col_value and col_type:
                                df_clean = df[[col_date, col_type, col_value]].copy()
                                
                                # Μετατροπή Ημερομηνίας
                                df_clean[col_date] = pd.to_datetime(df_clean[col_date], errors='coerce')
                                df_clean = df_clean.dropna(subset=[col_date])
                                
                                # Μετατροπή Ποσού
                                if df_clean[col_value].dtype == object:
                                    df_clean[col_value] = df_clean[col_value].astype(str).str.replace('€', '').str.replace(',', '.').str.strip()
                                df_clean[col_value] = pd.to_numeric(df_clean[col_value], errors='coerce').fillna(0)
                                
                                # Μετονομασία για να είναι στάνταρ στη συνέχεια
                                df_clean.columns = ['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΣΥΝΟΛΙΚΗ ΑΞΙΑ']
                                
                                all_data = pd.concat([all_data, df_clean], ignore_index=True)
        
        status_text.empty() 
        return all_data
    except Exception as e:
        status_text.error(f"Σφάλμα κατά τη σύνδεση: {e}")
        return pd.DataFrame()

# --- GUI & ΣΧΕΔΙΑΣΜΟΣ ---
st.title("📊 Πίνακας Ελέγχου Παραστατικών")

col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🔄 Ανανέωση Δεδομένων", use_container_width=True):
        st.cache_data.clear()

tab_week, tab_month = st.tabs(["📅 Ανά Εβδομάδα", "📆 Ανά Μήνα"])

df = load_data()

# --- ΚΑΡΤΕΛΑ 1: ΕΒΔΟΜΑΔΑ ---
with tab_week:
    st.subheader("Στοιχεία Εβδομάδας")
    selected_date = st.date_input("Επίλεξε ημερομηνία", datetime.now(), key="week_date")
    target_date = datetime.combine(selected_date, datetime.min.time())
    start_week, end_week = get_week_range(target_date)
    
    st.markdown(f"**Περίοδος:** {start_week.strftime('%d/%m/%Y')} έως {end_week.strftime('%d/%m/%Y')}")

    if df.empty:
        st.warning("⚠️ Δεν υπάρχουν καθόλου δεδομένα στη μνήμη. Δοκίμασε να πατήσεις 'Ανανέωση Δεδομένων'.")
    else:
        mask_week = (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'] >= start_week) & (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'] <= end_week)
        weekly_df = df.loc[mask_week]

        if weekly_df.empty:
            st.info("Δεν βρέθηκαν παραστατικά για τη συγκεκριμένη εβδομάδα. Επίλεξε άλλη ημερομηνία.")
        else:
            invoices = weekly_df[~weekly_df['ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['ΣΥΝΟΛΙΚΗ ΑΞΙΑ'].sum()
            credits = weekly_df[weekly_df['ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['ΣΥΝΟΛΙΚΗ ΑΞΙΑ'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Τιμολόγια", f"{invoices:.2f} €")
            c2.metric("Πιστωτικά", f"-{credits:.2f} €")
            c3.metric("ΚΑΘΑΡΟ ΣΥΝΟΛΟ", f"{(invoices - credits):.2f} €", delta_color="normal")
            
            st.write("---")
            st.dataframe(weekly_df[['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΣΥΝΟΛΙΚΗ ΑΞΙΑ']].style.format({"ΣΥΝΟΛΙΚΗ ΑΞΙΑ": "{:.2f} €"}), use_container_width=True, hide_index=True)

# --- ΚΑΡΤΕΛΑ 2: ΜΗΝΑΣ ---
with tab_month:
    st.subheader("Συγκεντρωτικά Μήνα")
    
    col_m1, col_m2 = st.columns(2)
    months = ["Ιανουάριος", "Φεβρουάριος", "Μάρτιος", "Απρίλιος", "Μάιος", "Ιούνιος", "Ιούλιος", "Αύγουστος", "Σεπτέμβριος", "Οκτώβριος", "Νοέμβριος", "Δεκέμβριος"]
    current_month = datetime.now().month
    current_year = datetime.now().year
    
    with col_m1:
        sel_month_name = st.selectbox("Μήνας", months, index=current_month-1)
        sel_month = months.index(sel_month_name) + 1
    
    with col_m2:
        if df.empty:
            available_years = [current_year]
        else:
            available_years = df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'].dt.year.dropna().unique()
            if current_year not in available_years: 
                available_years = list(available_years) + [current_year]
        sel_year = st.selectbox("Έτος", sorted(available_years, reverse=True))

    if not df.empty:
        mask_month = (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'].dt.month == sel_month) & (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'].dt.year == sel_year)
        monthly_df = df.loc[mask_month]

        if monthly_df.empty:
            st.info(f"Δεν υπάρχουν δεδομένα για {sel_month_name} {sel_year}.")
        else:
            invoices_m = monthly_df[~monthly_df['ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['ΣΥΝΟΛΙΚΗ ΑΞΙΑ'].sum()
            credits_m = monthly_df[monthly_df['ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['ΣΥΝΟΛΙΚΗ ΑΞΙΑ'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Τιμολόγια", f"{invoices_m:.2f} €")
            c2.metric("Πιστωτικά", f"-{credits_m:.2f} €")
            c3.metric("ΣΥΝΟΛΟ ΜΗΝΑ", f"{(invoices_m - credits_m):.2f} €", delta_color="normal")
            
            st.write("---")
            csv = monthly_df[['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΣΥΝΟΛΙΚΗ ΑΞΙΑ']].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Κατέβασμα Μήνα σε CSV",
                data=csv,
                file_name=f"invoices_{sel_month}_{sel_year}.csv",
                mime="text/csv",
            )
