import streamlit as st
import pandas as pd
import io
from imap_tools import MailBox, AND
from datetime import datetime, timedelta

# --- ΡΥΘΜΙΣΕΙΣ ---
EMAIL_USER = "abf.skyros@gmail.com"
EMAIL_PASS = st.secrets["EMAIL_PASS"] 
SENDER_EMAIL = "Notifications@WeDoConnect.com"

st.set_page_config(page_title="Έλεγχος Τιμολογίων", layout="wide", page_icon="📊")

def get_week_range(date_obj):
    start_of_week = date_obj - timedelta(days=date_obj.weekday()) 
    end_of_week = start_of_week + timedelta(days=6)
    return start_of_week, end_of_week

def find_header_and_load(file_content, filename):
    try:
        is_excel = filename.lower().endswith(('.xlsx', '.xls'))
        if is_excel:
            df_raw = pd.read_excel(io.BytesIO(file_content), header=None)
        else:
            try:
                df_raw = pd.read_csv(io.BytesIO(file_content), header=None, sep=None, engine='python')
            except:
                df_raw = pd.read_csv(io.BytesIO(file_content), header=None, encoding='cp1253', sep=None, engine='python')

        header_row_index = -1
        for i in range(min(40, len(df_raw))):
            row_values = [str(x).upper() for x in df_raw.iloc[i].values if pd.notna(x)]
            row_str = " ".join(row_values)
            if "ΤΥΠΟΣ" in row_str and "ΗΜΕΡΟΜΗΝΙΑ" in row_str:
                header_row_index = i
                break
        
        if header_row_index == -1: return None
            
        df = df_raw.iloc[header_row_index + 1:].copy()
        headers = [str(h).strip().upper() for h in df_raw.iloc[header_row_index]]
        df.columns = headers
        df = df.loc[:, df.columns.notna()]
        df = df.loc[:, ~df.columns.str.contains('NAN|UNNAMED', case=False)]
        return df.reset_index(drop=True)
    except:
        return None

@st.cache_data(ttl=600) 
def load_data():
    all_data = pd.DataFrame()
    
    try:
        with MailBox('imap.gmail.com').login(EMAIL_USER, EMAIL_PASS) as mailbox:
            # ΣΤΟΧΕΥΜΕΝΗ ΑΝΑΖΗΤΗΣΗ: Μόνο τα 20 τελευταία από τον συγκεκριμένο αποστολέα!
            messages = list(mailbox.fetch(AND(from_=SENDER_EMAIL), limit=20, reverse=True))
            
            for msg in messages:
                for att in msg.attachments:
                    if att.filename.lower().endswith(('.xlsx', '.csv', '.xls')):
                        df = find_header_and_load(att.payload, att.filename)
                        if df is not None:
                            col_date = next((c for c in df.columns if 'ΗΜΕΡΟΜΗΝΙΑ' in c), None)
                            col_value = next((c for c in df.columns if 'ΑΞΙΑ' in c or 'ΣΥΝΟΛΟ' in c), None)
                            col_type = next((c for c in df.columns if 'ΤΥΠΟΣ' in c), None)
                            
                            if col_date and col_value and col_type:
                                temp_df = df[[col_date, col_type, col_value]].copy()
                                temp_df.columns = ['DATE', 'TYPE', 'VALUE']
                                
                                temp_df['DATE'] = pd.to_datetime(temp_df['DATE'], errors='coerce')
                                if temp_df['VALUE'].dtype == object:
                                    temp_df['VALUE'] = temp_df['VALUE'].astype(str).str.replace('€', '').str.replace(',', '.').str.strip()
                                temp_df['VALUE'] = pd.to_numeric(temp_df['VALUE'], errors='coerce').fillna(0)
                                
                                all_data = pd.concat([all_data, temp_df.dropna(subset=['DATE'])], ignore_index=True)
        return all_data
    except Exception as e:
        st.error(f"Σφάλμα σύνδεσης: {e}")
        return pd.DataFrame()

# --- ΕΜΦΑΝΙΣΗ ---
st.title("📊 Σύστημα Ελέγχου Παραστατικών")

if st.button("🔄 Φόρτωση & Ανανέωση Δεδομένων", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

df = load_data()

tab1, tab2 = st.tabs(["📅 Εβδομαδιαία Εικόνα", "📆 Μηνιαία Εικόνα"])

with tab1:
    sel_date = st.date_input("Επίλεξε ημέρα για την εβδομάδα:", datetime.now())
    start, end = get_week_range(datetime.combine(sel_date, datetime.min.time()))
    st.info(f"Περίοδος: {start.strftime('%d/%m/%Y')} έως {end.strftime('%d/%m/%Y')}")

    if not df.empty:
        mask = (df['DATE'] >= start) & (df['DATE'] <= end)
        w_df = df.loc[mask]
        
        if not w_df.empty:
            inv = w_df[~w_df['TYPE'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['VALUE'].sum()
            crd = w_df[w_df['TYPE'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['VALUE'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Τιμολόγια", f"{inv:.2f} €")
            c2.metric("Πιστωτικά", f"-{crd:.2f} €")
            c3.metric("ΚΑΘΑΡΟ ΣΥΝΟΛΟ", f"{(inv - crd):.2f} €")
            
            st.dataframe(w_df.rename(columns={'DATE':'ΗΜΕΡΟΜΗΝΙΑ', 'TYPE':'ΤΥΠΟΣ', 'VALUE':'ΑΞΙΑ'}).style.format({"ΑΞΙΑ": "{:.2f} €"}), use_container_width=True, hide_index=True)
        else:
            st.warning("Δεν υπάρχουν εγγραφές για αυτή την εβδομάδα.")
    else:
        st.info("Δεν έχουν φορτωθεί δεδομένα. Πάτα 'Ανανέωση Δεδομένων'.")

with tab2:
    if not df.empty:
        m_list = ["Ιανουάριος", "Φεβρουάριος", "Μάρτιος", "Απρίλιος", "Μάιος", "Ιούνιος", "Ιούλιος", "Αύγουστος", "Σεπτέμβριος", "Οκτώβριος", "Νοέμβριος", "Δεκέμβριος"]
        col_a, col_b = st.columns(2)
        with col_a: s_m = st.selectbox("Μήνας", range(1, 13), format_func=lambda x: m_list[x-1], index=datetime.now().month-1)
        with col_b: s_y = st.selectbox("Έτος", sorted(df['DATE'].dt.year.unique(), reverse=True))
        
        mask_m = (df['DATE'].dt.month == s_m) & (df['DATE'].dt.year == s_y)
        m_df = df.loc[mask_m]
        
        if not m_df.empty:
            inv_m = m_df[~m_df['TYPE'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['VALUE'].sum()
            crd_m = m_df[m_df['TYPE'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['VALUE'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Τιμολόγια Μήνα", f"{inv_m:.2f} €")
            c2.metric("Πιστωτικά Μήνα", f"-{crd_m:.2f} €")
            c3.metric("ΣΥΝΟΛΟ ΜΗΝΑ", f"{(inv_m - crd_m):.2f} €", delta_color="normal")
            
            st.divider()
            csv = m_df.rename(columns={'DATE':'ΗΜΕΡΟΜΗΝΙΑ', 'TYPE':'ΤΥΠΟΣ', 'VALUE':'ΑΞΙΑ'}).to_csv(index=False).encode('utf-8-sig')
            st.download_button("📥 Κατέβασμα Μήνα σε CSV", csv, f"invoices_{s_m}_{s_y}.csv", "text/csv")
        else:
            st.warning("Δεν υπάρχουν εγγραφές για αυτόν τον μήνα.")
