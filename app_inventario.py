import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import datetime
import pytz
from fpdf import FPDF
import io

# --- 0. CONFIGURACIÓN ---
zona_horaria = pytz.timezone('America/Argentina/Buenos_Aires')
st.set_page_config(page_title="Gatica Food - Sistema Pro", page_icon="🍔", layout="wide")

# --- 1. CLASE PDF PARA TICKETS Y REPORTES ---
class GaticaPDF(FPDF):
    def header(self):
        self.set_font("Arial", 'B', 14)
        self.cell(0, 10, "GATICA FOOD", ln=True, align='C')
        self.set_font("Arial", '', 9)
        self.cell(0, 5, "Gestión de Inventario y Ventas", ln=True, align='C')
        self.ln(5)

def generar_pdf_ticket(items, total, metodo, nro="0001"):
    pdf = GaticaPDF(orientation='P', unit='mm', format=(80, 150))
    pdf.add_page()
    ahora = datetime.now(zona_horaria)
    
    # Resaltado de Fecha y Hora
    pdf.set_fill_color(240, 240, 240)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, f"{ahora.strftime('%d/%m/%Y')} | {ahora.strftime('%H:%M:%S')}", ln=True, align='C', fill=True)
    pdf.ln(3)

    pdf.set_font("Arial", '', 9)
    pdf.cell(0, 5, f"Ticket: {nro}", ln=True)
    pdf.cell(0, 5, f"Pago: {metodo}", ln=True)
    pdf.cell(0, 2, "-"*40, ln=True)

    # Detalle de productos
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(35, 6, "Item", 0)
    pdf.cell(10, 6, "Cant", 0)
    pdf.cell(25, 6, "Total", ln=True, align='R')
    
    pdf.set_font("Arial", '', 9)
    for item in items:
        pdf.cell(35, 6, str(item['nombre'])[:18], 0)
        pdf.cell(10, 6, str(item['cant']), 0)
        pdf.cell(25, 6, f"${item['subtotal']:.2f}", ln=True, align='R')

    pdf.ln(4)
    pdf.set_font("Arial", 'B', 11)
    pdf.cell(0, 10, f"TOTAL: ${total:.2f}", border='T', ln=True, align='R')
    return pdf.output()

# --- 2. CONEXIÓN A GOOGLE SHEETS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def conectar_google_sheets():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
        client = gspread.authorize(creds)
        # ID de tu hoja basado en tu historial
        spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
        return spreadsheet
    except Exception as e:
        st.error(f"Error crítico de conexión: {e}")
        return None

def obtener_hoja_segura(ss, nombre_hoja):
    try:
        return ss.worksheet(nombre_hoja)
    except:
        st.error(f"⚠️ No se encontró la pestaña '{nombre_hoja}'. Revisa el nombre en Google Sheets.")
        return None

def leer_datos_dataframe(ws):
    if ws is None: return pd.DataFrame()
    try:
        # Leemos todo y limpiamos nombres de columnas
        records = ws.get_all_records()
        if not records:
            return pd.DataFrame()
        df = pd.DataFrame(records)
        # Limpieza de espacios en nombres de columnas y datos de texto
        df.columns = [str(c).strip() for c in df.columns]
        df = df.applymap(lambda x: x.strip() if isinstance(x, str) else x)
        return df
    except Exception as e:
        st.error(f"Error al procesar datos: {e}")
        return pd.DataFrame()

# --- 3. LOGICA PRINCIPAL ---
ss = conectar_google_sheets()
if not ss: st.stop()

st.sidebar.title("🍔 Gatica Food")
menu = st.sidebar.radio("Navegación", ["📦 Inventario", "💰 Nueva Venta", "📊 Cierre de Caja"])

