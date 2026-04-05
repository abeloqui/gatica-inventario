import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# 1. CONFIGURACIÓN DE PÁGINA (Debe ser lo primero siempre)
st.set_page_config(page_title="Gatica Food - Inventario", page_icon="📦", layout="wide")

# 2. DISEÑO CSS
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    [data-testid="stMetric"] {
        background-color: #ffffff !important;
        padding: 20px !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
        border: 1px solid #e0e0e0 !important;
    }
    [data-testid="stMetricLabel"] { color: #31333F !important; font-weight: bold !important; }
    [data-testid="stMetricValue"] { color: #1a1c23 !important; }
    div.stButton > button:first-child { width: 100%; border-radius: 10px; height: 3.5em; font-weight: bold; background-color: #ff4b4b; color: white; }
    @media (max-width: 640px) { [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; margin-bottom: 10px; } }
    </style>
    """, unsafe_allow_html=True)

# 3. CONEXIÓN Y SCOPES
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_all_sheets():
    creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
    return {
        "General": spreadsheet.get_worksheet(0),
        "Cocina": spreadsheet.worksheet("Cocina")
    }

# 4. LÓGICA DE SELECCIÓN (Aquí se crea la variable sector_seleccionado)
with st.sidebar:
    st.title("Panel de Control")
    sector_seleccionado = st.selectbox("Seleccionar Sector", ["General", "Cocina"])
    st.divider()
    busqueda = st.text_input("🔍 Buscar Producto", "")
    solo_bajos = st.toggle("🚨 Solo alertas críticas", value=False)
    if st.button("🔄 Refrescar Datos"):
        st.cache_resource.clear()
        st.rerun()

# 5. OBTENER DATOS DE LA HOJA ELEGIDA
try:
    diccionario_hojas = get_all_sheets()
    sheet = diccionario_hojas[sector_seleccionado]
    
    values = sheet.get_all_values()
    if values and len(values) > 0:
        clean_values = [row[:5] for row in values]
        df_raw = pd.DataFrame(clean_values[1:], columns=[c.strip() for c in clean_values[0]])
        # Normalizar columnas
        df_raw.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df_raw.columns]
        column_map = {'categoria': 'Categoría', 'producto': 'Producto', 'stock actual': 'Stock Actual', 'stock minimo': 'Stock Mínimo', 'estado': 'Estado'}
        df_raw = df_raw.rename(columns=column_map)
        for col in ['Stock Actual', 'Stock Mínimo']:
            if col in df_raw.columns:
                df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0).astype(int)
    else:
        df_raw = pd.DataFrame()
except Exception as e:
    st.error(f"Error al conectar: {e}")
    st.stop()

# --- 6. INTERFAZ PRINCIPAL (Ahora sector_seleccionado ya existe) ---
st.title(f"📦 Inventario: {sector_seleccionado}")

if not df_raw.empty:
    # Métricas
    t1, t2, t3 = st.columns(3)
    t1.metric("Productos", len(df_raw))
    alertas = len(df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']])
    t2.metric("Alertas", alertas, delta=-alertas, delta_color="inverse")
    t3.metric("Sync", datetime.now().strftime('%H:%M'))

    # Tabla
    df_display = df_raw.copy()
    if busqueda: df_display = df_display[df_display['Producto'].str.contains(busqueda, case=False)]
    if solo_bajos: df_display = df_display[df_display['Stock Actual'] < df_display['Stock Mínimo']]

    st.dataframe(df_display, width="stretch", hide_index=True)
else:
    st.info(f"La hoja '{sector_seleccionado}' está vacía.")

st.divider()

# 7. ACCIONES
col_edit, col_new = st.columns(2)

with col_edit:
    if not df_raw.empty:
        with st.container(border=True):
            st.subheader("📝 Editar")
            prod_sel = st.selectbox("Producto", df_raw['Producto'].tolist(), key="edit")
            if prod_sel:
                curr = df_raw[df_raw['Producto'] == prod_sel].iloc[0]
                nuevo = st.number_input("Stock", value=int(curr['Stock Actual']))
                c_up, c_del = st.columns([2,1])
                if c_up.button("Guardar", type="primary"):
                    cell = sheet.find(prod_sel, in_column=2)
                    sheet.update_cell(cell.row, 3, nuevo)
                    sheet.update_cell(cell.row, 5, "🚨 BAJO" if nuevo < curr['Stock Mínimo'] else "✅ OK")
                    st.cache_resource.clear()
                    st.rerun()
                with c_del.popover("🗑️"):
                    if st.button("Confirmar Borrar"):
                        cell = sheet.find(prod_sel, in_column=2)
                        sheet.delete_rows(cell.row)
                        st.cache_resource.clear()
                        st.rerun()

with col_new:
    with st.container(border=True):
        st.subheader("➕ Nuevo")
        with st.form("nuevo", clear_on_submit=True):
            f_cat = st.text_input("Categoría", sector_seleccionado)
            f_prod = st.text_input("Nombre")
            f_st = st.number_input("Stock Inicial", 0)
            f_mi = st.number_input("Mínimo", 1, value=10)
            if st.form_submit_button("Agregar"):
                if f_prod:
                    est = "🚨 BAJO" if f_st < f_mi else "✅ OK"
                    sheet.append_row([f_cat, f_prod, f_st, f_mi, est])
                    st.cache_resource.clear()
                    st.rerun()

st.sidebar.caption(f"Gatica Food v2.3 | {datetime.now().year}")
