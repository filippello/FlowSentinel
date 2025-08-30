let mediaRecorder;
let recordedChunks = [];
let captureInterval;
const MAX_IMAGES = 10;

document.getElementById('startRecording').addEventListener('click', async () => {
  try {
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: {
        cursor: "always"
      },
      audio: true
    });

    // Configurar la captura de imágenes
    const videoTrack = stream.getVideoTracks()[0];
    const imageCapture = new ImageCapture(videoTrack);

    // Iniciar el intervalo de captura de imágenes
    captureInterval = setInterval(async () => {
      try {
        const frame = await imageCapture.grabFrame();
        const canvas = document.createElement('canvas');
        
        // Downscale a 720p (máx 1280x720) manteniendo aspecto
        const maxWidth = 1280;
        const maxHeight = 720;
        const scale = Math.min(maxWidth / frame.width, maxHeight / frame.height, 1);
        const targetWidth = Math.round(frame.width * scale);
        const targetHeight = Math.round(frame.height * scale);
        
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        
        const context = canvas.getContext('2d');
        context.drawImage(frame, 0, 0, targetWidth, targetHeight);
        
        // Convertir el canvas a base64 con mejor calidad
        const imageData = canvas.toDataURL('image/jpeg', 0.9); // Aumentado a 90% de calidad
        
        // Enviar la imagen al servidor Python
        try {
          const response = await fetch('http://127.0.0.1:5001/save-image', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json'
            },
            mode: 'cors',
            body: JSON.stringify({
              image: imageData
            })
          });
          
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          
          const result = await response.json();
          if (result.success) {
            document.getElementById('status').textContent = `Imagen guardada: ${result.filename}`;
          } else {
            console.error('Error al guardar imagen:', result.error);
            document.getElementById('status').textContent = `Error: ${result.error}`;
          }
        } catch (err) {
          console.error('Error al enviar imagen:', err);
          document.getElementById('status').textContent = `Error de conexión: ${err.message}`;
        }

      } catch (err) {
        console.error("Error al capturar imagen:", err);
        document.getElementById('status').textContent = `Error de captura: ${err.message}`;
      }
    }, 2000); // Asegurar intervalo de 2 segundos

    mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'video/webm;codecs=vp9'
    });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = () => {
      // Detener el intervalo de captura de imágenes
      clearInterval(captureInterval);
      
      const blob = new Blob(recordedChunks, {
        type: 'video/webm'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      document.body.appendChild(a);
      a.style.display = 'none';
      a.href = url;
      a.download = 'grabacion-' + new Date().toISOString() + '.webm';
      a.click();
      window.URL.revokeObjectURL(url);
      recordedChunks = [];
    };

    mediaRecorder.start();
    document.getElementById('startRecording').disabled = true;
    document.getElementById('startRecording').classList.add('recording');
    document.getElementById('stopRecording').disabled = false;
  } catch (err) {
    console.error("Error: " + err);
  }
});

document.getElementById('stopRecording').addEventListener('click', async () => {
  try {
    // Detener el mediaRecorder
    mediaRecorder.stop();
    
    // Enviar petición para detener la grabación y generar el análisis final
    const response = await fetch('http://127.0.0.1:5001/stop-recording', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
      },
      mode: 'cors'
    });
    
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }
    
    const result = await response.json();
    if (result.success) {
      document.getElementById('status').textContent = 'Análisis final generado correctamente';
      console.log('Análisis final:', result.analysis);
    } else {
      console.error('Error al generar análisis final:', result.message);
      document.getElementById('status').textContent = `Error: ${result.message}`;
    }
  } catch (err) {
    console.error('Error al detener la grabación:', err);
    document.getElementById('status').textContent = `Error: ${err.message}`;
  }
  
  // Actualizar UI
  document.getElementById('startRecording').disabled = false;
  document.getElementById('startRecording').classList.remove('recording');
  document.getElementById('stopRecording').disabled = true;
});

// Event listener para captura manual
document.getElementById('manualCapture').addEventListener('click', async () => {
  try {
    document.getElementById('status').textContent = 'Iniciando captura manual...';
    
    // Mostrar instrucciones claras
    const instructions = confirm(
      '📱 CAPTURA MANUAL\n\n' +
      '1. Haz clic en "Compartir pantalla"\n' +
      '2. Selecciona "Toda la pantalla" (NO pestaña)\n' +
      '3. Haz clic en "Compartir"\n\n' +
      '¿Estás listo para continuar?'
    );
    
    if (!instructions) {
      document.getElementById('status').textContent = 'Captura manual cancelada';
      return;
    }
    
    // Intentar captura manual
    const stream = await captureWithSelection();
    document.getElementById('status').textContent = 'Captura manual iniciada';
    
    // Configurar la captura de imágenes
    const videoTrack = stream.getVideoTracks()[0];
    const imageCapture = new ImageCapture(videoTrack);

    // Iniciar el intervalo de captura de imágenes
    captureInterval = setInterval(async () => {
      try {
        const frame = await imageCapture.grabFrame();
        const canvas = document.createElement('canvas');
        
        // Downscale a 720p (máx 1280x720) manteniendo aspecto
        const maxWidth = 1280;
        const maxHeight = 720;
        const scale = Math.min(maxWidth / frame.width, maxHeight / frame.height, 1);
        const targetWidth = Math.round(frame.width * scale);
        const targetHeight = Math.round(frame.height * scale);
        
        canvas.width = targetWidth;
        canvas.height = targetHeight;
        
        const context = canvas.getContext('2d');
        context.drawImage(frame, 0, 0, targetWidth, targetHeight);
        
        // Convertir el canvas a base64 con mejor calidad
        const imageData = canvas.toDataURL('image/jpeg', 0.9);
        
        // Enviar la imagen al servidor Python
        try {
          const response = await fetch('http://127.0.0.1:5001/save-image', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json'
            },
            mode: 'cors',
            body: JSON.stringify({
              image: imageData
            })
          });
          
          if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
          }
          
          const result = await response.json();
          if (result.success) {
            document.getElementById('status').textContent = `Imagen guardada: ${result.filename}`;
          } else {
            console.error('Error al guardar imagen:', result.error);
            document.getElementById('status').textContent = `Error: ${result.error}`;
          }
        } catch (err) {
          console.error('Error al enviar imagen:', err);
          document.getElementById('status').textContent = `Error de conexión: ${err.message}`;
        }

      } catch (err) {
        console.error("Error al capturar imagen:", err);
        document.getElementById('status').textContent = `Error de captura: ${err.message}`;
      }
    }, 2000);

    mediaRecorder = new MediaRecorder(stream, {
      mimeType: 'video/webm;codecs=vp9'
    });

    mediaRecorder.ondataavailable = (event) => {
      if (event.data.size > 0) {
        recordedChunks.push(event.data);
      }
    };

    mediaRecorder.onstop = () => {
      clearInterval(captureInterval);
      
      const blob = new Blob(recordedChunks, {
        type: 'video/webm'
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      document.body.appendChild(a);
      a.style.display = 'none';
      a.href = url;
      a.download = 'grabacion-' + new Date().toISOString() + '.webm';
      a.click();
      window.URL.revokeObjectURL(url);
      recordedChunks = [];
    };

    mediaRecorder.start();
    document.getElementById('startRecording').disabled = true;
    document.getElementById('manualCapture').disabled = true;
    document.getElementById('startRecording').classList.add('recording');
    document.getElementById('stopRecording').disabled = false;
    
  } catch (err) {
    console.error("Error en captura manual: " + err);
    document.getElementById('status').textContent = `Error en captura manual: ${err.message}`;
  }
}); 