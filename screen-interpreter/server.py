from flask import Flask, request, jsonify
from flask_cors import CORS
import base64
import os
from datetime import datetime
import logging
from PIL import Image
import io
import numpy as np
from io import BytesIO
from openai import OpenAI
from collections import deque
import time
import requests
import shutil
import json
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Configurar CORS para permitir peticiones desde cualquier origen
CORS(app, resources={
    r"/*": {
        "origins": "*",
        "methods": ["GET", "POST", "OPTIONS"],
        "allow_headers": ["Content-Type"]
    }
})

# Configurar OpenAI con API key desde variable de entorno
api_key = os.getenv('OPENAI_API_KEY')
if not api_key:
    logger.error("OPENAI_API_KEY no encontrada en variables de entorno")
    raise ValueError("OPENAI_API_KEY debe estar definida en el archivo .env")

client = OpenAI(api_key=api_key)

# Asegurarse de que la carpeta images existe
if not os.path.exists('images'):
    os.makedirs('images')

# Variables globales
last_image = None
last_image_path = None
image_buffer = deque(maxlen=5)  # Buffer para mantener las últimas 5 imágenes
last_analysis_time = 0
ANALYSIS_COOLDOWN = 30  # Segundos entre análisis
all_analyses = []  # Lista para almacenar todos los análisis
is_processing = False  # Flag para controlar si estamos procesando imágenes

def save_analysis_to_file(analysis_text):
    """Guarda el análisis en un archivo."""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'analysis_{timestamp}.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(analysis_text)
        logger.info(f"Análisis guardado en {filename}")
        return filename
    except Exception as e:
        logger.error(f"Error al guardar análisis: {str(e)}")
        return None

def clean_images_directory():
    """Limpia el directorio de imágenes."""
    try:
        if os.path.exists('images'):
            shutil.rmtree('images')
            os.makedirs('images')
            logger.info("Directorio de imágenes limpiado correctamente")
            return True
    except Exception as e:
        logger.error(f"Error al limpiar directorio de imágenes: {str(e)}")
        return False

@app.route('/clean-images', methods=['POST'])
def clean_images():
    """Endpoint para limpiar las imágenes."""
    success = clean_images_directory()
    return jsonify({
        'success': success,
        'message': 'Directorio de imágenes limpiado' if success else 'Error al limpiar directorio'
    })

def calculate_image_difference(img1, img2):
    """Calcula la diferencia porcentual entre dos imágenes."""
    # Convertir imágenes a arrays numpy
    arr1 = np.array(img1)
    arr2 = np.array(img2)
    
    # Calcular la diferencia absoluta
    diff = np.abs(arr1.astype(np.int32) - arr2.astype(np.int32))
    
    # Calcular el porcentaje de diferencia
    total_pixels = arr1.size
    changed_pixels = np.sum(diff > 10)  # Umbral de diferencia de 30 en cada canal
    difference_percentage = (changed_pixels / total_pixels) * 100
    
    return difference_percentage

def encode_image(image_path):
    """Codifica una imagen a base64."""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode("utf-8")
    except Exception as e:
        logger.error(f"Error al codificar imagen: {str(e)}")
        return None


def encode_image_downscaled(image_path, max_width=1280, max_height=720, output_format='JPEG', quality=85):
    """Abre una imagen, la reduce manteniendo aspecto a un bounding box 1280x720 y la devuelve en base64."""
    try:
        img = Image.open(image_path)
        # Asegurar espacio de color compatible
        if img.mode not in ("RGB", "L"):  # p.ej. RGBA
            img = img.convert("RGB")
        # Reducción manteniendo aspecto
        resample = getattr(Image, 'Resampling', Image).LANCZOS
        img.thumbnail((max_width, max_height), resample=resample)
        # Serializar a bytes como JPEG
        buffer = BytesIO()
        img.save(buffer, format=output_format, quality=quality, optimize=True)
        buffer.seek(0)
        return base64.b64encode(buffer.read()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error al hacer downscale/codificar imagen: {str(e)}")
        return None

def analyze_final_intent(previous_analyses):
    """Realiza un análisis final de la intención del usuario basado en todos los análisis previos."""
    try:
        # Crear el prompt para el análisis final
        prompt = """
        Based on the following screenshot analyses, provide a clear conclusion about the user's cryptocurrency transaction intent:

        {analyses}

        Your goal is to determine the user's INTENT to buy, sell, exchange, or transfer cryptocurrencies.

        Provide a single, clear conclusion that answers:
        - What is the user's main intention regarding cryptocurrency operations?
        - Which specific cryptocurrencies are they interested in?
        - What type of transaction are they likely to perform?

        Focus on the user's intent to:
        - Buy cryptocurrency (specify which one)
        - Sell cryptocurrency (specify which one)
        - Exchange/swap tokens (specify which ones)
        - Transfer funds to another wallet
        - Involved wallet addresses
        - Research before making a transaction

        Its really important to capture the addresses, if you see any, you should capture and report them.

        Give a direct, actionable conclusion about what the user is trying to accomplish with crypto.
        """

        # Llamar a la API de ChatGPT
        response = client.responses.create(
            model="gpt-5",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt.format(analyses="\n\n".join(previous_analyses))}
                    ]
                }
            ]
        )

        # Guardar el análisis final en un archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'final_analysis_{timestamp}.txt'
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(response.output_text)
        logger.info(f"Análisis final guardado en {filename}")

        return {
            'analysis': response.output_text,
            'file': filename
        }

    except Exception as e:
        logger.error(f"Error al realizar análisis final: {str(e)}")
        return None

