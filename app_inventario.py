import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# 1. CONFIGURACIÓN Y ESTILO
st.set_page_config(
    page_title="Gatica Food - Panel de Control",
    page_icon="📦",
    layout="wide", # Crucial para el responsive en escritorio
)

# CSS Personalizado para mejorar el aspecto de las tarjetas y botones
st.markdown("""
    <style>
    .main {
        background-color: #f8f9fa;
    }
    .stMetric {
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    div.stButton > button:first-child {
        width: 100%;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_status_code=True)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_sheet():
    creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
    return spreadsheet.sheet1

try:
    sheet = get_sheet()
except Exception as e:
    st.error(f"⚠️ Error de conexión: {e}")
    st.stop()

def cargar_datos():
    values = sheet.get_all_values()
    if not values or len(values) < 1: return pd.DataFrame()
    clean_values = [row[:5] for row in values]
    df = pd.DataFrame(clean_values[1:], columns=[c.strip() for c in clean_values[0]])
    
    # Normalización prolija
    df.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df.columns]
    column_map = {
        'categoria': 'Categoría', 'producto': 'Producto', 
        'stock actual': 'Stock Actual', 'stock minimo': 'Stock Mínimo', 'estado': 'Estado'
    }
    df = df.rename(columns=column_map)
    for col in ['Stock Actual', 'Stock Mínimo']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    return df

# --- PROCESAMIENTO DE DATOS ---
df_raw = cargar_datos()

# --- SIDEBAR (Filtros Móviles) ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4043/4043231.png", width=100)
    st.title("Filtros")
    busqueda = st.text_input("🔍 Buscar Producto", "")
    solo_bajos = st.toggle("🚨 Solo alertas de Stock", value=False)
    st.divider()
    if st.button("🔄 Refrescar Datos"):
        st.cache_resource.clear()
        st.rerun()

# --- DASHBOARD PRINCIPAL ---
st.title("📦 Sistema de Inventario")

if not df_raw.empty:
    # 1. MÉTRICAS RÁPIDAS (Se ven genial en celular)
    total_prods = len(df_raw)
    bajos = len(df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']])
    
    m1, m2, m3 = st.columns(3)
    m1.metric("Total Productos", total_prods)
    m2.metric("Alertas Críticas", bajos, delta=-bajos, delta_color="inverse")
    m3.metric("Último Sync", datetime.now().strftime('%H:%M'))

    # Aplicar filtros al DF que se muestra
    df_display = df_raw.copy()
    if busqueda:
        df_display = df_display[df_display['Producto'].str.contains(busqueda, case=False)]
    if solo_bajos:
        df_display = df_display[df_display['Stock Actual'] < df_display['Stock Mínimo']]

    # 2. TABLA PRINCIPAL
    with st.expander("Ver tabla completa", expanded=True):
        st.dataframe(
            df_display, 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "Stock Actual": st.column_config.NumberColumn(format="%d 📦"),
                "Estado": st.column_config.TextColumn("Status")
            }
        )

    # 3. ACCIONES EN COLUMNAS (Responsive)
    col_a, col_b = st.columns([1, 1])

    with col_a:
        with st.container(border=True):
            st.subheader("📝 Editar Stock")
            prod_sel = st.selectbox("Producto", df_raw['Producto'].tolist(), key="sel_edit")
            if prod_sel:
                curr_stock = int(df_raw[df_raw['Producto'] == prod_sel]['Stock Actual'].values[0])
                nuevo = st.number_input("Cantidad nueva", value=curr_stock, step=1)
                if st.button("Actualizar", type="primary"):
                    try:
                        cell = sheet.find(prod_sel, in_column=2)
                        sheet.update_cell(cell.row, 3, nuevo)
                        # Auto-estado
                        min_s = int(df_raw[df_raw['Producto'] == prod_sel]['Stock Mínimo'].values[0])
                        sheet.update_cell(cell.row, 5, "🚨 BAJO" if nuevo < min_s else "✅ OK")
                        st.success("¡Listo!")
                        st.cache_resource.clear()
                        st.rerun()
                    except: st.error("Error al guardar")

    with col_b:
        with st.container(border=True):
            st.subheader("➕ Nuevo Item")
            with st.popover("Abrir Formulario"):
                with st.form("new_item", clear_on_submit=True):
                    n_cat = st.text_input("Categoría")
                    n_prod = st.text_input("Producto")
                    c1, c2 = st.columns(2)
                    n_st = c1.number_input("Stock", min_value=0)
                    n_mi = c2.number_input("Mínimo", min_value=0)
                    if st.form_submit_button("Registrar"):
                        if n_prod:
                            est = "🚨 BAJO" if n_st < n_mi else "✅ OK"
                            sheet.append_row([n_cat, n_prod, n_st, n_mi, est])
                            st.cache_resource.clear()
                            st.rerun()
else:
    st.info("Agrega tu primer producto para empezar.")
