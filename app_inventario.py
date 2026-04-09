import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import pytz

# --- 0. CONFIGURACIÓN ---
zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
st.set_page_config(page_title="Gatica Food - Inventario", page_icon="📦", layout="wide")

# --- 2. DISEÑO CSS ---
st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    [data-testid="stMetric"] {
        background-color: #ffffff !important;
        padding: 15px !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
    }
    div.stButton > button:first-child { width: 100%; border-radius: 10px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# --- 3. CONEXIÓN ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_all_sheets():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
        
        # Intentamos obtener las hojas necesarias
        try:
            ws_general = spreadsheet.get_worksheet(0)
            ws_cocina = spreadsheet.worksheet("Cocina")
        except:
            st.error("No se encontraron las hojas 'General' o 'Cocina'.")
            return None
            
        try:
            ws_recetas = spreadsheet.worksheet("Recetas")
        except:
            ws_recetas = None # Opcional
            
        return {"General": ws_general, "Cocina": ws_cocina, "Recetas": ws_recetas}
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

# --- 4. PANEL LATERAL ---
with st.sidebar:
    st.title("🍔 Gatica Food")
    sector_seleccionado = st.selectbox("Seleccionar Sector", ["General", "Cocina"])
    st.divider()
    busqueda = st.text_input("🔍 Buscar Producto", "")
    solo_bajos = st.toggle("🚨 Solo alertas críticas", value=False)
    if st.button("🔄 Refrescar Datos"):
        st.cache_resource.clear()
        st.rerun()

# --- 5. PROCESAMIENTO DE DATOS ---
diccionario_hojas = get_all_sheets()
if not diccionario_hojas:
    st.stop()

sheet = diccionario_hojas[sector_seleccionado]
try:
    values = sheet.get_all_values()
    if values and len(values) > 1:
        # Normalización de DataFrame principal
        df_raw = pd.DataFrame(values[1:], columns=[c.strip() for c in values[0]])
        df_raw = df_raw.loc[:, df_raw.columns != ""]
        df_raw.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df_raw.columns]
        
        column_map = {
            'categoria': 'Categoría', 'producto': 'Producto', 
            'stock actual': 'Stock Actual', 'stock minimo': 'Stock Mínimo', 
            'estado': 'Estado', 'unidad': 'Unidad'
        }
        df_raw = df_raw.rename(columns=column_map)
        
        # Convertir a numérico de forma segura
        for col in ['Stock Actual', 'Stock Mínimo']:
            if col in df_raw.columns:
                df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0)
    else:
        df_raw = pd.DataFrame()
except Exception as e:
    st.error(f"Error al procesar la hoja: {e}")
    st.stop()

# --- 6. INTERFAZ PRINCIPAL ---
st.title(f"📦 Inventario: {sector_seleccionado}")
ahora = datetime.now(zona_horaria)