def analyze_images_with_chatgpt():
    """Analiza la imagen más reciente con ChatGPT."""
    global last_analysis_time, all_analyses
    
    current_time = time.time()
    if current_time - last_analysis_time < ANALYSIS_COOLDOWN:
        logger.info("Esperando cooldown antes del siguiente análisis")
        return None
    
    if not image_buffer:
        logger.info("No hay imágenes para analizar")
        return None
    
    try:
        # Obtener solo la imagen más reciente
        latest_image_path = image_buffer[-1]
        
        if not os.path.exists(latest_image_path):
            logger.error(f"No se encontró la imagen: {latest_image_path}")
            return None
            
        # Downscale a 720p y codificar
        base64_image = encode_image_downscaled(latest_image_path)
        if not base64_image:
            logger.error("Error al codificar la imagen (downscale)")
            return None

        # Crear el prompt para ChatGPT
        prompt = """
        You are analyzing a screenshot for a cryptocurrency transaction detection app. Your goal is to understand what the user is looking at and whether it relates to cryptocurrency investment or trading intentions.

        Describe what you see in a natural, conversational way. For example:
        - "The user is browsing Twitter and reading a post about the benefits of a specific cryptocurrency"
        - "The user is searching Google for information about a particular crypto"
        - "The user is reading an article about top 10 cryptocurrencies and currently viewing the CARDANO section"
        - "The user is on a DEX platform trying to swap ETH for another token"
        - "The user is reading a news article about Bitcoin price movements"
        - "The user is on a wallet interface with the intention to transfer 0.5 ETH to wallet address 0x742d35Cc6634C0532925a3b8D4C9db96C4b4d8b6"

        Focus on:
        - What platform or website the user is on
        - What content they are consuming or interacting with
        - Any cryptocurrency names, prices, or trading information visible
        - Whether this suggests investment research, trading intent, or general crypto interest
        - Any suspicious or risky elements that might indicate scam attempts

        It's very useful to capture any data regarding what the user might be trying to do. Specifically look for:
        - Buy cryptocurrency (specify which one)
        - Sell cryptocurrency (specify which one)
        - Exchange/swap tokens (specify which ones)
        - Transfer funds to another wallet
        - Involved wallet addresses
        - Research before making a transaction

        Its really important to capture the addresses, if you see any, you should capture and report them.
        Addresses can be ofuscated like 0xAdc8b143f...9BF75A4139 treat them with importance but say its an ofuscated address, like this ofuscatedAddress(0xAd8b143f...9BF75A4139)

        Write your response as if you're explaining to a colleague what the user is doing right now. Be natural and descriptive, not overly structured.
        """

        # Llamar a la API de ChatGPT con el formato correcto (responses.create)
        response = client.responses.create(
            model="gpt-5",
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                    ]
                }
            ]
        )

        # Guardar el análisis en un archivo
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        analysis_text = f"Timestamp: {timestamp}\nScreenshot information: {response.output_text}"
        analysis_file = save_analysis_to_file(analysis_text)
        if analysis_file:
            logger.info(f"Análisis guardado en {analysis_file}")
            all_analyses.append(analysis_text)
            last_analysis_time = current_time
            return analysis_text
        else:
            logger.error("Error al guardar el análisis")
            return None

    except Exception as e:
        logger.error(f"Error al analizar imagen con ChatGPT: {str(e)}")
        return None

