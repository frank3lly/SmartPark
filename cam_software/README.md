# Guia de Hardware y Firmware para Seeed Studio XIAO ESP32S3 Sense

Esta guia esta dirigida al equipo electromecanico para programar y poner en marcha las unidades de camara del proyecto Parqueame. No se asume conocimiento previo en programacion de microcontroladores: cada paso esta detallado desde cero, con explicaciones claras, analogias practicas y recursos de apoyo.

---

## 1. Mision de la Unidad de Camara

Cada estacion de monitoreo consta de:
* Un microcontrolador Seeed Studio XIAO ESP32S3 Sense con modulo de camara OV2640.
* Una bateria de polimero de litio (LiPo) de 3.7V y 3000 mAh.
* Un programa interno (firmware) que realiza la siguiente secuencia de forma autonoma:
  1. Se conecta a la red Wi-Fi del estacionamiento.
  2. Mide el estado de carga y voltaje de la bateria.
  3. Captura una fotografia a color en resolucion VGA (640x480 pixeles).
  4. Envia la fotografia y los datos de bateria a la laptop servidor mediante una peticion HTTP POST.
  5. Espera un tiempo determinado (por defecto 30 segundos) y repite la tarea.

---

## 2. Analogias Utiles para Entender el Sistema

### Analogia del Microcontrolador: El Operador Automático
Un microcontrolador ESP32-S3 es como un operario con reloj, libreta y una camara fotografica. No puede improvisar nada, pero cumple de manera exacta las ordenes que le grabemos en su memoria. Su rutina es:
1. Revisa el nivel de agua de su tanque (voltaje de la bateria).
2. Presiona el disparador de la camara (toma la foto).
3. Mete la foto en un sobre sellado con el nivel de agua anotado en el remitente (peticion HTTP POST).
4. Entrega el sobre al cartero inalambrico (antena Wi-Fi).
5. Descansa x segundos antes de la siguiente foto.

### Analogia de la Bateria LiPo: El Tanque de Agua a Presion
Una bateria LiPo de 3.7V nominales se comporta como un tanque hidraulico:
* Completamente cargada (llena): Su presion electrica es de 4.20 Voltios.
* A media carga: Ronda los 3.70 a 3.80 Voltios.
* Descargada (vacia): Llega a 3.30 Voltios. Por debajo de 3.0 Voltios el microcontrolador se apaga por falta de energia.

### Analogia del Divisor de Tension: La Valvula Reductora de Presion
El pin de lectura del microcontrolador solo tolera presiones electricas de hasta 3.30 Voltios. Si conectamos directamente la bateria cargada (4.20 Voltios), el pin sufrira danos permanentes por sobretension.

( No se de eso resuelve como o que parte hay que comprar o usar para bajar de 4.20 a 3.30  habla con carlos yo creo
que es como un regulador de nuevo no sé de esa vaina )

El microcontrolador lee esos 2.10 Voltios con total seguridad y en el codigo multiplica por 2 para saber que la bateria real tiene 4.20 Voltios.

---

## 3. Descripcion del Hardware Físico

El kit Seeed Studio XIAO ESP32S3 Sense esta formado por tres piezas que vienen ensambladas o en la misma caja:

1. Placa Base (XIAO ESP32S3):
   * Contiene el procesador ESP32-S3 de doble nucleo a 240 MHz.
   * Cuenta con un puerto USB Tipo C para alimentacion y carga de codigo.
   * En la cara inferior posee dos zonas metalicas para soldar la bateria: terminal positivo (BAT+) y terminal negativo (GND).
   * Cuenta con dos botones diminutos en la superficie:
     - Boton 'B' (Boot): Forzar el modo de carga de programa.
     - Boton 'R' (Reset): Reiniciar el microcontrolador.

2. Placa de Expansion (Sense Daughterboard):
   * Se acopla encima de la placa base mediante dos filas de conectores miniatura.
   * Contiene el conector para la cinta plana de la camara, un microfono digital y una ranura para tarjeta MicroSD.

