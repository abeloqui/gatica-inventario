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
            ws_recetas = None
            
        return {"General": ws_general, "Cocina": ws_cocina, "Recetas": ws_recetas}
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

# --- CARGA DE DATOS ---
diccionario_hojas = get_all_sheets()
if not diccionario_hojas: st.stop()

sector_seleccionado = st.sidebar.selectbox("Seleccionar Sector", ["Cocina", "General"])
sheet = diccionario_hojas[sector_seleccionado]
values = sheet.get_all_values()
df_raw = pd.DataFrame(values[1:], columns=[c.strip() for c in values[0]])
df_raw.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df_raw.columns]
df_raw = df_raw.rename(columns={'producto': 'Producto', 'stock actual': 'Stock Actual'})
df_raw['Stock Actual'] = pd.to_numeric(df_raw['Stock Actual'], errors='coerce').fillna(0)

# --- TABS ---
tab1, tab2, tab3 = st.tabs(["📋 Inventario", "🍳 Transformación de Productos", "⚙️ Gestión"])

with tab2:
    st.subheader("👨‍🍳 Transformación de Productos")
    st.info("Generación de preelaborados y productos finales a partir de materia prima.")

    preelaborados_pedidos = [
        "Masa para Pizza", 
        "Lomos Preparados", 
        "Milanesas de Carne", 
        "Milanesas de Pollo", 
        "Pollo Frito (Marinado)", 
        "Hamburguesas (Medallones)"
    ]

    prod_a_fabricar = st.selectbox("¿Qué vas a preparar hoy?", preelaborados_pedidos)
    cant_a_fabricar = st.number_input(f"Cantidad de {prod_a_fabricar} a producir (en KG)", min_value=0.1, value=1.0, step=0.1)

    # --- RECETAS AJUSTADAS (SIN AGUA) ---
    recetas_internas = {
        "Masa para Pizza": {"Harina": 0.650, "Levadura": 0.010, "Sal": 0.015},
        "Lomos Preparados": {"Carne de Lomo": 1.0, "Condimentos": 0.020},
        "Milanesas de Carne": {"Bola de Lomo": 0.800, "Pan Rallado": 0.200, "Huevo": 0.100},
        "Milanesas de Pollo": {"Pechuga de Pollo": 0.800, "Pan Rallado": 0.200, "Huevo": 0.100},
        "Pollo Frito (Marinado)": {"Pollo Trozado": 1.0, "Rebozador": 0.150},
        "Hamburguesas (Medallones)": {"Carne Picada": 0.950, "Sal": 0.010}
    }

    if prod_a_fabricar in recetas_internas:
        st.write("### 📋 Insumos a descontar:")
        receta = recetas_internas[prod_a_fabricar]
        puedo_fabricar = True
        cambios_stock = []

        for ingrediente, proporcion in receta.items():
            gasto_total = proporcion * cant_a_fabricar
            
            if ingrediente in df_raw['Producto'].values:
                idx = df_raw[df_raw['Producto'] == ingrediente].index[0]
                stock_disponible = float(df_raw.at[idx, 'Stock Actual'])
                
                if stock_disponible < gasto_total:
                    st.error(f"Stock insuficiente: {ingrediente}. (Disponible: {stock_disponible} kg, Necesario: {gasto_total:.3f} kg)")
                    puedo_fabricar = False
                else:
                    st.write(f"- {ingrediente}: **{gasto_total:.3f} kg** (Stock OK)")
                    cambios_stock.append({'idx': idx, 'nuevo_st': stock_disponible - gasto_total})
            else:
                st.warning(f"El ingrediente '{ingrediente}' no se encuentra en el stock de {sector_seleccionado}.")
                puedo_fabricar = False

        if st.button("🚀 Registrar Elaboración", type="primary", disabled=not puedo_fabricar):
            # 1. Descontar materia prima
            for c in cambios_stock:
                sheet.update_cell(c['idx'] + 2, 3, c['nuevo_st'])
            
            # 2. Sumar al preelaborado/producto final
            if prod_a_fabricar in df_raw['Producto'].values:
                idx_f = df_raw[df_raw['Producto'] == prod_a_fabricar].index[0]
                st_prod_actual = float(df_raw.at[idx_f, 'Stock Actual'])
                sheet.update_cell(idx_f + 2, 3, st_prod_actual + cant_a_fabricar)
                
                st.success(f"Se agregaron {cant_a_fabricar} kg a '{prod_a_fabricar}' y se descontaron los insumos.")
                st.cache_resource.clear()
                st.rerun()
            else:
                st.error(f"Error: No existe el producto '{prod_a_fabricar}' en tu lista de stock.")

with tab3:
    st.info("Sección de gestión de inventario y nuevos productos.")
    # Aquí continuaría el resto de tu código de gestión...
