import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(
    page_title="Gatica Food - Gestión de Inventario",
    page_icon="📦",
    layout="wide",
)

# 2. DISEÑO CSS (CORREGIDO PARA VISIBILIDAD EN MÓVIL)
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
    
    div.stButton > button:first-child {
        width: 100%;
        border-radius: 10px;
        height: 3.5em;
        font-weight: bold;
        background-color: #ff4b4b;
        color: white;
    }
    @media (max-width: 640px) {
        [data-testid="column"] { width: 100% !important; flex: 1 1 100% !important; margin-bottom: 10px; }
    }
    </style>
    """, unsafe_allow_html=True)

# 3. CONEXIÓN A GOOGLE SHEETS (MULTI-HOJA)
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_all_sheets():
    # Cargamos credenciales desde los Secrets de Streamlit
    creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
    client = gspread.authorize(creds)
    # Tu ID de documento
    spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
    
    return {
        "General": spreadsheet.get_worksheet(0),
        "Cocina": spreadsheet.worksheet("Cocina")
    }

# 4. LÓGICA DE SELECCIÓN DE SECTOR (DEBE IR ANTES QUE EL CONTENIDO)
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/4043/4043231.png", width=80)
    st.title("Panel de Control")
    
    # Esta es la variable que causaba el error, ahora definida al inicio
    sector_seleccionado = st.selectbox("Seleccionar Sector", ["General", "Cocina"])
    
    st.divider()
    busqueda = st.text_input("🔍 Buscar Producto", "")
    solo_bajos = st.toggle("🚨 Solo alertas críticas", value=False)
    
    if st.button("🔄 Refrescar Datos"):
        st.cache_resource.clear()
        st.rerun()

# Intentar obtener la hoja seleccionada
try:
    diccionario_hojas = get_all_sheets()
    sheet = diccionario_hojas[sector_seleccionado]
except Exception as e:
    st.error(f"⚠️ Error al conectar con la hoja '{sector_seleccionado}': {e}")
    st.info("Asegúrate de que la pestaña exista exactamente con ese nombre en tu Google Sheets.")
    st.stop()

# 5. FUNCIONES DE DATOS
def cargar_datos():
    values = sheet.get_all_values()
    if not values or len(values) < 1: return pd.DataFrame()
    
    # Limpieza de datos
    clean_values = [row[:5] for row in values]
    df = pd.DataFrame(clean_values[1:], columns=[c.strip() for c in clean_values[0]])
    
    # Normalizar nombres de columnas
    df.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df.columns]
    column_map = {
        'categoria': 'Categoría', 'producto': 'Producto', 
        'stock actual': 'Stock Actual', 'stock minimo': 'Stock Mínimo', 'estado': 'Estado'
    }
    df = df.rename(columns=column_map)
    
    for col in ['Stock Actual', 'Stock Mínimo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    return df

# Procesar DataFrame
df_raw = cargar_datos()

# --- INTERFAZ PRINCIPAL ---
st.title(f"📦 Inventario: {sector_seleccionado}")

if not df_raw.empty:
    # Métricas
    total_items = len(df_raw)
    alertas = len(df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']])
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Productos", total_items)
    c2.metric("Alertas", alertas, delta=-alertas, delta_color="inverse")
    c3.metric("Último Sync", datetime.now().strftime('%H:%M'))

    # Filtros de visualización
    df_display = df_raw.copy()
    if busqueda:
        df_display = df_display[df_display['Producto'].str.contains(busqueda, case=False)]
    if solo_bajos:
        df_display = df_display[df_display['Stock Actual'] < df_display['Stock Mínimo']]

    # Tabla de Inventario (Actualizada para 2026)
    st.subheader("Listado de Existencias")
    st.dataframe(
        df_display, 
        width="stretch", # Reemplaza use_container_width=True
        hide_index=True,
        column_config={
            "Stock Actual": st.column_config.NumberColumn(format="%d 📦"),
            "Stock Mínimo": st.column_config.NumberColumn(format="%d ⚠️"),
            "Estado": st.column_config.TextColumn("Status")
        }
    )

    # Bloques de Acción
    # 6. BLOQUES DE ACCIÓN (Responsive)
    col_edit, col_new = st.columns(2)

    with col_edit:
        with st.container(border=True):
            st.subheader("📝 Gestionar Existente")
            prod_sel = st.selectbox("Elegir producto", df_raw['Producto'].tolist(), key="edit_box")
            
            if prod_sel:
                curr_data = df_raw[df_raw['Producto'] == prod_sel].iloc[0]
                
                # Formulario de edición
                nuevo_valor = st.number_input("Nuevo Stock", value=int(curr_data['Stock Actual']), step=1)
                
                # BOTONES DE ACCIÓN (Actualizar y Eliminar)
                c_upd, c_del = st.columns([2, 1])
                
                if c_upd.button("Guardar Cambios", type="primary", use_container_width=True):
                    try:
                        cell = sheet.find(prod_sel, in_column=2)
                        sheet.update_cell(cell.row, 3, nuevo_valor)
                        nuevo_estado = "🚨 BAJO" if nuevo_valor < curr_data['Stock Mínimo'] else "✅ OK"
                        sheet.update_cell(cell.row, 5, nuevo_estado)
                        st.success("¡Actualizado!")
                        st.cache_resource.clear()
                        st.rerun()
                    except: st.error("Error de conexión")

                # FUNCIÓN ELIMINAR CON CONFIRMACIÓN
                with c_del.popover("🗑️"):
                    st.warning(f"¿Eliminar '{prod_sel}'?")
                    if st.button("Confirmar Borrado", type="secondary", help="Esta acción no se puede deshacer"):
                        try:
                            cell = sheet.find(prod_sel, in_column=2)
                            sheet.delete_rows(cell.row) # Borra la fila completa en Google Sheets
                            st.success(f"'{prod_sel}' eliminado")
                            st.cache_resource.clear()
                            st.rerun()
                        except: st.error("No se pudo eliminar")

    with col_new:
        with st.container(border=True):
            st.subheader("➕ Nuevo Producto")
            with st.popover("Abrir Formulario", use_container_width=True):
                with st.form("form_nuevo", clear_on_submit=True):
                    f_cat = st.text_input("Categoría", "Cocina" if sector_seleccionado == "Cocina" else "General")
                    f_prod = st.text_input("Nombre del Producto")
                    f_stock = st.number_input("Stock Inicial", min_value=0)
                    f_min = st.number_input("Stock Mínimo", min_value=1, value=10)
                    
                    if st.form_submit_button("Registrar en " + sector_seleccionado, use_container_width=True):
                        if f_prod:
                            f_est = "🚨 BAJO" if f_stock < f_min else "✅ OK"
                            sheet.append_row([f_cat, f_prod, f_stock, f_min, f_est])
                            st.success("Agregado con éxito")
                            st.cache_resource.clear()
                            st.rerun()

st.sidebar.caption(f"Gatica Food v2.1 | {datetime.now().year}")