if not df_raw.empty:
    m1, m2, m3 = st.columns(3)
    m1.metric("Productos", len(df_raw))
    bajos_count = len(df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']])
    m2.metric("Alertas", bajos_count, delta=-bajos_count, delta_color="inverse")
    m3.metric("Hora Local", ahora.strftime('%H:%M'))

    tab1, tab2, tab3 = st.tabs(["📋 Lista de Stock", "🍳 Producción", "⚙️ Gestión"])

    with tab1:
        # Aplicar filtros
        df_viz = df_raw.copy()
        if busqueda: 
            df_viz = df_viz[df_viz['Producto'].str.contains(busqueda, case=False)]
        if solo_bajos: 
            df_viz = df_viz[df_viz['Stock Actual'] < df_viz['Stock Mínimo']]
        
        # Estilo de color (Reemplazo de applymap por map/apply para evitar AttributeError)
        def color_critico(row):
            return ['color: red' if row['Stock Actual'] < row['Stock Mínimo'] else 'color: black'] * len(row)

        st.dataframe(df_viz.style.apply(color_critico, axis=1), use_container_width=True, hide_index=True)

    with tab2:
        st.subheader("👨‍🍳 Transformación de Productos")
        if diccionario_hojas.get("Recetas"):
            recetas_raw = diccionario_hojas["Recetas"].get_all_values()
            if len(recetas_raw) > 1:
                df_recetas = pd.DataFrame(recetas_raw[1:], columns=[c.strip() for c in recetas_raw[0]])
                df_recetas.columns = [c.lower().strip().replace('í', 'i').replace('ó', 'o') for c in df_recetas.columns]
                
                # Columnas esperadas: 'producto final', 'ingrediente', 'cantidad'
                if 'producto final' in df_recetas.columns:
                    prod_final_list = df_recetas['producto final'].unique()
                    prod_a_fabricar = st.selectbox("Selecciona qué vas a elaborar", prod_final_list)
                    cant_a_fabricar = st.number_input("¿Cuántas unidades fabricarás?", min_value=0.1, value=1.0, step=1.0)
                    
                    if st.button("Procesar Producción (Descontar Insumos)", type="primary"):
                        ingredientes = df_recetas[df_recetas['producto final'] == prod_a_fabricar]
                        
                        # 1. Descontar Ingredientes
                        for _, row_receta in ingredientes.iterrows():
                            ing_nombre = row_receta['ingrediente']
                            ing_cant_u = float(row_receta['cantidad']) * cant_a_fabricar
                            
                            if ing_nombre in df_raw['Producto'].values:
                                idx = df_raw[df_raw['Producto'] == ing_nombre].index[0]
                                nuevo_st = float(df_raw.at[idx, 'Stock Actual']) - ing_cant_u
                                sheet.update_cell(idx + 2, 3, nuevo_st) # Columna 3 = Stock Actual
                            else:
                                st.warning(f"No se encontró el ingrediente '{ing_nombre}' en {sector_seleccionado}")
                        
                        # 2. Sumar al Producto Final
                        if prod_a_fabricar in df_raw['Producto'].values:
                            idx_f = df_raw[df_raw['Producto'] == prod_a_fabricar].index[0]
                            nuevo_st_f = float(df_raw.at[idx_f, 'Stock Actual']) + cant_a_fabricar
                            sheet.update_cell(idx_f + 2, 3, nuevo_st_f)
                        
                        st.success(f"Se fabricó {cant_a_fabricar} de {prod_a_fabricar}. Insumos descontados.")
                        st.cache_resource.clear()
                        st.rerun()
            else:
                st.info("La hoja 'Recetas' está vacía.")
        else:
            st.warning("Para usar esto, crea una pestaña llamada 'Recetas' con: Producto Final, Ingrediente, Cantidad.")

    with tab3:
        UNIDADES = ["Unidades", "Kg", "Gramos", "Litros", "Cm3", "Pack", "Caja", "Bolsa", "Maples"]
        c_edit, c_new = st.columns(2)

        with c_edit:
            with st.container(border=True):
                st.subheader("📝 Editar Stock")
                prod_sel = st.selectbox("Producto", df_raw['Producto'].tolist(), key="edit_sel")
                if prod_sel:
                    curr = df_raw[df_raw['Producto'] == prod_sel].iloc[0]
                    idx_fila = df_raw[df_raw['Producto'] == prod_sel].index[0] + 2
                    
                    v_st = st.number_input("Stock Actual", value=float(curr['Stock Actual']), step=0.5)
                    v_mi = st.number_input("Mínimo", value=float(curr['Stock Mínimo']), step=0.5)
                    
                    if st.button("Guardar Cambios"):
                        est = "🚨 BAJO" if v_st < v_mi else "✅ OK"
                        # Actualiza C(3), D(4), E(5) -> Stock, Min, Estado
                        sheet.update(range_name=f'C{idx_fila}:E{idx_fila}', values=[[v_st, v_mi, est]])
                        st.cache_resource.clear(); st.rerun()

        with c_new:
            with st.container(border=True):
                st.subheader("➕ Nuevo Producto")
                with st.form("form_nuevo"):
                    f_pr = st.text_input("Nombre del Producto")
                    f_un = st.selectbox("Unidad", UNIDADES)
                    f_st = st.number_input("Stock Inicial", min_value=0.0)
                    f_mi = st.number_input("Mínimo", min_value=0.1, value=1.0)
                    if st.form_submit_button("Agregar al Inventario"):
                        if f_pr:
                            est = "🚨 BAJO" if f_st < f_mi else "✅ OK"
                            sheet.append_row([sector_seleccionado, f_pr, f_st, f_mi, est, f_un])
                            st.cache_resource.clear(); st.rerun()
else:
    st.info("No hay datos disponibles. Verifica tu Google Sheets.")
