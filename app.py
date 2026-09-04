if btn_guardar_edit:
    if not persona_modifica.strip():
        st.error("❌ El campo 'Persona que modifica' es obligatorio.")
    elif not resp_correcta_input or not str(resp_correcta_input).strip():
        st.error("❌ Debes indicar una respuesta correcta válida.")
    elif not motivo_edicion.strip():
        st.error("❌ El motivo de la corrección es obligatorio.")
    else:
        try:
            # 1. Actualizar respuestas del examen
            respuestas_lista[p_idx]["es_correcta"] = nuevo_estado
            respuestas_lista[p_idx]["respuesta_correcta_texto"] = resp_correcta_input
            respuestas_lista[p_idx]["opciones_posibles"] = opciones_disponibles
            
            correctas_nuevas = sum(1 for r in respuestas_lista if r["es_correcta"])
            total_preg = len(respuestas_lista)
            nuevo_porc = round((correctas_nuevas / total_preg) * 100, 2)
            nueva_nota = round((correctas_nuevas / total_preg) * 10, 2)
            
            supabase.table("intentos_examen").update({
                "respuestas_usuario": respuestas_lista,
                "nota": nueva_nota,
                "porcentaje_obtenido": nuevo_porc
            }).eq("id", intento_target_id).execute()
            
            # 2. Registrar auditoría
            registro_audit = {
                "intento_id": int(intento_target_id),
                "usuario_modificador": persona_modifica.strip(),
                "fecha_modificacion": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "valor_anterior": json.dumps({"es_correcta": p_objetivo.get("es_correcta"), "respuesta_correcta": texto_respuesta_correcta}),
                "valor_nuevo": json.dumps({"es_correcta": nuevo_estado, "respuesta_correcta": resp_correcta_input}),
                "motivo": motivo_edicion.strip()
            }
            
            supabase.table("auditoria_modificaciones").insert(registro_audit).execute()
            st.success("✅ Corrección guardada y auditada correctamente.")
            time.sleep(1.5)
            st.rerun()

        except Exception as err:
            st.error(f"⚠️ Error al guardar en la base de datos: {err}")
