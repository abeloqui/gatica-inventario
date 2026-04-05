

# Agregar producto
st.subheader("Agregar Nuevo Producto")
with st.form("agregar"):
    col1, col2 = st.columns(2)
    with col1:
        cat = st.text_input("Categoría", "Descartables y Empaques")
        prod = st.text_input("Producto")
    with col2:
        actual = st.number_input("Stock Actual", min_value=0, value=0)
        minimo = st.number_input("Stock Mínimo", min_value=1, value=10)
    
    if st.form_submit_button("Agregar"):
        if prod:
            try:
                estado = "🚨 BAJO" if actual < minimo else "✅ OK"
                sheet.append_row([cat, prod, actual, minimo, estado])
                st.success("Producto agregado")
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")

st.caption(f"Actualizado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
