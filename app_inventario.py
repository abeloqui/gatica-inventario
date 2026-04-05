# --- INTERFAZ PRINCIPAL ---
st.title(f"📦 Inventario: {sector_seleccionado}")

# 1. MÉTRICAS (Solo si hay datos)
if not df_raw.empty:
    total_items = len(df_raw)
    alertas = len(df_raw[df_raw['Stock Actual'] < df_raw['Stock Mínimo']])
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Productos", total_items)
    c2.metric("Alertas", alertas, delta=-alertas, delta_color="inverse")
    c3.metric("Último Sync", datetime.now().strftime('%H:%M'))

    # Filtros de visualización
    df_display = df_raw.copy()
    if busqueda:
        df_display = df_display[df_display['Producto'].str.contains(busqueda, case=False)]
    if solo_bajos:
        df_display = df_display[df_display['Stock Actual'] < df_display['Stock Mínimo']]

    # Tabla de Inventario
    st.subheader("Listado de Existencias")
    st.dataframe(
        df_display, 
        width="stretch", 
        hide_index=True,
        column_config={
            "Stock Actual": st.column_config.NumberColumn(format="%d 📦"),
            "Stock Mínimo": st.column_config.NumberColumn(format="%d ⚠️"),
            "Estado": st.column_config.TextColumn("Status")
        }
    )
else:
    st.info(f"La hoja '{sector_seleccionado}' está vacía. ¡Agregá el primer producto abajo!")

st.divider()

# 2. BLOQUES DE ACCIÓN (Fuera del IF para que siempre aparezcan)
col_edit, col_new = st.columns(2)

with col_edit:
    # Solo mostramos edición si hay qué editar
    if not df_raw.empty:
        with st.container(border=True):
            st.subheader("📝 Gestionar Existente")
            prod_sel = st.selectbox("Elegir producto", df_raw['Producto'].tolist(), key="edit_box")
            
            if prod_sel:
                curr_data = df_raw[df_raw['Producto'] == prod_sel].iloc[0]
                nuevo_valor = st.number_input("Nuevo Stock", value=int(curr_data['Stock Actual']), step=1)
                
                c_upd, c_del = st.columns([2, 1])
                
                if c_upd.button("Guardar Cambios", type="primary", use_container_width=True):
                    try:
                        cell = sheet.find(prod_sel, in_column=2)
                        sheet.update_cell(cell.row, 3, nuevo_valor)
                        nuevo_estado = "🚨 BAJO" if nuevo_valor < curr_data['Stock Mínimo'] else "✅ OK"
                        sheet.update_cell(cell.row, 5, nuevo_estado)
                        st.success("¡Actualizado!")
                        st.cache_resource.clear()
                        st.rerun()
                    except: st.error("Error de conexión")

                with c_del.popover("🗑️"):
                    st.warning(f"¿Eliminar '{prod_sel}'?")
                    if st.button("Confirmar Borrado", type="secondary"):
                        try:
                            cell = sheet.find(prod_sel, in_column=2)
                            sheet.delete_rows(cell.row)
                            st.success("Eliminado")
                            st.cache_resource.clear()
                            st.rerun()
                        except: st.error("Error")
    else:
        st.visual_light("Aquí aparecerán las opciones de edición cuando tengas productos.")

with col_new:
    # EL FORMULARIO DE NUEVO SIEMPRE ESTÁ DISPONIBLE
    with st.container(border=True):
        st.subheader("➕ Nuevo Producto")
        # Quitamos el popover para que sea más directo si la lista está vacía
        with st.form("form_nuevo", clear_on_submit=True):
            f_cat = st.text_input("Categoría", "Cocina" if sector_seleccionado == "Cocina" else "General")
            f_prod = st.text_input("Nombre del Producto")
            f_stock = st.number_input("Stock Inicial", min_value=0, value=0)
            f_min = st.number_input("Stock Mínimo", min_value=1, value=10)
            
            if st.form_submit_button(f"Registrar en {sector_seleccionado}", use_container_width=True):
                if f_prod:
                    try:
                        f_est = "🚨 BAJO" if f_stock < f_min else "✅ OK"
                        sheet.append_row([f_cat, f_prod, f_stock, f_min, f_est])
                        st.success("¡Primer producto agregado!")
                        st.cache_resource.clear()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Error al guardar: {e}")
                else:
                    st.warning("El nombre es obligatorio")

st.sidebar.caption(f"Gatica Food v2.2 | {datetime.now().year}")