# --- SECCIÓN: INVENTARIO ---
if menu == "📦 Inventario":
    st.title("📦 Control de Stock")
    sector_nombre = st.sidebar.selectbox("Seleccionar Sector", ["General", "Cocina"])
    ws_inv = obtener_hoja_segura(ss, sector_nombre)
    df_inv = leer_datos_dataframe(ws_inv)
    
    if not df_inv.empty:
        # Formateo visual
        st.dataframe(df_inv, use_container_width=True, hide_index=True)
    else:
        st.info(f"La hoja '{sector_nombre}' está conectada pero no tiene datos o falta el encabezado.")

# --- SECCIÓN: VENTAS ---
elif menu == "💰 Nueva Venta":
    st.title("💰 Punto de Venta")
    
    # Consolidamos productos de ambos sectores para vender
    df_c = leer_datos_dataframe(obtener_hoja_segura(ss, "Cocina"))
    df_g = leer_datos_dataframe(obtener_hoja_segura(ss, "General"))
    df_todo = pd.concat([df_c, df_g]).drop_duplicates(subset=['Producto']) if not (df_c.empty and df_g.empty) else pd.DataFrame()

    if not df_todo.empty:
        with st.form("form_venta"):
            c1, c2 = st.columns(2)
            with c1:
                producto_v = st.selectbox("Producto", df_todo['Producto'].unique())
                cantidad_v = st.number_input("Cantidad", min_value=1.0, step=1.0, value=1.0)
            with c2:
                precio_v = st.number_input("Precio Unitario ($)", min_value=0.0, step=50.0)
                metodo_v = st.selectbox("Método de Pago", ["Efectivo", "Transferencia", "Tarjeta"])
            
            total_v = cantidad_v * precio_v
            st.markdown(f"### TOTAL A COBRAR: **${total_v:.2f}**")
            
            if st.form_submit_button("✅ Finalizar y Generar Ticket"):
                ahora = datetime.now(zona_horaria)
                ws_ventas = obtener_hoja_segura(ss, "Ventas")
                
                if ws_ventas:
                    # Guardar en Sheets
                    ws_ventas.append_row([
                        ahora.strftime('%d/%m/%Y'), 
                        ahora.strftime('%H:%M'), 
                        producto_v, cantidad_v, total_v, metodo_v
                    ])
                    
                    # Generar Ticket
                    item_ticket = [{'nombre': producto_v, 'cant': cantidad_v, 'subtotal': total_v}]
                    pdf_bytes = generar_pdf_ticket(item_ticket, total_v, metodo_v)
                    
                    st.success("¡Venta registrada!")
                    st.download_button("📥 Descargar Ticket", data=bytes(pdf_bytes), 
                                     file_name=f"ticket_{ahora.strftime('%H%M%S')}.pdf", mime="application/pdf")
    else:
        st.error("No se encontraron productos en 'Cocina' o 'General'. Carga el inventario primero.")

# --- SECCIÓN: CIERRE DE CAJA ---
elif menu == "📊 Cierre de Caja":
    st.title("📊 Reporte de Cierre")
    ws_v = obtener_hoja_segura(ss, "Ventas")
    df_v = leer_datos_dataframe(ws_v)
    
    if not df_v.empty:
        hoy = datetime.now(zona_horaria).strftime('%d/%m/%Y')
        if 'Fecha' in df_v.columns:
            df_hoy = df_v[df_v['Fecha'] == hoy]
            if not df_hoy.empty:
                st.subheader(f"Ventas realizadas hoy ({hoy})")
                st.table(df_hoy)
                
                total_hoy = df_hoy['Total'].sum()
                st.metric("Recaudación Total", f"${total_hoy:.2f}")
                
                # Desglose por método
                st.write("**Resumen por medio de pago:**")
                st.write(df_hoy.groupby('Metodo')['Total'].sum())
            else:
                st.info("No hay ventas registradas con la fecha de hoy.")
        else:
            st.error("La hoja 'Ventas' no tiene una columna llamada 'Fecha'.")
    else:
        st.info("No hay historial de ventas disponible.")
