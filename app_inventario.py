import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import pytz

# --- 0. CONFIGURACIÓN ---
zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
st.set_page_config(page_title="Gatica Food - Inventario", page_icon="📦", layout="wide")

# Estilos CSS mejorados para móviles
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetric"] {
        background-color: #ffffff;
        padding: 10px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* Hace que los botones sean más fáciles de tocar en móvil */
    .stButton > button {
        height: 3em;
        border-radius: 8px;
    }
    </style>
    """, unsafe_allow_html=True)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_all_sheets():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
        # Intentamos obtener la hoja de Recetas, si no existe, avisamos
        try:
            ws_recetas = spreadsheet.worksheet("Recetas")
        except:
            ws_recetas = None
        return {
            "General": spreadsheet.get_worksheet(0), 
            "Cocina": spreadsheet.worksheet("Cocina"),
            "Recetas": ws_recetas
        }
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

# --- 5. LÓGICA DE DATOS ---
diccionario_hojas = get_all_sheets()
if not diccionario_hojas: st.stop()

# Sidebar
with st.sidebar:
    st.title("🍔 Gatica Food")
    sector_seleccionado = st.selectbox("Sector", ["General", "Cocina"])
    st.divider()
    busqueda = st.text_input("🔍 Buscar", "")
    solo_bajos = st.toggle("🚨 Alertas críticas", value=False)
    if st.button("🔄 Refrescar Pantalla"):
        st.cache_resource.clear()
        st.rerun()

sheet = diccionario_hojas[sector_seleccionado]
values = sheet.get_all_values()

if values and len(values) > 1:
    df_raw = pd.DataFrame(values[1:], columns=[c.strip() for c in values[0]])
    df_raw = df_raw.loc[:, df_raw.columns != ""]
    # Normalización de columnas
    df_raw.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df_raw.columns]
    column_map = {'categoria': 'Categoría', 'producto': 'Producto', 'stock actual': 'Stock Actual', 'stock minimo': 'Stock Mínimo', 'unidad': 'Unidad'}
    df_raw = df_raw.rename(columns=column_map)
    df_raw['Stock Actual'] = pd.to_numeric(df_raw['Stock Actual'], errors='coerce').fillna(0)
    df_raw['Stock Mínimo'] = pd.to_numeric(df_raw['Stock Mínimo'], errors='coerce').fillna(0)
else:
    st.info("No hay datos en esta hoja.")
    st.stop()

# --- 6. INTERFAZ PRINCIPAL ---
ahora = datetime.now(zona_horaria)
st.title(f"📦 {sector_seleccionado}")

# Métricas Responsivas
m1, m2, m3 = st.columns([1,1,1])
m1.metric("Items", len(df_raw))
bajos = len(df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']])
m2.metric("Alertas", bajos, delta=-bajos, delta_color="inverse")
m3.metric("Reloj", ahora.strftime('%H:%M'))

# Tabs para organizar mejor en celular
tab1, tab2, tab3 = st.tabs(["📋 Inventario", "🍳 Producción", "⚙️ Gestión"])

with tab1:
    if busqueda: df_raw = df_raw[df_raw['Producto'].str.contains(busqueda, case=False)]
    if solo_bajos: df_raw = df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']]
    
    # Formateo de color para stock
    def color_stock(val):
        color = 'red' if val < 1 else 'black'
        return f'color: {color}'

    st.dataframe(df_raw.style.applymap(color_stock, subset=['Stock Actual']), 
                 use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Transformar Materia Prima")
    st.info("Aquí puedes crear un producto final (ej: Pizza) y descontar sus ingredientes automáticamente.")
    
    if diccionario_hojas["Recetas"]:
        recetas_raw = diccionario_hojas["Recetas"].get_all_records()
        df_recetas = pd.DataFrame(recetas_raw)
        
        productos_finales = df_recetas['Producto Final'].unique()
        prod_a_fabricar = st.selectbox("¿Qué vas a preparar?", productos_finales)
        cantidad_fab = st.number_input("Cantidad a producir", min_value=1, value=1)
        
        if st.button("Finalizar Producción", type="primary"):
            # Lógica: 1. Buscar ingredientes de la receta
            ingredientes = df_recetas[df_recetas['Producto Final'] == prod_a_fabricar]
            
            # 2. Descontar cada ingrediente en la hoja actual
            error_stock = False
            for _, row in ingredientes.iterrows():
                nombre_ing = row['Ingrediente']
                cant_necesaria = float(row['Cantidad']) * cantidad_fab
                
                # Buscar en el DF actual
                if nombre_ing in df_raw['Producto'].values:
                    idx_df = df_raw[df_raw['Producto'] == nombre_ing].index[0]
                    nuevo_stock = df_raw.at[idx_df, 'Stock Actual'] - cant_necesaria
                    
                    # Actualizar Google Sheets (Fila = index + 2)
                    fila_ing = idx_df + 2
                    # Asumimos que Stock Actual es Columna C (3)
                    sheet.update_cell(fila_ing, 3, nuevo_stock)
                else:
                    st.warning(f"No se encontró el ingrediente: {nombre_ing}")
            
            # 3. Sumar al producto final si existe en el inventario
            if prod_a_fabricar in df_raw['Producto'].values:
                idx_f = df_raw[df_raw['Producto'] == prod_a_fabricar].index[0]
                stock_f = df_raw.at[idx_f, 'Stock Actual'] + cantidad_fab
                sheet.update_cell(idx_f + 2, 3, stock_f)
            
            st.success(f"¡{prod_a_fabricar} producido con éxito! Stock actualizado.")
            st.cache_resource.clear()
            st.rerun()
    else:
        st.warning("Crea una hoja llamada 'Recetas' con columnas: Producto Final, Ingrediente, Cantidad.")

with tab3:
    # Agrupamos Editar y Nuevo en columnas para PC, que se apilan en Móvil
    UNIDADES = ["Unidades", "Kg", "Gramos", "Litros", "Cm3", "Pack", "Caja", "Bolsa"]
    
    col_ed, col_new = st.columns(2)
    
    with col_ed:
        with st.container(border=True):
            st.markdown("### 📝 Editar Stock")
            p_sel = st.selectbox("Producto a editar", df_raw['Producto'].tolist())
            curr_row = df_raw[df_raw['Producto'] == p_sel].iloc[0]
            
            val_st = st.number_input("Nuevo Stock", value=float(curr_row['Stock Actual']))
            if st.button("Actualizar"):
                idx_filla = df_raw[df_raw['Producto'] == p_sel].index[0] + 2
                # Actualizar C (Stock), E (Estado)
                nuevo_estado = "✅ OK" if val_st >= curr_row['Stock Mínimo'] else "🚨 BAJO"
                sheet.update(range_name=f'C{idx_filla}', values=[[val_st]])
                sheet.update_cell(idx_filla, 5, nuevo_estado)
                st.cache_resource.clear(); st.rerun()

    with col_new:
        with st.container(border=True):
            st.markdown("### ➕ Nuevo Item")
            with st.form("nuevo_item"):
                n_nom = st.text_input("Nombre")
                n_cat = st.text_input("Categoría", value=sector_seleccionado)
                n_uni = st.selectbox("Unidad", UNIDADES)
                n_st = st.number_input("Stock Inicial", min_value=0.0)
                n_min = st.number_input("Mínimo", min_value=0.0)
                if st.form_submit_button("Crear"):
                    est = "✅ OK" if n_st >= n_min else "🚨 BAJO"
                    sheet.append_row([n_cat, n_nom, n_st, n_min, est, n_uni])
                    st.cache_resource.clear(); st.rerun()
