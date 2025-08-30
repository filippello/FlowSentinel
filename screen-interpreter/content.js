// Content script para la pestaña temporal de selección de pantalla
console.log('Content script cargado en pestaña temporal');

// Listener para mensajes del background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log('Mensaje recibido en content script:', request);
  
  if (request.action === 'chooseDesktopMedia') {
    console.log('Iniciando selección de pantalla...');
    
    // Usar chrome.desktopCapture.chooseDesktopMedia desde el contexto de la pestaña
    chrome.desktopCapture.chooseDesktopMedia(
      ['screen', 'window', 'tab'],
      (streamId) => {
        console.log('Stream ID obtenido:', streamId);
        if (streamId) {
          sendResponse({ streamId: streamId });
        } else {
          sendResponse({ error: 'No se seleccionó ninguna fuente de pantalla' });
        }
      }
    );
    
    return true; // Indica que la respuesta será asíncrona
  }
});

// Mostrar mensaje en la página
document.body.innerHTML = `
  <div style="text-align: center; padding: 50px; font-family: Arial, sans-serif;">
    <h1>🎥 Selecciona tu pantalla</h1>
    <p>Se abrirá una ventana para que selecciones qué compartir.</p>
    <p>Esta pestaña se cerrará automáticamente después de la selección.</p>
    <div style="margin-top: 30px; padding: 20px; background-color: #f0f0f0; border-radius: 10px;">
      <p><strong>Opciones disponibles:</strong></p>
      <ul style="text-align: left; display: inline-block;">
        <li>🖥️ Toda la pantalla</li>
        <li>🪟 Ventana específica</li>
        <li>📑 Pestaña específica</li>
      </ul>
    </div>
  </div>
`;
