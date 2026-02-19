import streamlit as st
import pandas as pd
import io
from imap_tools import MailBox, AND
from datetime import datetime, timedelta

# --- ΡΥΘΜΙΣΕΙΣ ---
EMAIL_USER = "abf.skyros@gmail.com"
EMAIL_PASS = st.secrets["EMAIL_PASS"] # Παίρνει τον κωδικό με ασφάλεια
SENDER_EMAIL = "Notifications@WeDoConnect.com"

st.set_page_config(page_title="Έλεγχος Τιμολογίων", layout="centered", page_icon="📊")

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

@st.cache_data(ttl=600) 
def load_data():
    all_data = pd.DataFrame()
    status_text = st.empty()
    status_text.info("⏳ Λήψη νέων δεδομένων από το Email...")
    
    try:
        with MailBox('imap.gmail.com').login(EMAIL_USER, EMAIL_PASS) as mailbox:
            for msg in mailbox.fetch(AND(from_=SENDER_EMAIL), limit=50, reverse=True):
                for att in msg.attachments:
                    if att.filename.endswith(('.xlsx', '.csv')):
                        df = find_header_and_load(att.payload, att.filename.endswith('.xlsx'))
                        if df is not None:
                            df.columns = df.columns.astype(str).str.strip()
                            col_date = 'ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'
                            col_value = 'ΣΥΝΟΛΙΚΗ ΑΞΙΑ'
                            col_type = 'ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'
                            
                            if col_date in df.columns and col_value in df.columns:
                                df[col_date] = pd.to_datetime(df[col_date], errors='coerce')
                                df = df.dropna(subset=[col_date])
                                
                                if df[col_value].dtype == object:
                                    df[col_value] = df[col_value].astype(str).str.replace('€', '').str.replace(',', '.')
                                df[col_value] = pd.to_numeric(df[col_value], errors='coerce').fillna(0)
                                
                                # Δημιουργία στήλης καθαρής αξίας (Αρνητικά τα πιστωτικά)
                                df['ΚΑΘΑΡΗ ΑΞΙΑ'] = df.apply(
                                    lambda row: -row[col_value] if "ΠΙΣΤΩΤΙΚΟ" in str(row[col_type]).upper() else row[col_value], 
                                    axis=1
                                )
                                
                                all_data = pd.concat([all_data, df], ignore_index=True)
        
        status_text.empty() # Καθαρίζει το μήνυμα φόρτωσης
        return all_data
    except Exception as e:
        status_text.error(f"Σφάλμα: {e}")
        return pd.DataFrame()

# --- G UI & ΣΧΕΔΙΑΣΜΟΣ ---
st.title("📊 Πίνακας Ελέγχου Παραστατικών")

col1, col2 = st.columns([3, 1])
with col2:
    if st.button("🔄 Ανανέωση", use_container_width=True):
        st.cache_data.clear()

df = load_data()

