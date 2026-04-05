import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

# 1. DEFINIR SCOPES (Indispensable para evitar el RefreshError)
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

st.set_page_config(page_title="Gatica Food - Inventario", layout="wide")

# 2. FUNCIÓN DE CONEXIÓN ÚNICA Y CACHEADA
@st.cache_resource
def get_sheet():
    # Cargamos desde st.secrets["gsheets"] y LE PASAMOS LOS SCOPES
    creds = Credentials.from_service_account_info(
        st.secrets["gsheets"],
        scopes=SCOPES
    )
    client = gspread.authorize(creds)
    # Usamos tu ID de hoja
    spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
    return spreadsheet.sheet1

# Inicializar la hoja
try:
    sheet = get_sheet()
except Exception as e:
    st.error(f"Error de conexión: {e}")
    st.stop()

st.title("📦 Inventario Gatica Food")

def cargar_datos():
    values = sheet.get_all_values()
    if not values or len(values) < 1:
        return pd.DataFrame()
    
    # Solo tomamos las primeras 5 columnas para evitar errores
    clean_values = [row[:5] for row in values]
    headers = [col.strip() for col in clean_values[0]]
    df = pd.DataFrame(clean_values[1:], columns=headers)

    # Normalizar nombres de columnas
    column_map = {}
    for col in df.columns:
        col_clean = col.strip().lower()
        if col_clean in ['categoría', 'categoria']:
            column_map[col] = 'Categoría'
        elif col_clean in ['producto']:
            column_map[col] = 'Producto'
        elif col_clean in ['stock actual']:
            column_map[col] = 'Stock Actual'
        elif col_clean in ['stock mínimo', 'stock minimo']:
            column_map[col] = 'Stock Mínimo'

    df = df.rename(columns=column_map)

    # Convertir a números
    for col in ['Stock Actual', 'Stock Mínimo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df

# --- SIDEBAR ---
st.sidebar.header("Opciones")
mostrar_solo_bajos = st.sidebar.checkbox("Mostrar solo 🚨 BAJO", value=False)
busqueda = st.sidebar.text_input("Buscar producto", "")

# Carga inicial de datos
df = cargar_datos()

# Aplicar filtros
if not df.empty:
    if busqueda:
        df = df[df['Producto'].str.contains(busqueda, case=False, na=False)]

    if mostrar_solo_bajos:
        if 'Stock Actual' in df.columns and 'Stock Mínimo' in df.columns:
            df = df[df['Stock Actual'] < df['Stock Mínimo']]

# --- CUERPO PRINCIPAL ---
st.subheader("Estado del Inventario")
if not df.empty:
    st.dataframe(
        df,
        use_container_width=True,
        height=400,
        hide_index=True
    )
else:
    st.warning("No se encontraron datos en la hoja o los filtros no coinciden.")

# --- ACTUALIZAR STOCK ---
st.divider()
st.subheader("🔄 Actualizar Stock")
if not df.empty:
    # Usamos una clave única para el selectbox
    producto_sel = st.selectbox("Seleccioná el producto para editar", df['Producto'].tolist(), key="editor_stock")
    if producto_sel:
        fila = df[df['Producto'] == producto_sel].iloc[0]
        
        col_edit1, col_edit2 = st.columns(2)
        with col_edit1:
            nuevo_stock = st.number_input("Nuevo Stock Actual", min_value=0, value=int(fila['Stock Actual']))
        
        if st.button("Guardar Cambio", type="primary"):
            try:
                # Buscar por nombre de producto en la columna B (índice 2)
                cell = sheet.find(producto_sel, in_column=2)
                row_num = cell.row
                
                # Actualizar Stock Actual (Columna 3 / C)
                sheet.update_cell(row_num, 3, nuevo_stock)
                
                # Calcular nuevo estado y actualizar (Columna 5 / E)
                nuevo_estado = "🚨 BAJO" if nuevo_stock < fila['Stock Mínimo'] else "✅ OK"
                sheet.update_cell(row_num, 5, nuevo_estado)
                
                st.success(f"✅ {producto_sel} actualizado!")
                st.cache_resource.clear() # Limpiar cache para forzar recarga
                st.rerun()
            except Exception as e:
                st.error(f"Error al actualizar: {e}")

# --- AGREGAR NUEVO PRODUCTO ---
st.divider()
st.subheader("➕ Agregar Nuevo Producto")
with st.form("agregar"):
    col1, col2 = st.columns(2)
    with col1:
        nueva_cat = st.text_input("Categoría", "Descartables y Empaques")
        nuevo_prod = st.text_input("Nombre del Producto")
    with col2:
        nuevo_stock_ini = st.number_input("Stock Inicial", min_value=0, value=0)
        nuevo_minimo = st.number_input("Stock Mínimo Alert", min_value=1, value=10)
    
    if st.form_submit_button("Registrar Producto"):
        if nuevo_prod:
            try:
                estado_ini = "🚨 BAJO" if nuevo_stock_ini < nuevo_minimo else "✅ OK"
                sheet.append_row([nueva_cat, nuevo_prod, nuevo_stock_ini, nuevo_minimo, estado_ini])
                st.success("¡Producto registrado con éxito!")
                st.cache_resource.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
        else:
            st.warning("El nombre del producto es obligatorio.")

st.sidebar.markdown(f"**Sincronizado:** {datetime.now().strftime('%H:%M:%S')}")
