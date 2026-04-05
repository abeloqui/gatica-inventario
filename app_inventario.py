import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import pytz

# 0. CONFIGURACIÓN DE ZONA HORARIA
zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires') # GMT-3

# 1. CONFIGURACIÓN DE PÁGINA
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
    div.stButton > button:first-child { width: 100%; border-radius: 10px; height: 3.5em; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# 3. CONEXIÓN Y SCOPES
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_all_sheets():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
        return {
            "General": spreadsheet.get_worksheet(0),
            "Cocina": spreadsheet.worksheet("Cocina")
        }
    except Exception as e:
        st.error(f"Error de autenticación: {e}")
        return None

# 4. PANEL LATERAL
with st.sidebar:
    st.title("🍔 Gatica Food")
    st.subheader("Panel de Control")
    sector_seleccionado = st.selectbox("Seleccionar Sector", ["General", "Cocina"])
    st.divider()
    busqueda = st.text_input("🔍 Buscar Producto", "")
    solo_bajos = st.toggle("🚨 Solo alertas críticas", value=False)
    
    if st.button("🔄 Refrescar Datos", type="secondary"):
        st.cache_resource.clear()
        st.rerun()

# 5. OBTENCIÓN DE DATOS (Actualizado para 6 columnas: Cat, Prod, Stock, Min, Estado, Unidad)
diccionario_hojas = get_all_sheets()
if diccionario_hojas:
    sheet = diccionario_hojas[sector_seleccionado]
    try:
        values = sheet.get_all_values()
        if values and len(values) > 1:
            # Tomamos hasta la columna 6 (F)
            clean_values = [row[:6] for row in values]
            df_raw = pd.DataFrame(clean_values[1:], columns=[c.strip() for c in clean_values[0]])
            
            # Normalización de nombres de columnas
            df_raw.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df_raw.columns]
            column_map = {
                'categoria': 'Categoría', 
                'producto': 'Producto', 
                'stock actual': 'Stock Actual', 
                'stock minimo': 'Stock Mínimo', 
                'estado': 'Estado',
                'unidad': 'Unidad' # Nueva columna
            }
            df_raw = df_raw.rename(columns=column_map)
            
            for col in ['Stock Actual', 'Stock Mínimo']:
                df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0).astype(int)
        else:
            df_raw = pd.DataFrame()
    except Exception as e:
        st.error(f"Error al leer datos: {e}")
        st.stop()
else:
    st.stop()

# 6. INTERFAZ PRINCIPAL
st.title(f"📦 Inventario: {sector_seleccionado}")
ahora_gmt3 = datetime.now(zona_horaria)

if not df_raw.empty:
    # --- MÉTRICAS ---
    t1, t2, t3 = st.columns(3)
    t1.metric("Productos Total", len(df_raw))
    alertas_df = df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']]
    t2.metric("Alertas Críticas", len(alertas_df), delta=len(alertas_df), delta_color="inverse")
    t3.metric("Sincronizado (GMT-3)", ahora_gmt3.strftime('%H:%M'))

    # --- GRÁFICA ---
    with st.expander("📊 Visualización de Stock Crítico", expanded=True):
        df_plot = df_raw.copy()
        df_plot['Disponibilidad'] = df_plot['Stock Actual'] - df_plot['Stock Mínimo']
        df_plot = df_plot.sort_values(by='Disponibilidad').head(15)
        st.bar_chart(df_plot.set_index('Producto')[['Stock Actual', 'Stock Mínimo']])

    # --- TABLA DE DATOS ---
    df_display = df_raw.copy()
    if busqueda: 
        df_display = df_display[df_display['Producto'].str.contains(busqueda, case=False)]
    if solo_bajos: 
        df_display = df_display[df_display['Stock Actual'] < df_display['Stock Mínimo']]

    st.subheader("Lista de Productos")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.divider()

    # 7. ACCIONES
    col_edit, col_new = st.columns(2)
    UNIDADES_MEDIDA = ["Unidades", "Kg", "Gramos", "Litros", "Cm3", "Pack", "Caja"]

    with col_edit:
        with st.container(border=True):
            st.subheader("📝 Editar / Eliminar")
            prod_nombres = df_raw['Producto'].tolist()
            mapa_filas = {nombre: idx + 2 for idx, nombre in enumerate(prod_nombres)}
            prod_sel = st.selectbox("Seleccionar producto", prod_nombres, key="edit_box")
            
            if prod_sel:
                curr = df_raw[df_raw['Producto'] == prod_sel].iloc[0]
                
                c1, c2 = st.columns(2)
                n_stock = c1.number_input("Stock Actual", value=int(curr['Stock Actual']), key="n_st")
                n_min = c2.number_input("Stock Mínimo", value=int(curr['Stock Mínimo']), key="n_mi")
                
                # Para editar la unidad si te equivocaste
                u_idx = UNIDADES_MEDIDA.index(curr['Unidad']) if curr['Unidad'] in UNIDADES_MEDIDA else 0
                n_uni = st.selectbox("Unidad de Medida", UNIDADES_MEDIDA, index=u_idx, key="n_uni")
                
                c_up, c_del = st.columns([2,1])
                row_idx = mapa_filas[prod_sel]

                if c_up.button("Actualizar Todo", type="primary"):
                    with st.spinner("Guardando..."):
                        nuevo_estado = "🚨 BAJO" if n_stock < n_min else "✅ OK"
                        # Actualizamos Rango C:F (Stock, Min, Estado, Unidad)
                        sheet.update(range_name=f'C{row_idx}:F{row_idx}', 
                                     values=[[n_stock, n_min, nuevo_estado, n_uni]])
                        st.toast(f"¡{prod_sel} actualizado!", icon="✅")
                        st.cache_resource.clear()
                        st.rerun()

                with c_del.popover("🗑️"):
                    if st.button("Confirmar Borrado"):
                        sheet.delete_rows(row_idx)
                        st.cache_resource.clear()
                        st.rerun()

    with col_new:
        with st.container(border=True):
            st.subheader("➕ Nuevo Registro")
            with st.form("form_nuevo", clear_on_submit=True):
                f_prod = st.text_input("Nombre del Producto (ej: Harina 000)")
                f_cat = st.text_input("Categoría", value=sector_seleccionado)
                
                c3, c4 = st.columns(2)
                f_st = c3.number_input("Stock Inicial", min_value=0, value=0)
                f_mi = c4.number_input("Mínimo", min_value=1, value=10)
                
                f_uni = st.selectbox("Unidad de Medida", UNIDADES_MEDIDA)
                
                if st.form_submit_button("Registrar Producto"):
                    if f_prod:
                        est = "🚨 BAJO" if f_st < f_mi else "✅ OK"
                        # Orden: Categoría, Producto, Stock, Mínimo, Estado, Unidad
                        sheet.append_row([f_cat, f_prod, f_st, f_mi, est, f_uni])
                        st.toast("Producto cargado correctamente", icon="🚀")
                        st.cache_resource.clear()
                        st.rerun()
                    else:
                        st.warning("El nombre es obligatorio")

else:
    st.info(f"La hoja '{sector_seleccionado}' no tiene datos.")

st.sidebar.caption(f"Gatica Food v2.7 | {ahora_gmt3.strftime('%d/%m/%Y %H:%M')}")