3. Sensor de Camara OV2640:
   * Camara de 2 Megapixeles con lente ajustable y cinta flexible dorada.

### Conexión Correcta de la Cinta de la Camara:
* Ubica el conector plastico FPC en la placa de expansion Sense.
* Levanta con suavidad y usando la punta de una una la pequena pestana negra de bloqueo (se abre hacia arriba como una bisagra).
* Inserta la cinta dorada de la camara hasta el fondo, asegurandote de que las pistas metalicas queden hacia el lado de los contactos del conector.
* Baja la pestana negra para aprisionar la cinta firmemente.
* Nota: Si la cinta queda ligeramente torcida o suelta, la camara no iniciara y el programa reportara error.

---

## 4. Circuito de Medicion de Bateria (Divisor de Tension) ( cambiar por plan nuevo de regulador )

Para que el microcontrolador reporte el porcentaje de bateria, se requiere soldar dos resistencias de 100k ohm (o cualquier par de resistencias identicas de entre 47k y 220k ohm):

Esquema de conexion:
* Terminal positivo de la bateria (BAT+) conectado a un extremo de la Resistencia 1.
* El punto medio (la union entre Resistencia 1 y Resistencia 2) conectado al pin A0 (GPIO 1) del XIAO.
* El otro extremo de la Resistencia 2 conectado a tierra comun (GND).

Si al momento de probar aun no has soldado las resistencias, no hay problema: en el archivo de codigo `xiao_camera_firmware.ino` cambia la linea `const bool HAS_BATTERY_DIVIDER = true;` a `false;` y la camara enviara las fotos con un valor simulado mientras concluyes el montaje electrico.

( creo que esto habra que cambiarlo o hay una mejor manera de hacerlo, figure it out )

---

## 5. Herramientas de Software Necesarias

Para transferir el programa desde la computadora a la tarjeta se utiliza:
* Lenguaje de programacion: C++ orientado al entorno Arduino.
* Entorno de desarrollo: **Arduino IDE version 2.x**.
* Sistema operativo compatible: Windows 10/11, Ubuntu Linux o macOS.

### Enlaces de Descarga de Herramientas:
1. Arduino IDE (Descarga oficial):
   https://www.arduino.cc/en/software
2. Guia de inicio rapido de Seeed Studio para XIAO ESP32S3:
   https://wiki.seeedstudio.com/xiao_esp32s3_getting_started/
3. Repositorio de la camara XIAO ESP32S3 Sense:
   https://github.com/limengdu/SeeedStudio-XIAO-ESP32S3-Sense-camera

---

## 6. Paso a Paso: Configuracion de Arduino IDE

Sigue estos pasos en orden para preparar el software en tu computadora:

### Paso 1: Instalar Arduino IDE
* Descarga el instalador desde el enlace oficial y ejecutalo siguiendo las opciones por defecto.

### Paso 2: Agregar el paquete de placas ESP32
* Abre Arduino IDE.
* En el menu superior ve a: `Archivo` -> `Preferencias` (en Windows/Linux) o `Arduino IDE` -> `Settings` (en macOS).
* Busca la casilla llamada **Gestor de URLs Adicionales de Tarjetas** (Additional boards manager URLs).
* Pega exactamente la siguiente direccion URL:
  ```text
  https://espressif.github.io/arduino-esp32/package_esp32_index.json
  ```
* Haz clic en el boton `OK` para guardar.

### Paso 3: Instalar la definicion de tarjetas ESP32
* En la barra lateral izquierda de Arduino IDE, haz clic en el icono del segundo boton (parece una placa de circuito, se llama **Boards Manager**).
* En el buscador escribe: `esp32`.
* Busca el paquete llamado **esp32 by Espressif Systems**.
* Haz clic en **Instalar** (Install). Espera unos minutos a que descargue todas las herramientas de compilacion.