@app.route('/generate-final-analysis', methods=['POST'])
def generate_final_analysis():
    """Endpoint para generar el análisis final con todos los análisis acumulados."""
    global all_analyses
    
    if not all_analyses:
        return jsonify({
            'success': False,
            'message': 'No hay análisis previos para generar el análisis final'
        }), 400
    
    try:
        final_analysis = analyze_final_intent(all_analyses)
        if final_analysis:
            # Limpiar la lista de análisis después de generar el final
            all_analyses = []
            return jsonify({
                'success': True,
                'message': 'Análisis final generado correctamente',
                'analysis': final_analysis
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Error al generar el análisis final'
            }), 500
    except Exception as e:
        logger.error(f"Error al generar análisis final: {str(e)}")
        return jsonify({
            'success': False,
            'message': f'Error al generar el análisis final: {str(e)}'
        }), 500

def send_intent_to_rpc_server(intent):
    """Envía el análisis final al servidor RPC."""
    try:
        response = requests.post(os.getenv('RPC_SERVER_API'), json={'intent': intent}, headers={'Content-Type': 'application/json'})
        if response.status_code > 299:
            logger.error(f"Error al enviar análisis al servidor RPC: {response.status_code} - {response.text}")
            return
        logger.info("Análisis final enviado al servidor RPC correctamente")
    except Exception as e:
        logger.error(f"Excepción al enviar análisis al servidor RPC: {str(e)}")

@app.route('/stop-recording', methods=['POST', 'OPTIONS'])
def stop_recording():
    """Endpoint para detener la grabación, generar el análisis final y limpiar las imágenes."""
    global all_analyses, image_buffer, is_processing
    
    # Manejar preflight request
    if request.method == 'OPTIONS':
        return '', 200

    logger.info("Recibida petición para detener la grabación")
    logger.info(f"Estado inicial del buffer: {list(image_buffer)}")
    logger.info(f"Número de imágenes en el buffer: {len(image_buffer)}")
    
    try:
        # Marcar que estamos procesando
        is_processing = True
        logger.info("Iniciando procesamiento de imágenes")
        
        # Convertir el buffer a una lista y limpiarlo inmediatamente
        images_to_process = list(image_buffer)
        logger.info(f"Imágenes a procesar: {images_to_process}")
        image_buffer.clear()
        logger.info("Buffer limpiado")
        
        logger.info(f"Procesando {len(images_to_process)} imágenes pendientes...")
        
        processed_images = []
        for image_path in images_to_process:
            if os.path.exists(image_path):
                logger.info(f"Analizando imagen: {image_path}")
                processed_images.append(image_path)
                # Downscale a 720p y codificar
                base64_image = encode_image_downscaled(image_path)
                if base64_image:
                    # Crear el prompt para ChatGPT
                    prompt = """
                    You are analyzing a screenshot for a cryptocurrency transaction detection app. Your goal is to understand what the user is looking at and whether it relates to cryptocurrency investment or trading intentions.
                    Describe what you see in a natural, conversational way. For example:
                    - "The user is browsing Twitter and reading a post about the benefits of a specific cryptocurrency"
                    - "The user is searching Google for information about a particular crypto"
                    - "The user is reading an article about top 10 cryptocurrencies and currently viewing the CARDANO section"
                    - "The user is on a DEX platform trying to swap ETH for another token"
                    - "The user is reading a news article about Bitcoin price movements"
                    Focus on:
                    - What platform or website the user is on
                    - What content they are consuming or interacting with
                    - Any cryptocurrency names, prices, or trading information visible
                    - Whether this suggests investment research, trading intent, or general crypto interest
                    - Any suspicious or risky elements that might indicate scam attempts
                    Write your response as if you're explaining to a colleague what the user is doing right now. Be natural and descriptive, not overly structured.
                    """

                    # Llamar a la API de ChatGPT con el formato correcto
                    response = client.responses.create(
                        model="gpt-5-nano",
                        input=[
                            {
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": prompt},
                                    {"type": "input_image", "image_url": f"data:image/jpeg;base64,{base64_image}"}
                                ]
                            }
                        ]
                    )

                    # Guardar el análisis
                    analysis_text = response.output_text
                    analysis_file = save_analysis_to_file(analysis_text)
                    if analysis_file:
                        logger.info(f"Análisis guardado en {analysis_file}")
                        all_analyses.append(analysis_text)
            else:
                logger.warning(f"Imagen no encontrada: {image_path}")
        
        logger.info(f"Imágenes procesadas: {processed_images}")
        logger.info(f"Número de análisis generados: {len(all_analyses)}")
        
        if not all_analyses:
            logger.warning("No se generaron análisis para las imágenes")
            is_processing = False
            return jsonify({
                'success': False,
                'message': 'No se generaron análisis para las imágenes'
            }), 400
        
        logger.info(f"Generando análisis final con {len(all_analyses)} análisis")
        
        # Generar el análisis final
        final_analysis = analyze_final_intent(all_analyses)
        if final_analysis:
            logger.info("Análisis final generado correctamente")
            
            # Limpiar las imágenes y los análisis
            clean_images_directory()
            all_analyses.clear()
            
            logger.info("Imágenes y análisis limpiados correctamente")
            
            # Marcar que terminamos de procesar
            is_processing = False

            send_intent_to_rpc_server(final_analysis['analysis'])
            
            return jsonify({
                'success': True,
                'message': 'Grabación detenida y análisis final generado correctamente',
                'analysis': final_analysis
            })
        else:
            logger.error("Error al generar el análisis final")
            is_processing = False
            return jsonify({
                'success': False,
                'message': 'Error al generar el análisis final'
            }), 500
            
    except Exception as e:
        logger.error(f"Error al detener la grabación: {str(e)}")
        is_processing = False
        return jsonify({
            'success': False,
            'message': f'Error al detener la grabación: {str(e)}'
        }), 500

