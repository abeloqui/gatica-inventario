import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime

st.set_page_config(
    page_title="Gatica Food - Inventario",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📦 Inventario Gatica Food")

# Conexión
@st.cache_resource
def get_sheet():
    creds = Credentials.from_service_account_file(
        "credentials.json", 
        scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    )
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
    return spreadsheet.sheet1

sheet = get_sheet()

def cargar_datos():
    values = sheet.get_all_values()
    if not values or len(values) < 1:
        return pd.DataFrame()
    
    # Tomamos solo las primeras 5 columnas para evitar errores
    clean_values = [row[:5] for row in values]
    headers = [col.strip() for col in clean_values[0]]
    df = pd.DataFrame(clean_values[1:], columns=headers)

    # Normalizar nombres
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

    for col in ['Stock Actual', 'Stock Mínimo']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    return df

# Sidebar
st.sidebar.header("Opciones")
mostrar_solo_bajos = st.sidebar.checkbox("Mostrar solo 🚨 BAJO", value=False)
busqueda = st.sidebar.text_input("Buscar producto", "")

df = cargar_datos()

if busqueda:
    df = df[df['Producto'].str.contains(busqueda, case=False, na=False)]

if mostrar_solo_bajos:
    df = df[df['Stock Actual'] < df['Stock Mínimo']]

st.subheader("Estado actual del inventario")
st.dataframe(df, use_container_width=True, height=600, hide_index=True)

# Actualizar stock
st.subheader("Actualizar Stock")
if not df.empty:
    producto = st.selectbox("Producto", df['Producto'].tolist())
    if producto:
        fila = df[df['Producto'] == producto].iloc[0]
        nuevo = st.number_input("Nuevo Stock Actual", min_value=0, value=int(fila['Stock Actual']))
        if st.button("Guardar Cambio", type="primary"):
            try:
                cell = sheet.find(producto, in_column=2)
                sheet.update_cell(cell.row, 3, nuevo)
                estado = "🚨 BAJO" if nuevo < fila['Stock Mínimo'] else "✅ OK"
                sheet.update_cell(cell.row, 5, estado)
                st.success(f"{producto} actualizado a {nuevo}")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

# Agregar producto
st.subheader("Agregar Nuevo Producto")
with st.form("agregar"):
    col1, col2 = st.columns(2)
    with col1:
        cat = st.text_input("Categoría", "Descartables y Empaques")
        prod = st.text_input("Producto")
    with col2:
        actual = st.number_input("Stock Actual", min_value=0, value=0)
        minimo = st.number_input("Stock Mínimo", min_value=1, value=10)
    
    if st.form_submit_button("Agregar"):
        if prod:
            try:
                estado = "🚨 BAJO" if actual < minimo else "✅ OK"
                sheet.append_row([cat, prod, actual, minimo, estado])
                st.success("Producto agregado")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

st.caption(f"Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")