### Paso 4: Seleccionar la Placa y sus Parametros Criticos
Una vez instalado el paquete, ve al menu superior `Herramientas` (Tools) y configura las siguientes opciones exactamente como se indican:
* **Placa (Board):** `esp32` -> `XIAO_ESP32S3`.
* **PSRAM:** `OPI PSRAM` (OBLIGATORIO: La camara requiere memoria PSRAM para almacenar la imagen; si esta en Disabled la camara fallara).
* **Flash Size:** `8MB (64Mb)`.
* **USB CDC On Boot:** `Enabled` (Permite ver los textos de prueba en el Monitor Serie al conectar el cable USB).
* **Upload Speed:** `921600` (Velocidad de transmision recomendada).

---

## 7. Como Pasar el Codigo de tu Computadora a la Placa

### Paso 1: Conexion Fisica
* Conecta la tarjeta XIAO a un puerto USB de tu computadora utilizando un cable USB Tipo C de buena calidad.
* Importante: Asegurate de que el cable sea de **datos y carga**, no solo de carga. Si el cable es solo de carga, la computadora no detectara la placa.

### Paso 2: Seleccionar el Puerto COM
* En Arduino IDE, ve a `Herramientas` -> `Puerto` (Port).
* Selecciona el puerto que aparece (por ejemplo: `COM3`, `COM4` en Windows o `/dev/ttyACM0` en Linux).
* Si no aparece ningun puerto, utiliza el **Metodo de Recuperacion del Boton BOOT**:
  1. Manten presionado el boton con la letra **B** en la placa.
  2. Con el boton B presionado, presiona una sola vez el boton con la letra **R** y sueltalo.
  3. Suelta el boton **B**.
  4. La tarjeta entrara en modo cargador de arranque y el puerto COM aparecera de inmediato en el menu de Arduino IDE.

### Paso 3: Abrir y Modificar el Codigo de la Camara
* En Arduino IDE, abre el archivo ubicado en este proyecto:
  `cam_software/xiao_camera_firmware/xiao_camera_firmware.ino`
* En las primeras lineas del codigo, modifica estos tres parametros con los datos de tu red:

```cpp

// 1. Nombre y clave de tu red Wi-Fi (debe ser la misma red de la laptop servidor)
const char* WIFI_SSID = "NOMBRE_DE_TU_WIFI";
const char* WIFI_PASS = "CONTRASENA_DE_TU_WIFI";

// 2. Direccion IP de la laptop que tiene encendido el backend de Python
// Abre una terminal en la laptop y escribe 'ipconfig' (Windows) o 'ip a' (Linux) para ver su IP
const char* SERVER_HOST = "" // IP de my Laptop ( el servidor ) Frankelly;
const int   SERVER_PORT = 8000 // Puerto no tiene que ser el 8000 esta ahí de ejemplo;

// 3. Identificador de esta camara fisica (cam_01, cam_02, etc.)
const char* CAMERA_ID = "cam_01";

```
Ya ahí tu tendras que buscar la forma de programar el deepsleep para ahorrar bateria y el envio de las fotos
y lo demas.

### Paso 4: Compilar y Grabar (Upload)
* Haz clic en el boton con forma de flecha hacia la derecha ubicado en la esquina superior izquierda de Arduino IDE (**Subir / Upload**).
* En la consola inferior veras el progreso:
  ```text
  Compiling sketch...
  Connecting...
  Writing at 0x00010000... (100 %)
  Leaving...
  Hard resetting via RTS pin...
  ```
* Cuando veas `Done uploading`, el microcontrolador ya estara ejecutando el programa.

---

## 8. Verificacion en Tiempo Real: Monitor Serie

Para ver lo que la camara esta haciendo y diagnosticar cualquier detalle:
1. En Arduino IDE, ve a `Herramientas` -> `Monitor Serie` (Serial Monitor), o presiona `Ctrl + Shift + M`.
2. En la esquina inferior derecha del monitor serie, cambia la velocidad a **115200 baudios**.
3. Presiona el boton **R** (Reset) en la placa para reiniciar el programa.
4. Deberas observar una salida similar a esta:

