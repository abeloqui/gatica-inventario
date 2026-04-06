import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import pytz

# 0. CONFIGURACIÓN DE ZONA HORARIA
zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')

# 1. CONFIGURACIÓN DE PÁGINA
st.set_page_config(page_title="Gatica Food - Inventario", page_icon="📦", layout="wide")

# 2. DISEÑO CSS
st.markdown("""
    <style>
    .main { background-color: #f0f2f6; }
    [data-testid="stMetric"] {
        background-color: #ffffff !important;
        padding: 15px !important;
        border-radius: 12px !important;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1) !important;
    }
    div.stButton > button:first-child { width: 100%; border-radius: 10px; font-weight: bold; }
    </style>
    """, unsafe_allow_html=True)

# 3. CONEXIÓN
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_all_sheets():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
        return {"General": spreadsheet.get_worksheet(0), "Cocina": spreadsheet.worksheet("Cocina")}
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

# 4. PANEL LATERAL
with st.sidebar:
    st.title("🍔 Gatica Food")
    sector_seleccionado = st.selectbox("Seleccionar Sector", ["General", "Cocina"])
    st.divider()
    busqueda = st.text_input("🔍 Buscar Producto", "")
    solo_bajos = st.toggle("🚨 Solo alertas críticas", value=False)
    if st.button("🔄 Refrescar Datos"):
        st.cache_resource.clear()
        st.rerun()

# 5. OBTENCIÓN DE DATOS
# --- 5. OBTENCIÓN DE DATOS (VERSIÓN ANTIBLOQUEO) ---
diccionario_hojas = get_all_sheets()
if diccionario_hojas:
    sheet = diccionario_hojas[sector_seleccionado]
    try:
        values = sheet.get_all_values()
        if values and len(values) > 1:
            # 1. Crear el DataFrame inicial
            df_raw = pd.DataFrame(values[1:], columns=[c.strip() for c in values[0]])
            
            # 2. ELIMINAR COLUMNAS TOTALMENTE VACÍAS (A veces gspread trae columnas fantasma)
            df_raw = df_raw.loc[:, df_raw.columns != ""]
            
            # 3. TRATAR COLUMNAS DUPLICADAS (Esto evita el ValueError)
            cols = pd.Series(df_raw.columns)
            for i, col in enumerate(cols):
                if (cols == col).sum() > 1:
                    # Si el nombre está repetido, le agrega un número al final
                    count = (cols[:i] == col).sum()
                    if count > 0:
                        cols[i] = f"{col}_{count}"
            df_raw.columns = cols

            # 4. Normalización de nombres para la lógica interna
            df_raw.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df_raw.columns]
            
            # Mapeo de columnas a nombres bonitos
            column_map = {
                'categoria': 'Categoría', 
                'producto': 'Producto', 
                'stock actual': 'Stock Actual', 
                'stock minimo': 'Stock Mínimo', 
                'estado': 'Estado', 
                'unidad': 'Unidad'
            }
            df_raw = df_raw.rename(columns=column_map)
            
            # 5. Convertir a numérico
            for col in ['Stock Actual', 'Stock Mínimo']:
                if col in df_raw.columns:
                    df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0)
        else:
            df_raw = pd.DataFrame()
    except Exception as e:
        st.error(f"Error crítico al procesar columnas: {e}")
        st.stop()
else:
    st.stop()
# 6. INTERFAZ
st.title(f"📦 Inventario: {sector_seleccionado}")
ahora = datetime.now(zona_horaria)

if not df_raw.empty:
    col1, col2, col3 = st.columns(3)
    col1.metric("Productos", len(df_raw))
    bajos = len(df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']])
    col2.metric("Alertas", bajos, delta=-bajos, delta_color="inverse")
    col3.metric("Hora Local", ahora.strftime('%H:%M'))

    with st.expander("📊 Gráfico de Stock", expanded=True):
        df_p = df_raw.copy().sort_values('Stock Actual').head(15)
        st.bar_chart(df_p.set_index('Producto')[['Stock Actual', 'Stock Mínimo']])

    df_viz = df_raw.copy()
    if busqueda: df_viz = df_viz[df_viz['Producto'].str.contains(busqueda, case=False)]
    if solo_bajos: df_viz = df_viz[df_viz['Stock Actual'] < df_viz['Stock Mínimo']]
    st.dataframe(df_viz, use_container_width=True, hide_index=True)

    st.divider()

    # 7. ACCIONES
    UNIDADES = ["Unidades", "Kg", "Gramos", "Litros", "Cm3", "Pack", "Caja", "Bolsa", "Atado", "Cajon", "Tacho", "Barra", "Sache", "Maples"]
    c_edit, c_new = st.columns(2)

    with c_edit:
        with st.container(border=True):
            st.subheader("📝 Editar")
            prod_sel = st.selectbox("Producto", df_raw['Producto'].tolist(), key="ed")
            if prod_sel:
                curr = df_raw[df_raw['Producto'] == prod_sel].iloc[0]
                idx_filla = df_raw[df_raw['Producto'] == prod_sel].index[0] + 2
                
                ce1, ce2 = st.columns(2)
                v_st = ce1.number_input("Stock", value=float(curr['Stock Actual']), step=0.25)
                v_mi = ce2.number_input("Mínimo", value=float(curr['Stock Mínimo']), step=0.25)
                
                # Manejo de error de columna 'Unidad'
                u_val = curr.get('Unidad', "Unidades")
                u_idx = UNIDADES.index(u_val) if u_val in UNIDADES else 0
                v_un = st.selectbox("Unidad", UNIDADES, index=u_idx)
                
                if st.button("Guardar", type="primary"):
                    est = "🚨 BAJO" if v_st < v_mi else "✅ OK"
                    sheet.update(range_name=f'C{idx_filla}:F{idx_filla}', values=[[v_st, v_mi, est, v_un]])
                    st.cache_resource.clear(); st.rerun()

    with c_new:
        with st.container(border=True):
            st.subheader("➕ Nuevo")
            with st.form("f_new", clear_on_submit=True):
                f_pr = st.text_input("Nombre")
                f_ca = st.text_input("Categoría", value=sector_seleccionado)
                f_un = st.selectbox("Unidad", UNIDADES)
                c_n1, c_n2 = st.columns(2)
                f_st = c_n1.number_input("Stock", min_value=0.0, step=0.5)
                f_mi = c_n2.number_input("Mínimo", min_value=0.1, value=1.0, step=0.5)
                if st.form_submit_button("Agregar"):
                    if f_pr:
                        est = "🚨 BAJO" if f_st < f_mi else "✅ OK"
                        sheet.append_row([f_ca, f_pr, f_st, f_mi, est, f_un])
                        st.cache_resource.clear(); st.rerun()
else:
    st.info("No hay datos.")
