#  Guía de Inicio Rápido: Frontend de Parqueame (Vite + Vanilla JS) 

Tu misión es crear una interfaz web bonita, rápida y limpia donde las personas puedan ver en tiempo real qué puestos del estacionamiento están libres y cuáles ocupados.

Vamos a usar **Vite + JavaScript Vanilla (puro) + CSS**. Nada de frameworks complicados ni configuraciones pesadas: solo código web directo, rápido y divertido de aprender.

---

## La Analogía Clave: ¿Cómo funciona este sistema?

Imagina un **restaurante**:
1. **La Cocina (El Backend en FastAPI):**
   - En la cocina, las cámaras mandan fotos cada 30 segundos.
   - El chef (nuestro modelo de Inteligencia Artificial YOLOv8) analiza la foto y revisa cada puesto de estacionamiento: *"Puesto 1: Ocupado, Puesto 2: Libre"*.
   - El chef anota los resultados en una pizarra en la cocina.
2. **El Mesero (Tu código con `fetch` en JavaScript):**
   - Cada 2 o 3 segundos, tu código va a la ventanilla de la cocina y pregunta: *"¿Cuál es el estado actual de los puestos?"*.
   - La cocina le entrega una nota en formato **JSON** (un texto muy ordenado con llaves `{}` y corchetes `[]`).
3. **El Comedor y la Pantalla (Tu página Web en Vite):**
   - Tomas esa nota y la muestras bonita en la pantalla:
     - 🟢 **Verde** = Puesto Libre.
     - 🔴 **Rojo** = Puesto Ocupado.
     - Contadores numéricos grandes: *"Libres: 4 | Ocupados: 1"*.

---

## 🌿 1. Tu Rama de Trabajo en Git

Para no mezclar tu trabajo con el backend de Python, trabajarás en tu propia rama de Git llamada `frontend`.

Abre tu terminal en la carpeta principal del proyecto (`parqueame`) y corre:

```bash
# 1. Crear y cambiarte a tu rama de trabajo
git checkout -b frontend

# 2. Confirmar que estás en la rama correcta (debe salir con un asterisco * frontend)
git branch
```

### Comandos de Git para tu día a día:
```bash
# Ver qué archivos has modificado
git status

# Guardar tus cambios
git add .
git commit -m "Mi diseño inicial de tarjetas de puestos"

# Subir tus cambios al repositorio remoto
git push origin frontend
```

---

##  2. Crear tu Proyecto Web con Vite (En 3 Minutos)

Vite es una herramienta moderna que te levanta un servidor de desarrollo ultrarrápido con recarga automática: cada vez que guardes un archivo HTML, CSS o JS, tu navegador se actualizará al instante.

### Pasos exactos en la terminal:

```bash
# 1. Entrar a la carpeta app
cd app

# 2. Inicializar el proyecto Vite con JavaScript Vanilla
npm create vite@latest . -- --template vanilla
# 3. Instalar las dependencias
npm install

# 4. Iniciar tu servidor web de desarrollo
npm run dev
```

Al correr `npm run dev`, verás algo como:
```text
  VITE v5.x.x  ready in 150 ms

  ➜  Local:   http://localhost:5173/
  ➜  Network: use --host to expose
```
Abre en tu navegador: **`http://localhost:5173`**. ¡Listo, ya tienes tu entorno corriendo!

---

## 📂 3. Estructura de Archivos que Tendrás

Dentro de `app/`, tus archivos principales serán:

- **`index.html`**: El esqueleto de tu página (título, tarjetas, contenedor donde irán los puestos y la imagen).
- **`style.css`**: El estilo visual (los colores verde y rojo, fuentes, espaciados y diseño responsivo).
- **`main.js`**: El cerebro de tu web (se conecta con el backend, pide los datos y dibuja los puestos en la pantalla).

---

## 📡 4. El Menú de Endpoints del Backend (Tus datos)

El servidor backend correrá en tu misma computadora en la dirección:  
👉 **`http://localhost:8000`**

Aquí tienes los 4 endpoints que el backend tiene preparados para ti:

### 1. Resumen General del Estacionamiento
- **URL:** `GET http://localhost:8000/api/v1/status`
- **Para qué sirve:** Ideal para mostrar el cartel principal con los totales.
- **Ejemplo de respuesta:**
  ```json
  {
    "total_spots": 5,
    "total_occupied": 2,
    "total_free": 3,
    "timestamp": 1727367200.5,
    "cameras": {
      "cam_01": {
        "camera_id": "cam_01",
        "name": "Campus North Lot - Pole 1",
        "total_spots": 5,
        "occupied_spots": 2,
        "free_spots": 3
      }
    }
  }
  ```

---

