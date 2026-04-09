import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import pytz
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# --- 0. CONFIGURACIÓN ---
zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
st.set_page_config(page_title="Gatica Food - Inventario", page_icon="📦", layout="wide")

# --- 1. CONFIG EMAIL (agregá esto en secrets.toml) ---
# [email]
# sender = "tucorreo@gmail.com"
# password = "tu-app-password-de-16-digitos"
# receiver = "correo-para-alertas@gmail.com"

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

# --- 3. CONEXIÓN A GOOGLE SHEETS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_all_sheets():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
        
        ws_general = spreadsheet.worksheet("General")
        ws_cocina = spreadsheet.worksheet("Cocina")
        
        # Crear hoja Movimientos si no existe
        try:
            ws_mov = spreadsheet.worksheet("Movimientos")
        except:
            ws_mov = spreadsheet.add_worksheet(title="Movimientos", rows=1000, cols=10)
            ws_mov.append_row(["Fecha", "Tipo", "Producto", "Cantidad", "Sector", "Usuario", "Notas"])
        
        try:
            ws_recetas = spreadsheet.worksheet("Recetas")
        except:
            ws_recetas = None
            
        return {
            "General": ws_general,
            "Cocina": ws_cocina,
            "Recetas": ws_recetas,
            "Movimientos": ws_mov
        }
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

# --- 4. REGISTRO GLOBAL DE PRODUCTOS ---
def get_product_registry(sheets_dict):
    registry = {}
    for sector, ws in sheets_dict.items():
        if sector in ["Recetas", "Movimientos"] or not ws:
            continue
        try:
            values = ws.get_all_values()
            if len(values) <= 1:
                continue
            headers = [c.strip().lower().replace('í', 'i').replace('ó', 'o') for c in values[0]]
            try:
                col_prod = headers.index("producto")
            except ValueError:
                continue
                
            for r_idx, row in enumerate(values[1:], start=2):
                if len(row) > col_prod:
                    prod_name = str(row[col_prod]).strip()
                    if prod_name:
                        key = prod_name.lower().strip()
                        registry[key] = {
                            'worksheet': ws,
                            'row': r_idx,
                            'sector': sector
                        }
        except Exception as e:
            st.warning(f"Error indexando {sector}: {e}")
    return registry

# --- 5. FUNCIÓN PARA ENVIAR EMAIL DE ALERTA ---
def enviar_alerta_email(producto, stock_actual, stock_minimo, sector):
    try:
        if "email" not in st.secrets:
            return False
        sender = st.secrets.email.sender
        password = st.secrets.email.password
        receiver = st.secrets.email.receiver
        
        msg = MIMEMultipart()
        msg['From'] = sender
        msg['To'] = receiver
        msg['Subject'] = f"🚨 ALERTA CRÍTICA - {producto}"
        
        body = f"""
        <h2>Alerta de Stock Crítico</h2>
        <p><strong>Producto:</strong> {producto}</p>
        <p><strong>Sector:</strong> {sector}</p>
        <p><strong>Stock Actual:</strong> {stock_actual}</p>
        <p><strong>Stock Mínimo:</strong> {stock_minimo}</p>
        <p><strong>Hora:</strong> {datetime.now(zona_horaria).strftime('%d/%m/%Y %H:%M')}</p>
        <p>Por favor, revisar inventario lo antes posible.</p>
        """
        msg.attach(MIMEText(body, 'html'))
        
        with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
            server.login(sender, password)
            server.sendmail(sender, receiver, msg.as_string())
        return True
    except Exception as e:
        st.warning(f"No se pudo enviar email: {e}")
        return False

# --- 6. PANEL LATERAL ---
with st.sidebar:
    st.title("🍔 Gatica Food")
    sector_seleccionado = st.selectbox("Seleccionar Sector", ["General", "Cocina"])
    st.divider()
    busqueda = st.text_input("🔍 Buscar Producto", "")
    solo_bajos = st.toggle("🚨 Solo alertas críticas", value=False)
    if st.button("🔄 Refrescar Datos"):
        st.cache_resource.clear()
        st.rerun()

# --- 7. PROCESAMIENTO ---
diccionario_hojas = get_all_sheets()
if not diccionario_hojas:
    st.stop()

product_registry = get_product_registry(diccionario_hojas)

sheet = diccionario_hojas[sector_seleccionado]

try:
    values = sheet.get_all_values()
    if values and len(values) > 1:
        df_raw = pd.DataFrame(values[1:], columns=[c.strip() for c in values[0]])
        df_raw = df_raw.loc[:, df_raw.columns != ""]
        df_raw.columns = [c.replace('í', 'i').replace('ó', 'o').strip().lower() for c in df_raw.columns]
        
        column_map = {
            'categoria': 'Categoría', 'producto': 'Producto',
            'stock actual': 'Stock Actual', 'stock minimo': 'Stock Mínimo',
            'estado': 'Estado', 'unidad': 'Unidad'
        }
        df_raw = df_raw.rename(columns=column_map)
        
        for col in ['Stock Actual', 'Stock Mínimo']:
            if col in df_raw.columns:
                df_raw[col] = pd.to_numeric(df_raw[col], errors='coerce').fillna(0)
    else:
        df_raw = pd.DataFrame()