@app.route('/save-image', methods=['POST', 'OPTIONS'])
def save_image():
    global last_image, last_image_path, is_processing
    
    # Manejar preflight request
    if request.method == 'OPTIONS':
        return '', 200
        
    try:
        # Si estamos procesando imágenes, no guardar nuevas
        if is_processing:
            logger.info("Ignorando nueva imagen mientras se procesan las existentes")
            return jsonify({
                'success': True,
                'message': 'Ignorando nueva imagen mientras se procesan las existentes'
            })
            
        logger.info("Recibida petición para guardar imagen")
        
        # Verificar que el request tiene datos
        if not request.is_json:
            logger.error("Request no contiene JSON")
            return jsonify({'success': False, 'error': 'Request debe ser JSON'}), 400
        
        # Obtener la imagen en base64 del request
        data = request.get_json()
        if not data or 'image' not in data:
            logger.error("No se encontró la imagen en el request")
            return jsonify({'success': False, 'error': 'No se encontró la imagen en el request'}), 400
            
        image_data = data['image']
        logger.info("Imagen recibida en base64")
        
        # Remover el prefijo de base64 si existe
        if ',' in image_data:
            image_data = image_data.split(',')[1]
        
        # Convertir base64 a bytes y luego a imagen PIL
        try:
            image_bytes = base64.b64decode(image_data)
            current_image = Image.open(BytesIO(image_bytes))
            logger.info("Imagen decodificada correctamente")
        except Exception as e:
            logger.error(f"Error al decodificar base64: {str(e)}")
            return jsonify({'success': False, 'error': 'Error al decodificar la imagen'}), 400
        
        # Si es la primera imagen o hay cambios significativos, guardar
        should_save = True
        difference = 100
        if last_image is not None:
            difference = calculate_image_difference(last_image, current_image)
            logger.info(f"Diferencia con la imagen anterior: {difference:.2f}%")
            should_save = difference > 20  # Guardar solo si hay más de 20% de diferencia
        
        if should_save:
            # Crear nombre de archivo con timestamp
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f'images/captura_{timestamp}.png'
            
            # Guardar la imagen
            try:
                current_image.save(filename, 'PNG')
                logger.info(f"Imagen guardada en {filename}")
                
                # Actualizar la última imagen y el buffer
                last_image = current_image
                last_image_path = filename
                image_buffer.append(filename)
                
                return jsonify({
                    'success': True, 
                    'message': 'Imagen guardada correctamente',
                    'filename': filename,
                    'difference': difference
                })
            except Exception as e:
                logger.error(f"Error al guardar la imagen: {str(e)}")
                return jsonify({'success': False, 'error': 'Error al guardar la imagen'}), 500
        else:
            return jsonify({
                'success': True,
                'message': 'Imagen no guardada - cambios insuficientes',
                'difference': difference
            })
    
    except Exception as e:
        logger.error(f"Error inesperado: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("Iniciando servidor en puerto 5001...")
    app.run(host='0.0.0.0', port=5001, debug=True) 
    