### 2. Detalle de Puestos de una Cámara
- **URL:** `GET http://localhost:8000/api/v1/cameras/cam_01/status`
- **Para qué sirve:** Para dibujar cada puesto individualmente en una cuadrícula.
- **Ejemplo de respuesta:**
  ```json
  {
    "camera_id": "cam_01",
    "name": "Campus North Lot - Pole 1",
    "total_spots": 5,
    "occupied_spots": 2,
    "free_spots": 3,
    "last_processed_at": 1727367200.5,
    "spots": [
      { "spot_id": "spot_01", "occupied": true, "confidence": 0.91 },
      { "spot_id": "spot_02", "occupied": false, "confidence": 0.0 },
      { "spot_id": "spot_03", "occupied": true, "confidence": 0.88 },
      { "spot_id": "spot_04", "occupied": false, "confidence": 0.0 },
      { "spot_id": "spot_05", "occupied": false, "confidence": 0.0 }
    ]
  }
  ```

---

### 3. ¡La Foto con Detección en Vivo! (Súper fácil de mostrar)
- **URL:** `GET http://localhost:8000/api/v1/cameras/cam_01/image`
- **Para qué sirve:** El backend ya dibuja los cuadros de los carros, las líneas verdes para puestos libres y las rojas para puestos ocupados.
- **Cómo usarla en tu HTML:** No tienes que hacer nada complicado, solo ponla en una etiqueta de imagen normal:
  ```html
  <img id="camera-feed" src="http://localhost:8000/api/v1/cameras/cam_01/image" alt="Vista en vivo" />
  ```

---

### 4. Chequeo de Salud del Servidor
- **URL:** `GET http://localhost:8000/api/v1/health`
- **Para qué sirve:** Para mostrar una lucecita verde si el backend está prendido o roja si está apagado.

---

## 🛠️ 5. Código Base Inicial (Copia, Pega y Personaliza)

Para que no arranques desde cero, aquí tienes una plantilla lista que funciona directamente con el backend:

### A. `index.html`
```html
<!DOCTYPE html>
<html lang="es">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Parqueame - Detección en Tiempo Real</title>
    <link rel="stylesheet" href="./style.css" />
  </head>
  <body>
    <div class="app-container">
      <header>
        <h1>🚗 Parqueame</h1>
        <p>Sistema Inteligente de Monitoreo de Estacionamiento</p>
        <div id="connection-badge" class="badge">Conectando...</div>
      </header>

      <!-- Tarjetas de resumen -->
      <section class="stats-grid">
        <div class="card stat-card">
          <span class="label">Total Puestos</span>
          <span id="total-spots" class="value">--</span>
        </div>
        <div class="card stat-card free">
          <span class="label">Puestos Libres</span>
          <span id="free-spots" class="value">--</span>
        </div>
        <div class="card stat-card occupied">
          <span class="label">Puestos Ocupados</span>
          <span id="occupied-spots" class="value">--</span>
        </div>
      </section>

      <!-- Cuadrícula de puestos individuales -->
      <section class="spots-section">
        <h2>Estado de los Puestos (Cámara 1)</h2>
        <div id="spots-grid" class="spots-grid">
          <!-- main.js generará los puestos aquí automáticamente -->
        </div>
      </section>

      <!-- Foto en vivo de la cámara con detecciones -->
      <section class="camera-section">
        <h2>Vista de la Cámara con IA</h2>
        <div class="image-wrapper">
          <img id="live-camera" src="http://localhost:8000/api/v1/cameras/cam_01/image" alt="Esperando imagen..." />
        </div>
      </section>
    </div>

    <script type="module" src="./main.js"></script>
  </body>
</html>
```

---

