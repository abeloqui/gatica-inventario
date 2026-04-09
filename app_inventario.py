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

# --- 1. LÓGICA DE PDF ---
class PDF(FPDF):
    def header(self):
        self.set_font("Arial", 'B', 12)
        self.cell(0, 8, "GATICA FOOD", ln=True, align='C')
        self.ln(5)

def generar_ticket_venta(items, total, metodo, nro_venta="0001"):
    pdf = PDF(orientation='P', unit='mm', format=(80, 150))
    pdf.add_page()
    ahora = datetime.now(zona_horaria)
    pdf.set_fill_color(230, 230, 230)
    pdf.set_font("Arial", 'B', 9)
    pdf.cell(0, 8, f"{ahora.strftime('%d/%m/%Y')} | {ahora.strftime('%H:%M:%S')}", ln=True, align='C', fill=True)
    pdf.ln(3)
    pdf.set_font("Arial", '', 8)
    pdf.cell(0, 4, f"Ticket Nro: {nro_venta}", ln=True)
    pdf.cell(0, 4, f"Metodo: {metodo}", ln=True)
    pdf.set_font("Arial", 'B', 8)
    pdf.cell(35, 5, "Item", 0); pdf.cell(10, 5, "Cant", 0); pdf.cell(20, 5, "Total", ln=True, align='R')
    pdf.set_font("Arial", '', 8)
    for item in items:
        pdf.cell(35, 5, item['nombre'][:18], 0)
        pdf.cell(10, 5, str(item['cant']), 0)
        pdf.cell(20, 5, f"${item['subtotal']:.2f}", ln=True, align='R')
    pdf.ln(2)
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(0, 8, f"TOTAL: ${total:.2f}", border='T', ln=True, align='R')
    return pdf.output()

# --- 2. CONEXIÓN ---
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
                st.warning(f"La hoja '{h}' no existe. Por favor créala.")
                dic_h[h] = None
        return dic_h
    except Exception as e:
        st.error(f"Error de conexión: {e}")
        return None

def obtener_datos_seguros(sheet):
    try:
        data = sheet.get_all_records()
        return pd.DataFrame(data) if data else pd.DataFrame()
    except:
        return pd.DataFrame()

# --- 3. PROCESAMIENTO ---
diccionario_hojas = get_all_sheets()
if not diccionario_hojas: st.stop()

# --- 4. INTERFAZ ---
st.sidebar.title("🍔 Gatica Food")
menu = st.sidebar.radio("Ir a:", ["📦 Inventario", "💰 Ventas", "📊 Cierre de Caja"])

if menu == "📦 Inventario":
    st.title("Gestión de Inventario")
    sector = st.sidebar.selectbox("Sector", ["General", "Cocina"])
    sheet = diccionario_hojas[sector]
    df_inv = obtener_datos_seguros(sheet)
    
    if not df_inv.empty:
        st.dataframe(df_inv, use_container_width=True, hide_index=True)
    else:
        st.info(f"No hay productos en el sector {sector}.")

elif menu == "💰 Ventas":
    st.title("Nueva Venta")
    
    # Obtenemos productos de Cocina y General para el selector
    df_c = obtener_datos_seguros(diccionario_hojas["Cocina"])
    df_g = obtener_datos_seguros(diccionario_hojas["General"])
    df_productos = pd.concat([df_c, df_g]).drop_duplicates(subset=['Producto']) if not (df_c.empty and df_g.empty) else pd.DataFrame()

    if not df_productos.empty:
        col1, col2 = st.columns([2, 1])
        with col1:
            # --- AQUÍ ELIGES EL PRODUCTO ---
            prod_sel = st.selectbox("Seleccionar Producto", df_productos['Producto'].tolist())
            prod_cant = st.number_input("Cantidad", min_value=1, value=1)
            # Podrías automatizar el precio si tuvieras una columna 'Precio' en el inventario
            prod_precio = st.number_input("Precio Unitario ($)", min_value=0.0, step=50.0)
            metodo = st.selectbox("Método de Pago", ["Efectivo", "Transferencia", "Tarjeta"])
            
        with col2:
            total = prod_cant * prod_precio
            st.metric("Total a cobrar", f"${total:.2f}")
            if st.button("Finalizar Venta"):
                ahora = datetime.now(zona_horaria)
                nueva_fila = [ahora.strftime('%d/%m/%Y'), ahora.strftime('%H:%M'), prod_sel, prod_cant, total, metodo]
                diccionario_hojas["Ventas"].append_row(nueva_fila)
                
                pdf_t = generar_ticket_venta([{'nombre': prod_sel, 'cant': prod_cant, 'subtotal': total}], total, metodo)
                st.success("Venta Exitosa")
                st.download_button("📥 Descargar Ticket", data=bytes(pdf_t), file_name=f"ticket_{ahora.strftime('%H%M%S')}.pdf")
    else:
        st.error("No hay productos cargados en el inventario para vender.")

elif menu == "📊 Cierre de Caja":
    st.title("Cierre de Caja")
    df_v = obtener_datos_seguros(diccionario_hojas["Ventas"])
    
    if not df_v.empty:
        hoy = datetime.now(zona_horaria).strftime('%d/%m/%Y')
        # Aseguramos que la columna Fecha exista
        if 'Fecha' in df_v.columns:
            df_hoy = df_v[df_v['Fecha'] == hoy]
            if not df_hoy.empty:
                st.dataframe(df_hoy, use_container_width=True)
                total_dia = df_hoy['Total'].sum()
                st.metric("Total Hoy", f"${total_dia:.2f}")
            else:
                st.info("Aún no hay ventas registradas hoy.")
        else:
            st.error("La hoja 'Ventas' no tiene el formato correcto (falta columna Fecha).")
    else:
        st.info("No hay registros de ventas.")