if not df.empty:
    # Δημιουργία Καρτελών (Tabs)
    tab_week, tab_month = st.tabs(["📅 Ανά Εβδομάδα", "📆 Ανά Μήνα"])
    
    # --- ΚΑΡΤΕΛΑ 1: ΕΒΔΟΜΑΔΑ ---
    with tab_week:
        st.subheader("Στοιχεία Εβδομάδας")
        selected_date = st.date_input("Επίλεξε ημερομηνία", datetime.now(), key="week_date")
        target_date = datetime.combine(selected_date, datetime.min.time())
        start_week, end_week = get_week_range(target_date)
        
        st.markdown(f"**Περίοδος:** {start_week.strftime('%d/%m')} έως {end_week.strftime('%d/%m/%Y')}")

        mask_week = (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'] >= start_week) & (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'] <= end_week)
        weekly_df = df.loc[mask_week]

        if weekly_df.empty:
            st.warning("Δεν βρέθηκαν παραστατικά.")
        else:
            invoices = weekly_df[~weekly_df['ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['ΣΥΝΟΛΙΚΗ ΑΞΙΑ'].sum()
            credits = weekly_df[weekly_df['ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['ΣΥΝΟΛΙΚΗ ΑΞΙΑ'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Τιμολόγια", f"{invoices:.2f} €")
            c2.metric("Πιστωτικά", f"-{credits:.2f} €")
            c3.metric("ΚΑΘΑΡΟ", f"{(invoices - credits):.2f} €", delta_color="normal")
            
            # Γράφημα ανά ημέρα
            st.markdown("##### Εξέλιξη μέσα στην εβδομάδα")
            daily_chart_data = weekly_df.groupby(weekly_df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'].dt.date)['ΚΑΘΑΡΗ ΑΞΙΑ'].sum()
            st.bar_chart(daily_chart_data)
            
            st.dataframe(weekly_df[['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΣΥΝΟΛΙΚΗ ΑΞΙΑ']].style.format({"ΣΥΝΟΛΙΚΗ ΑΞΙΑ": "{:.2f} €"}), use_container_width=True, hide_index=True)

    # --- ΚΑΡΤΕΛΑ 2: ΜΗΝΑΣ ---
    with tab_month:
        st.subheader("Συγκεντρωτικά Μήνα")
        
        # Φίλτρα Μήνα και Έτους
        col_m1, col_m2 = st.columns(2)
        months = ["Ιανουάριος", "Φεβρουάριος", "Μάρτιος", "Απρίλιος", "Μάιος", "Ιούνιος", "Ιούλιος", "Αύγουστος", "Σεπτέμβριος", "Οκτώβριος", "Νοέμβριος", "Δεκέμβριος"]
        
        current_month = datetime.now().month
        current_year = datetime.now().year
        
        with col_m1:
            sel_month_name = st.selectbox("Μήνας", months, index=current_month-1)
            sel_month = months.index(sel_month_name) + 1
        with col_m2:
            # Βρίσκει τα έτη που υπάρχουν στα δεδομένα
            available_years = df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'].dt.year.dropna().unique()
            if current_year not in available_years: available_years = list(available_years) + [current_year]
            sel_year = st.selectbox("Έτος", sorted(available_years, reverse=True))

        # Φιλτράρισμα βάσει μήνα/έτους
        mask_month = (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'].dt.month == sel_month) & (df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'].dt.year == sel_year)
        monthly_df = df.loc[mask_month]

        if monthly_df.empty:
            st.warning(f"Δεν υπάρχουν δεδομένα για {sel_month_name} {sel_year}.")
        else:
            invoices_m = monthly_df[~monthly_df['ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['ΣΥΝΟΛΙΚΗ ΑΞΙΑ'].sum()
            credits_m = monthly_df[monthly_df['ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ'].str.contains("ΠΙΣΤΩΤΙΚΟ", na=False)]['ΣΥΝΟΛΙΚΗ ΑΞΙΑ'].sum()
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Τιμολόγια", f"{invoices_m:.2f} €")
            c2.metric("Πιστωτικά", f"-{credits_m:.2f} €")
            c3.metric("ΣΥΝΟΛΟ ΜΗΝΑ", f"{(invoices_m - credits_m):.2f} €", delta_color="normal")
            
            st.markdown("##### Συνολική Αξία ανά Ημέρα του Μήνα")
            monthly_chart_data = monthly_df.groupby(monthly_df['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ'].dt.date)['ΚΑΘΑΡΗ ΑΞΙΑ'].sum()
            st.bar_chart(monthly_chart_data)

            # Κουμπί εξαγωγής δεδομένων
            csv = monthly_df[['ΗΜΕΡΟΜΗΝΙΑ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΤΥΠΟΣ ΠΑΡΑΣΤΑΤΙΚΟΥ', 'ΣΥΝΟΛΙΚΗ ΑΞΙΑ']].to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 Κατέβασμα Μήνα σε CSV",
                data=csv,
                file_name=f"invoices_{sel_month}_{sel_year}.csv",
                mime="text/csv",
            )
else:
    st.info("Δεν βρέθηκαν καθόλου δεδομένα. Πάτα Ανανέωση.")