### B. `style.css`
```css
:root {
  --bg-color: #0f172a;
  --card-bg: #1e293b;
  --text-main: #f8fafc;
  --text-muted: #94a3b8;
  --color-free: #22c55e;
  --color-occupied: #ef4444;
  --color-border: #334155;
}

* {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
  font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
}

body {
  background-color: var(--bg-color);
  color: var(--text-main);
  padding: 24px;
}

.app-container {
  max-width: 900px;
  margin: 0 auto;
}

header {
  text-align: center;
  margin-bottom: 24px;
}

header h1 {
  font-size: 2rem;
  margin-bottom: 6px;
}

header p {
  color: var(--text-muted);
}

.badge {
  display: inline-block;
  margin-top: 8px;
  padding: 4px 12px;
  border-radius: 9999px;
  font-size: 0.85rem;
  font-weight: 600;
  background-color: var(--card-bg);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 16px;
  margin-bottom: 32px;
}

.card {
  background-color: var(--card-bg);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px;
  text-align: center;
}

.stat-card .label {
  display: block;
  font-size: 0.9rem;
  color: var(--text-muted);
  margin-bottom: 8px;
}

.stat-card .value {
  font-size: 2.2rem;
  font-weight: 700;
}

.stat-card.free .value {
  color: var(--color-free);
}

.stat-card.occupied .value {
  color: var(--color-occupied);
}

.spots-section, .camera-section {
  margin-bottom: 32px;
}

h2 {
  font-size: 1.3rem;
  margin-bottom: 16px;
  border-bottom: 1px solid var(--color-border);
  padding-bottom: 8px;
}

.spots-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: 12px;
}

.spot-box {
  padding: 16px;
  border-radius: 8px;
  font-weight: bold;
  text-align: center;
  border: 2px solid;
  transition: transform 0.2s ease;
}

.spot-box:hover {
  transform: translateY(-2px);
}

.spot-box.libre {
  background-color: rgba(34, 197, 94, 0.15);
  border-color: var(--color-free);
  color: var(--color-free);
}

.spot-box.ocupado {
  background-color: rgba(239, 68, 68, 0.15);
  border-color: var(--color-occupied);
  color: var(--color-occupied);
}

.image-wrapper {
  background-color: var(--card-bg);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  overflow: hidden;
  text-align: center;
}

.image-wrapper img {
  width: 100%;
  max-height: 480px;
  object-fit: contain;
  display: block;
}
```

---

### C. `main.js`
```javascript
const API_BASE = 'http://localhost:8000/api/v1';

// Elementos de la pantalla
const totalSpotsEl = document.getElementById('total-spots');
const freeSpotsEl = document.getElementById('free-spots');
const occupiedSpotsEl = document.getElementById('occupied-spots');
const spotsGridEl = document.getElementById('spots-grid');
const liveImgEl = document.getElementById('live-camera');
const connectionBadge = document.getElementById('connection-badge');

// Función que consulta el estado y actualiza la pantalla
async function actualizarEstacionamiento() {
  try {
    // 1. Preguntarle al backend por el estado de la cámara 01
    const res = await fetch(`${API_BASE}/cameras/cam_01/status`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    
    const data = await res.json();

    // 2. Actualizar las tarjetas de números
    totalSpotsEl.textContent = data.total_spots;
    freeSpotsEl.textContent = data.free_spots;
    occupiedSpotsEl.textContent = data.occupied_spots;

    // 3. Dibujar las cajitas de los puestos
    spotsGridEl.innerHTML = ''; // Limpiar cuadrícula anterior
    data.spots.forEach(puesto => {
      const box = document.createElement('div');
      const estaOcupado = puesto.occupied;

      box.className = `spot-box ${estaOcupado ? 'ocupado' : 'libre'}`;
      box.innerHTML = `
        <div>${puesto.spot_id}</div>
        <small style="font-size:0.75rem;">${estaOcupado ? '🔴 Ocupado' : '🟢 Libre'}</small>
      `;
      spotsGridEl.appendChild(box);
    });

    // 4. Refrescar la imagen (agregamos timestamp ?t= para evitar caché del navegador)
    liveImgEl.src = `${API_BASE}/cameras/cam_01/image?t=${Date.now()}`;

    // 5. Actualizar etiqueta de conexión
    connectionBadge.textContent = '🟢 Sistema en línea';
    connectionBadge.style.color = '#22c55e';

  } catch (error) {
    console.warn('Backend aún no disponible o sin señal:', error);
    connectionBadge.textContent = '🔴 Servidor desconectado (reintentando...)';
    connectionBadge.style.color = '#ef4444';
  }
}

// Llamar inmediatamente al abrir la página
actualizarEstacionamiento();

// Repetir cada 3 segundos (3000 milisegundos) automáticamente
setInterval(actualizarEstacionamiento, 3000);
```

---

## 📚 6. Recursos Recomendados para Aprender

Si tienes dudas mientras programas o quieres agregar más estilo:
1. **Guía de `fetch()` de JavaScript (MDN Web Docs):**  
   https://developer.mozilla.org/es/docs/Web/API/Fetch_API/Using_Fetch
2. **Guía de CSS Flexbox y Grid (Para ordenar tarjetas fácilmente):**  
   https://css-tricks.com/snippets/css/a-guide-to-flexbox/
3. **Documentación interactiva de nuestro Backend:**  
   Cuando tu colega tenga el backend encendido, entra a: `http://localhost:8000/docs`. ¡Allí puedes probar cada endpoint haciendo clic en *"Try it out"* y ver exactamente qué devuelve!

¡Mucho éxito con el desarrollo del frontend! Cualquier duda con los endpoints o el formato de datos, coméntasela al equipo. 🚀
