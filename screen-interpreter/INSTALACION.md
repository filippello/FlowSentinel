# Instalación y Uso de FlowSentinel

## Instalación

1. **Abrir Chrome** y ir a `chrome://extensions/`
2. **Activar el "Modo desarrollador"** (toggle en la esquina superior derecha)
3. **Hacer clic en "Cargar descomprimida"**
4. **Seleccionar la carpeta** `FlowSentinel/screen-interpreter`
5. **Verificar que la extensión aparezca** en la lista de extensiones

## Uso

1. **Hacer clic en el icono de la extensión** en la barra de herramientas
2. **Hacer clic en "Start Recording"**
3. **Seleccionar "Toda la pantalla"** en la ventana que se abre
4. **Hacer clic en "Compartir"**
5. **La grabación comenzará automáticamente**
6. **Para detener**, hacer clic en "Stop Recording"

## Características

- ✅ **Persistencia**: La grabación continúa aunque cambies de ventana o pestaña
- ✅ **Estado sincronizado**: El popup siempre muestra el estado actual
- ✅ **Tiempo en tiempo real**: Muestra el tiempo transcurrido de la grabación
- ✅ **Captura de imágenes**: Toma capturas cada 2 segundos para análisis
- ✅ **Descarga automática**: El video se descarga automáticamente al detener

## Solución de Problemas

### La extensión se cierra al cambiar de ventana
- **Solución**: Ahora la grabación se ejecuta en el background script
- **Estado**: Se mantiene sincronizado entre el popup y el background

### No se puede grabar
- **Verificar**: Que el servidor Python esté ejecutándose en `http://127.0.0.1:5001`
- **Permisos**: Asegurarse de dar permiso para compartir pantalla

### Error de permisos
- **Verificar**: Que la extensión tenga permisos de "desktopCapture"
- **Reinstalar**: Si persiste, reinstalar la extensión

## Archivos Importantes

- `background.js`: Maneja la grabación y mantiene el estado
- `popup.js`: Interfaz de usuario que se comunica con el background
- `popup.html`: Interfaz visual de la extensión
- `manifest.json`: Configuración y permisos de la extensión

## Notas Técnicas

- La extensión usa **Manifest V3** (compatible con Chrome moderno)
- El **background script** persiste la grabación
- El **popup** se sincroniza automáticamente con el estado
- Se usa **chrome.storage** para persistir el estado entre sesiones