except Exception as e:
    st.error(f"Error al procesar la hoja: {e}")
    st.stop()

# --- 8. INTERFAZ PRINCIPAL ---
st.title(f"📦 Inventario: {sector_seleccionado}")
ahora = datetime.now(zona_horaria)

if not df_raw.empty:
    m1, m2, m3 = st.columns(3)
    m1.metric("Productos", len(df_raw))
    bajos_count = len(df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']])
    m2.metric("Alertas", bajos_count, delta=-bajos_count, delta_color="inverse")
    m3.metric("Hora Local", ahora.strftime('%H:%M'))
    
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Lista de Stock", "🍳 Producción", "📥 Entrada Mercadería", "⚙️ Gestión"])
    
    with tab1:
        df_viz = df_raw.copy()
        if busqueda:
            df_viz = df_viz[df_viz['Producto'].str.contains(busqueda, case=False)]
        if solo_bajos:
            df_viz = df_viz[df_viz['Stock Actual'] < df_viz['Stock Mínimo']]
        
        def color_critico(row):
            return ['color: red' if row['Stock Actual'] < row['Stock Mínimo'] else 'color: black'] * len(row)
        
        st.dataframe(df_viz.style.apply(color_critico, axis=1), use_container_width=True, hide_index=True)
    
    with tab2:  # Producción mejorada
        st.subheader("👨‍🍳 Producción de Pre-Elaborados")
        if not diccionario_hojas.get("Recetas"):
            st.warning("Crea una pestaña 'Recetas' con columnas: Producto Final | Ingrediente | Cantidad")
        else:
            recetas_raw = diccionario_hojas["Recetas"].get_all_values()
            if len(recetas_raw) > 1:
                df_recetas = pd.DataFrame(recetas_raw[1:], columns=[c.strip() for c in recetas_raw[0]])
                df_recetas.columns = [c.lower().strip().replace('í','i').replace('ó','o') for c in df_recetas.columns]
                
                if 'producto final' in df_recetas.columns and 'ingrediente' in df_recetas.columns and 'cantidad' in df_recetas.columns:
                    prod_final_list = sorted(df_recetas['producto final'].unique())
                    prod_a_fabricar = st.selectbox("Qué vas a elaborar", prod_final_list)
                    cant_a_fabricar = st.number_input("Cantidad a fabricar", min_value=0.1, value=1.0, step=0.5)
                    
                    # Previsualización
                    ingredientes = df_recetas[df_recetas['producto final'] == prod_a_fabricar]
                    st.subheader("Ingredientes requeridos")
                    preview = []
                    puede_producir = True
                    
                    for _, row_r in ingredientes.iterrows():
                        ing = str(row_r['ingrediente']).strip()
                        key = ing.lower().strip()
                        req = float(row_r['cantidad']) * cant_a_fabricar
                        
                        if key in product_registry:
                            info = product_registry[key]
                            try:
                                stock_act = float(info['worksheet'].cell(info['row'], 3).value or 0)
                            except:
                                stock_act = 0
                            suficiente = stock_act >= req
                            if not suficiente:
                                puede_producir = False
                            preview.append({"Ingrediente": ing, "Requerido": req, "Stock Actual": stock_act, "OK": "✅" if suficiente else "❌"})
                        else:
                            puede_producir = False
                            preview.append({"Ingrediente": ing, "Requerido": req, "Stock Actual": "NO ENCONTRADO", "OK": "❌"})
                    
                    st.dataframe(pd.DataFrame(preview), use_container_width=True, hide_index=True)
                    
                    if st.button("🚀 Procesar Producción", type="primary", disabled=not puede_producir):
                        if not puede_producir:
                            st.error("No hay stock suficiente para producir")
                        else:
                            # Descontar insumos + registrar movimiento
                            for _, row_r in ingredientes.iterrows():
                                ing = str(row_r['ingrediente']).strip()
                                key = ing.lower().strip()
                                cant_descontar = float(row_r['cantidad']) * cant_a_fabricar
                                info = product_registry[key]
                                ws = info['worksheet']
                                row = info['row']
                                
                                stock_act = float(ws.cell(row, 3).value or 0)
                                stock_min = float(ws.cell(row, 4).value or 0)
                                nuevo_stock = stock_act - cant_descontar
                                nuevo_estado = "🚨 BAJO" if nuevo_stock < stock_min else "✅ OK"
                                
                                ws.update(f'C{row}:E{row}', [[nuevo_stock, stock_min, nuevo_estado]])
                                
                                # Registrar movimiento
                                diccionario_hojas["Movimientos"].append_row([
                                    datetime.now(zona_horaria).strftime("%d/%m/%Y %H:%M"),
                                    "Salida Producción",
                                    ing,
                                    -cant_descontar,
                                    info['sector'],
                                    "Sistema",
                                    f"Producción de {cant_a_fabricar} {prod_a_fabricar}"
                                ])
                                
                                if nuevo_stock < stock_min:
                                    enviar_alerta_email(ing, nuevo_stock, stock_min, info['sector'])
                            
                            # Sumar producto final
                            key_f = prod_a_fabricar.lower().strip()
                            if key_f in product_registry:
                                info_f = product_registry[key_f]
                                ws_f = info_f['worksheet']
                                row_f = info_f['row']
                                stock_act_f = float(ws_f.cell(row_f, 3).value or 0)
                                stock_min_f = float(ws_f.cell(row_f, 4).value or 0)
                                nuevo_f = stock_act_f + cant_a_fabricar
                                nuevo_est_f = "🚨 BAJO" if nuevo_f < stock_min_f else "✅ OK"
                                ws_f.update(f'C{row_f}:E{row_f}', [[nuevo_f, stock_min_f, nuevo_est_f]])
                                
                                # Movimiento entrada
                                diccionario_hojas["Movimientos"].append_row([
                                    datetime.now(zona_horaria).strftime("%d/%m/%Y %H:%M"),
                                    "Entrada Producción",
                                    prod_a_fabricar,
                                    cant_a_fabricar,
                                    info_f['sector'],
                                    "Sistema",
                                    f"Fabricación de {cant_a_fabricar} unidades"
                                ])
                            
                            st.success(f"✅ Producción completada: {cant_a_fabricar} × {prod_a_fabricar}")
                            st.cache_resource.clear()
                            st.rerun()
                else:
                    st.error("Faltan columnas en Recetas")
            else:
                st.info("Hoja Recetas vacía")
    
    with tab3:  # Entrada de mercadería rápida
        st.subheader("📥 Entrada de Mercadería")
        prod_list = sorted(df_raw['Producto'].tolist())
        prod_entrada = st.selectbox("Producto que entra", prod_list, key="entrada_prod")
        
        cant_entrada = st.number_input("Cantidad recibida", min_value=0.1, value=1.0, step=0.5)
        notas = st.text_input("Notas (proveedor, lote, etc.)", "")
        
        if st.button("✅ Registrar Entrada", type="primary"):
            if prod_entrada and cant_entrada > 0:
                key = prod_entrada.lower().strip()
                if key in product_registry:
                    info = product_registry[key]
                    ws = info['worksheet']
                    row = info['row']
                    
                    stock_act = float(ws.cell(row, 3).value or 0)
                    stock_min = float(ws.cell(row, 4).value or 0)
                    nuevo_stock = stock_act + cant_entrada
                    nuevo_estado = "🚨 BAJO" if nuevo_stock < stock_min else "✅ OK"
                    
                    ws.update(f'C{row}:E{row}', [[nuevo_stock, stock_min, nuevo_estado]])
                    
                    # Registrar movimiento
                    diccionario_hojas["Movimientos"].append_row([
                        datetime.now(zona_horaria).strftime("%d/%m/%Y %H:%M"),
                        "Entrada Mercadería",
                        prod_entrada,
                        cant_entrada,
                        info['sector'],
                        "Usuario",
                        notas
                    ])
                    
                    st.success(f"Entrada registrada: +{cant_entrada} de {prod_entrada}")
                    st.cache_resource.clear()
                    st.rerun()
    
    with tab4:  # Gestión (editar + nuevo)
        UNIDADES = ["Unidades", "Kg", "Gramos", "Litros", "Cm3", "Pack", "Caja", "Bolsa", "Maples"]
        c_edit, c_new = st.columns(2)
        
        with c_edit:
            st.subheader("📝 Editar Stock")
            prod_sel = st.selectbox("Producto", df_raw['Producto'].tolist(), key="edit_sel")
            if prod_sel:
                curr = df_raw[df_raw['Producto'] == prod_sel].iloc[0]
                idx_fila = df_raw[df_raw['Producto'] == prod_sel].index[0] + 2
                
                v_st = st.number_input("Stock Actual", value=float(curr['Stock Actual']), step=0.5)
                v_mi = st.number_input("Mínimo", value=float(curr['Stock Mínimo']), step=0.5)
                
                if st.button("Guardar Cambios"):
                    est = "🚨 BAJO" if v_st < v_mi else "✅ OK"
                    sheet.update(range_name=f'C{idx_fila}:E{idx_fila}', values=[[v_st, v_mi, est]])
                    st.cache_resource.clear()
                    st.rerun()
        
        with c_new:
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
                        st.cache_resource.clear()
                        st.rerun()
else:
    st.info("No hay datos disponibles.")

# --- FIN ---
st.caption("Sistema de Inventario Gatica Food v2.0 - Stock Robusto")