```text
==================================================
Parqueame: Firmware de Camara Xiao ESP32S3
==================================================
[OK] Sensor de camara OV2640 inicializado con exito.
[WIFI] Conectando a red: MI_WIFI ...
[OK] Conectado a Wi-Fi exitosamente.
[INFO] Direccion IP asignada: 192.168.1.120
[BATERIA] Voltaje: 4.12 V | Nivel: 91.1 %
[CAMARA] Capturando fotografia...
[CAMARA] Foto capturada: 36240 bytes (640x480 px)
[HTTP] Conectando con servidor 192.168.1.50:8000 ...
[OK] Servidor respondio: 200 OK (Imagen procesada correctamente).
[ESPERA] Pausa de 30 segundos hasta el proximo envio...
```

---

## 9. Endpoints del Servidor Utilizados

La camara interactua con el servidor FastAPI en el puerto 8000 a traves de dos vias:

1. Envio Combinado (Recomendado para ahorrar bateria):
   * Metodo: `POST`
   * URL: `http://SERVER_IP:8000/api/v1/upload/{camera_id}?battery=85.0&voltage=4.05`
   * Formato: `multipart/form-data` con el archivo binario JPEG en el campo `file`.
   * Ventaja: En una sola conexion de radio Wi-Fi se transmite la foto y el nivel de carga, minimizando el consumo de la bateria LiPo.

2. Envio Independiente de Bateria (Opcional):
   * Metodo: `POST`
   * URL: `http://SERVER_IP:8000/api/v1/cameras/{camera_id}/battery`
   * Formato: `application/json`
   * Cuerpo: `{"battery_percentage": 85.0, "battery_voltage": 4.05}`

---

## 10. Resolucion de Problemas Frecuentes (Troubleshooting)

### Error 1: "Camera Init Failed (0x105)"
* Causa 1: La cinta dorada de la camara esta mal asentada o torcida en el conector. Abre la pestana negra, insertala recta y presiona firmemente la pestana hacia abajo.
* Causa 2: La opcion de memoria PSRAM en el menu `Herramientas` de Arduino IDE esta desactivada. Verifica que diga `OPI PSRAM`.

### Error 2: "No se encuentra el puerto COM en la computadora"
* Causa 1: El cable USB es solo para cargar telefonos y no tiene lineas de datos D+ y D-. Cambia de cable USB-C.
* Causa 2: El chip USB quedo bloqueado. Aplica el metodo de rescate: manten presionado el boton `B`, pulsa y suelta el boton `R`, y finalmente suelta el boton `B`.

### Error 3: "La camara se queda en puntos suspensivos conectando a Wi-Fi"
* Causa: Los microcontroladores ESP32 solo se conectan a redes Wi-Fi de **2.4 GHz**. No son compatibles con redes que operen exclusivamente en la banda de 5 GHz. Asegurate de que la red del router tenga habilitada la banda 2.4 GHz.

### Error 4: "Fallo de conexion TCP con el servidor"
* Causa 1: La IP configurada en `SERVER_HOST` no es la de la laptop. Verifica la IP local de la laptop con el comando `ipconfig` en Windows.
* Causa 2: El Firewall de Windows esta bloqueando las conexiones entrantes al puerto 8000. Desactiva temporalmente el firewall privado o crea una regla para permitir el puerto 8000.
* Causa 3: La laptop y el ESP32 estan en redes diferentes. Ambos deben estar conectados a la misma red Wi-Fi o router.

### Error 5: "La imagen se ve borrosa o desenfocada"
* Causa: El sensor OV2640 posee rosca de enfoque manual. Gira muy suavemente con los dedos el cilindro exterior del lente hacia la izquierda o derecha mientras observas la imagen recibida en el servidor hasta obtener la nitidez deseada.
