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
st.set_page_config(page_title="Gatica Food - Sistema Integral", page_icon="🍔", layout="wide")

# --- 1. LÓGICA DE PDF (TICKETS Y REPORTES) ---
class PDF(FPDF):
    def header(self):
        self.set_font("Arial", 'B', 12)
        self.cell(0, 8, "GATICA FOOD", ln=True, align='C')
        self.set_font("Arial", '', 8)
        self.cell(0, 4, "Sistema de Gestión de Inventario y Ventas", ln=True, align='C')
        self.ln(5)

def generar_ticket_venta(items, total, metodo, nro_venta="0001"):
    pdf = PDF(orientation='P', unit='mm', format=(80, 150))
    pdf.add_page()
    ahora = datetime.now(zona_horaria)
    
    # Fecha y Hora Resaltadas
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(0, 8, f"{ahora.strftime('%d/%m/%Y')} | {ahora.strftime('%H:%M:%S')}", ln=True, align='C', fill=True)
    pdf.ln(3)

    pdf.set_font("Arial", '', 8)
    pdf.cell(0, 4, f"Ticket Nro: {nro_venta}", ln=True)
    pdf.cell(0, 4, f"Método de Pago: {metodo}", ln=True)
    pdf.cell(0, 2, "-"*40, ln=True)

    # Detalle
    pdf.set_font("Arial", 'B', 8)
    pdf.cell(35, 5, "Item", 0)
    pdf.cell(10, 5, "Cant", 0)
    pdf.cell(20, 5, "Subtotal", ln=True, align='R')
    
    pdf.set_font("Arial", '', 8)
    for item in items:
        pdf.cell(35, 5, item['nombre'][:18], 0)
        pdf.cell(10, 5, str(item['cant']), 0)
        pdf.cell(20, 5, f"${item['subtotal']:.2f}", ln=True, align='R')

    pdf.ln(2)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, f"TOTAL: ${total:.2f}", border='T', ln=True, align='R')
    return pdf.output()

def generar_reporte_cierre(df_ventas, total_dia, metodo_stats):
    pdf = PDF(orientation='P', unit='mm', format='A4')
    pdf.add_page()
    ahora = datetime.now(zona_horaria)
    
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(0, 10, "REPORTE DE CIERRE DE CAJA", ln=True, align='C')
    
    pdf.set_fill_color(52, 73, 94)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, f"DIA: {ahora.strftime('%d/%m/%Y')} | CIERRE: {ahora.strftime('%H:%M')}", ln=True, align='C', fill=True)
    
    pdf.set_text_color(0, 0, 0)
    pdf.ln(10)

    # Resumen por método
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(0, 10, "Resumen por Método de Pago:", ln=True)
    pdf.set_font("Arial", '', 11)
    for metodo, monto in metodo_stats.items():
        pdf.cell(50, 8, f"- {metodo}:", 0)
        pdf.cell(0, 8, f"${monto:.2f}", ln=True)
    
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(0, 12, f"TOTAL RECAUDADO: ${total_dia:.2f}", border='TB', ln=True, align='R')
    
    return pdf.output()

# --- 2. CONEXIÓN Y DATOS ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]

@st.cache_resource
def get_all_sheets():
    try:
        creds = Credentials.from_service_account_info(st.secrets["gsheets"], scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key("19M-Tn7cYH4UmuKBZHxVqZhkI7RAGsxwdq2RP8xp5JFU")
        
        hojas = ["General", "Cocina", "Recetas", "Ventas"]
        dic_h = {}
        for h in hojas:
            try:
                dic_h[h] = spreadsheet.worksheet(h)
            except:
                dic_h[h] = None
        return dic_h
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

# --- 3. PROCESAMIENTO ---
diccionario_hojas = get_all_sheets()
if not diccionario_hojas: st.stop()

# --- 4. INTERFAZ ---
st.sidebar.title("🍔 Gatica Food")
menu = st.sidebar.radio("Ir a:", ["📦 Inventario", "💰 Ventas", "📊 Cierre de Caja"])

if menu == "📦 Inventario":
    # (Aquí va tu código original de inventario, filtrado y tablas)
    st.title("Gestión de Inventario")
    sector = st.sidebar.selectbox("Sector", ["General", "Cocina"])
    sheet = diccionario_hojas[sector]
    # ... (resto del código que ya tenías) ...

elif menu == "💰 Ventas":
    st.title("Nueva Venta")
    # Simulación de carrito (puedes expandir esto con tus productos de la hoja Cocina)
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("Productos")
        # Aquí cargarías el df_raw para seleccionar productos
        prod_nombre = st.text_input("Producto")
        prod_cant = st.number_input("Cantidad", min_value=1, value=1)
        prod_precio = st.number_input("Precio Unitario", min_value=0.0, step=100.0)
        metodo = st.selectbox("Método de Pago", ["Efectivo", "Transferencia", "Tarjeta"])
        
    with col2:
        st.subheader("Resumen")
        total = prod_cant * prod_precio
        st.metric("Total a cobrar", f"${total:.2f}")
        
        if st.button("Registrar Venta y Generar Ticket"):
            if prod_nombre:
                # 1. Guardar en Google Sheets (Hoja Ventas)
                ahora = datetime.now(zona_horaria)
                nueva_fila = [ahora.strftime('%d/%m/%Y'), ahora.strftime('%H:%M'), prod_nombre, prod_cant, total, metodo]
                diccionario_hojas["Ventas"].append_row(nueva_fila)
                
                # 2. Generar PDF
                item_data = [{'nombre': prod_nombre, 'cant': prod_cant, 'subtotal': total}]
                pdf_t = generar_ticket_venta(item_data, total, metodo)
                
                st.success("Venta Guardada")
                st.download_button("📥 Descargar Ticket", data=bytes(pdf_t), file_name="ticket.pdf", mime="application/pdf")

elif menu == "📊 Cierre de Caja":
    st.title("Cierre de Caja Diario")
    
    ws_v = diccionario_hojas["Ventas"]
    datos_v = ws_v.get_all_records()
    df_v = pd.DataFrame(datos_v)
    
    if not df_v.empty:
        # Filtrar solo hoy
        hoy = datetime.now(zona_horaria).strftime('%d/%m/%Y')
        df_hoy = df_v[df_v['Fecha'] == hoy]
        
        if not df_hoy.empty:
            st.write(f"### Ventas del día: {hoy}")
            st.dataframe(df_hoy, use_container_width=True)
            
            c1, c2 = st.columns(2)
            total_dia = df_hoy['Total'].sum()
            stats_pago = df_hoy.groupby('Metodo')['Total'].sum().to_dict()
            
            c1.metric("Recaudación Total", f"${total_dia:.2f}")
            with c2:
                st.write("**Desglose:**")
                for m, v in stats_pago.items():
                    st.write(f"{m}: ${v:.2f}")
            
            if st.button("Generar Reporte de Cierre (PDF)"):
                pdf_c = generar_reporte_cierre(df_hoy, total_dia, stats_pago)
                st.download_button("📥 Descargar Reporte PDF", data=bytes(pdf_c), file_name=f"cierre_{hoy}.pdf")
        else:
            st.warning("No hay ventas registradas el día de hoy.")
    else:
        st.info("La hoja de ventas está vacía.")
