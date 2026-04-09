import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import pytz

# --- 0. CONFIGURACIÓN ---
zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
st.set_page_config(page_title="Gatica Food - Inventario", page_icon="📦", layout="wide")

# --- 3. CONEXIÓN (CON TU ID ORIGINAL) ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_all_sheets():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
        
        ws_general = spreadsheet.get_worksheet(0)
        ws_cocina = spreadsheet.worksheet("Cocina")
        try:
            ws_recetas = spreadsheet.worksheet("Recetas")
        except:
            ws_recetas = None # Si no existe, avisamos después
            
        return {"General": ws_general, "Cocina": ws_cocina, "Recetas": ws_recetas}
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

# --- CARGA DE DATOS ---
diccionario_hojas = get_all_sheets()
if not diccionario_hojas: st.stop()

with st.sidebar:
    st.title("🍔 Gatica Food")
    sector_seleccionado = st.selectbox("Seleccionar Sector", ["Cocina", "General"])
    busqueda = st.text_input("🔍 Buscar Producto")
    if st.button("🔄 Refrescar Datos"):
        st.cache_resource.clear()
        st.rerun()

sheet = diccionario_hojas[sector_seleccionado]
values = sheet.get_all_values()
df_raw = pd.DataFrame(values[1:], columns=[c.strip() for c in values[0]])
df_raw.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df_raw.columns]

# Renombrar para consistencia
column_map = {'producto': 'Producto', 'stock actual': 'Stock Actual', 'stock minimo': 'Stock Mínimo'}
df_raw = df_raw.rename(columns=column_map)
df_raw['Stock Actual'] = pd.to_numeric(df_raw['Stock Actual'], errors='coerce').fillna(0)

# --- INTERFAZ ---
tab1, tab2, tab3 = st.tabs(["📋 Inventario", "🍳 Producción (Preelaborados y Final)", "⚙️ Gestión"])

with tab1:
    st.dataframe(df_raw, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("👨‍🍳 Transformación de Productos")
    st.write("Aquí puedes fabricar un **Preelaborado** (ej. Masa) o un **Producto Final** (ej. Pizza en caja).")
    
    if diccionario_hojas["Recetas"]:
        rec_values = diccionario_hojas["Recetas"].get_all_values()
        df_recetas = pd.DataFrame(rec_values[1:], columns=[c.strip() for c in rec_values[0]])
        df_recetas.columns = [c.lower().strip() for c in df_recetas.columns]
        
        # 1. Seleccionar qué vamos a fabricar
        lista_elaborables = df_recetas['producto final'].unique()
        prod_a_fabricar = st.selectbox("¿Qué vas a preparar hoy?", lista_elaborables)
        cant_a_fabricar = st.number_input("Cantidad de unidades", min_value=1.0, value=1.0)
        
        # Mostrar qué se va a descontar
        ingredientes = df_recetas[df_recetas['producto final'] == prod_a_fabricar]
        st.write("**Se descontará del stock:**")
        for _, row in ingredientes.iterrows():
            st.caption(f"• {row['ingrediente']}: {float(row['cantidad']) * cant_a_fabricar}")

        if st.button("✅ Registrar Producción", type="primary"):
            puedo_fabricar = True
            cambios_stock = []

            # Verificar si tenemos todo (materia prima o preelaborados previos)
            for _, row_r in ingredientes.iterrows():
                nom_ing = row_r['ingrediente']
                cant_total = float(row_r['cantidad']) * cant_a_fabricar
                
                if nom_ing in df_raw['Producto'].values:
                    idx = df_raw[df_raw['Producto'] == nom_ing].index[0]
                    stock_actual = float(df_raw.at[idx, 'Stock Actual'])
                    
                    if stock_actual < cant_total:
                        st.error(f"Stock insuficiente de {nom_ing}. Tienes {stock_actual}, necesitas {cant_total}")
                        puedo_fabricar = False
                        break
                    cambios_stock.append({'idx': idx, 'nuevo_st': stock_actual - cant_total})
            
            if puedo_fabricar:
                # A. Descontamos los ingredientes/descartables
                for c in cambios_stock:
                    sheet.update_cell(c['idx'] + 2, 3, c['nuevo_st'])
                
                # B. Sumamos al producto que acabamos de fabricar (sea preelaborado o final)
                if prod_a_fabricar in df_raw['Producto'].values:
                    idx_f = df_raw[df_raw['Producto'] == prod_a_fabricar].index[0]
                    nuevo_st_f = float(df_raw.at[idx_f, 'Stock Actual']) + cant_a_fabricar
                    sheet.update_cell(idx_f + 2, 3, nuevo_st_f)
                
                st.success(f"¡Listo! Se fabricaron {cant_a_fabricar} de {prod_a_fabricar}")
                st.cache_resource.clear()
                st.rerun()
    else:
        st.error("No se encontró la pestaña 'Recetas' en el Drive.")

with tab3:
    st.info("Aquí va tu sección de Editar Stock y Nuevo Producto que ya tenías.")
