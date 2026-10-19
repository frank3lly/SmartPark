/*
  Proyecto: Parqueame - Firmware de Camara para Seeed Studio XIAO ESP32S3 Sense
  Descripcion:
    1. Se conecta a la red Wi-Fi local.
    2. Inicializa el sensor de camara OV2640 en resolucion VGA (640x480).
    3. Mide el voltaje y porcentaje de la bateria LiPo de 3.7V mediante divisor de tension en pin A0 (GPIO 1).
    4. Captura un fotograma JPEG.
    5. Envia la fotografia y la telemetria de bateria al servidor central mediante HTTP POST multipart/form-data.
    6. Espera el intervalo configurado (por ejemplo, 30 segundos) y repite el ciclo.
*/

#include "esp_camera.h"
#include <WiFi.h>

// ==============================================================================
// 1. CONFIGURACION DE RED Y SERVIDOR (MODIFICA ESTOS DATOS)
// ==============================================================================

// Nombre y contrasena de tu red Wi-Fi (debe ser la misma red donde esta la laptop/servidor)
const char* WIFI_SSID = "NOMBRE_DE_TU_WIFI";
const char* WIFI_PASS = "CONTRASENA_DE_TU_WIFI";

// Direccion IP y puerto de la laptop que corre el servidor FastAPI
// Ejemplo: "192.168.1.50" (NO uses localhost ni 127.0.0.1 porque el ESP32 es otro equipo)
const char* SERVER_HOST = "192.168.1.50";
const int   SERVER_PORT = 8000;

// Identificador unico de esta camara (cam_01, cam_02, cam_03, cam_04)
const char* CAMERA_ID = "cam_01";

// Tiempo entre cada foto en segundos (ejemplo: 30 segundos)
const int CAPTURE_INTERVAL_SECONDS = 30;

// ==============================================================================
// 2. CONFIGURACION DE HARDWARE: BATERIA LIPO
// ==============================================================================
// Pin analogico para medir bateria mediante divisor de tension (2 resistencias iguales)
// Pin A0 / D0 en Seeed Studio XIAO ESP32S3 corresponde a GPIO 1.
const int BATTERY_ADC_PIN = 1;

// Si no tienes resistencias soldadas todavia, pon esta variable en false
const bool HAS_BATTERY_DIVIDER = true;

// Relacion del divisor de tension:
// Con dos resistencias de 100k ohm iguales, el voltaje se divide entre 2.
// Por tanto, multiplicamos la lectura del pin por 2.0 para obtener el voltaje real.
const float VOLTAGE_DIVIDER_RATIO = 2.0;

// ==============================================================================
// 3. MAPEO DE PINES DE LA CAMARA (SEEED STUDIO XIAO ESP32S3 SENSE)
// ==============================================================================
#define PWDN_GPIO_NUM     21
#define RESET_GPIO_NUM    -1
#define XCLK_GPIO_NUM     10
#define SIOD_GPIO_NUM     40
#define SIOC_GPIO_NUM     39

#define Y9_GPIO_NUM       48
#define Y8_GPIO_NUM       11
#define Y7_GPIO_NUM       12
#define Y6_GPIO_NUM       14
#define Y5_GPIO_NUM       16
#define Y4_GPIO_NUM       18
#define Y3_GPIO_NUM       17
#define Y2_GPIO_NUM       15
#define VSYNC_GPIO_NUM    38
#define HREF_GPIO_NUM     47
#define PCLK_GPIO_NUM     13

// ==============================================================================
// 4. FUNCION: LECTURA DE BATERIA
// ==============================================================================
struct BatteryInfo {
  float voltage;     // En Voltios (ej. 3.95 V)
  float percentage;  // De 0.0% a 100.0%
};

BatteryInfo readBattery() {
  BatteryInfo info;

  if (!HAS_BATTERY_DIVIDER) {
    // Valor por defecto si aun no se ha conectado el circuito de medicion
    info.voltage = 3.80;
    info.percentage = 70.0;
    return info;
  }

  // analogReadMilliVolts mide directamente en milivoltios con calibracion interna del ESP32
  uint32_t pin_mv = analogReadMilliVolts(BATTERY_ADC_PIN);
  float battery_mv = (float)pin_mv * VOLTAGE_DIVIDER_RATIO;
  info.voltage = battery_mv / 1000.0;

  // Calculo de porcentaje para bateria LiPo de 3.7V:
  // Completamente cargada = 4.20V (100%)
  // Completamente descargada = 3.30V (0%)
  float pct = ((info.voltage - 3.30) / (4.20 - 3.30)) * 100.0;
  if (pct > 100.0) pct = 100.0;
  if (pct < 0.0) pct = 0.0;
  info.percentage = pct;

  return info;
}

// ==============================================================================
// 5. FUNCION: INICIALIZACION DE LA CAMARA
// ==============================================================================
bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sccb_sda = SIOD_GPIO_NUM;
  config.pin_sccb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Resolucion VGA (640x480) para deteccion vehicular
  config.frame_size   = FRAMESIZE_VGA;
  config.jpeg_quality = 12; // 10-63 (menor numero = mayor calidad)
  config.fb_count     = 2;  // Doble buffer para mayor fluidez
  config.grab_mode    = CAMERA_GRAB_LATEST;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[ERROR] Inicializacion de camara fallida con codigo: 0x%x\n", err);
    return false;
  }

  Serial.println("[OK] Sensor de camara OV2640 inicializado con exito.");
  return true;
}

// ==============================================================================
// 6. FUNCION: CONECTAR A WI-FI
// ==============================================================================
void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) {
    return;
  }

  Serial.printf("[WIFI] Conectando a red: %s ...\n", WIFI_SSID);
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASS);

  int intentos = 0;
  while (WiFi.status() != WL_CONNECTED && intentos < 30) {
    delay(500);
    Serial.print(".");
    intentos++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n[OK] Conectado a Wi-Fi exitosamente.");
    Serial.print("[INFO] Direccion IP asignada: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[ERROR] No se pudo conectar a la red Wi-Fi. Reintentara en el siguiente ciclo.");
  }
}

// ==============================================================================
// 7. FUNCION: ENVIAR FOTO Y BATERIA AL SERVIDOR (HTTP POST MULTIPART)
// ==============================================================================
bool sendFrameAndBattery(camera_fb_t* fb, BatteryInfo bat) {
  WiFiClient client;

  Serial.printf("[HTTP] Conectando con servidor %s:%d ...\n", SERVER_HOST, SERVER_PORT);
  if (!client.connect(SERVER_HOST, SERVER_PORT)) {
    Serial.println("[ERROR] No se pudo establecer conexion TCP con el servidor.");
    return false;
  }

  // Ruta del endpoint con parametros de telemetria en la URL
  String path = "/api/v1/upload/";
  path += CAMERA_ID;
  path += "?battery=" + String(bat.percentage, 1);
  path += "&voltage=" + String(bat.voltage, 2);

  // Delimitador multipart
  String boundary = "------------------------ParqueameXiaoBoundary";

  // Encabezados del formulario multipart
  String head = "--" + boundary + "\r\n";
  head += "Content-Disposition: form-data; name=\"file\"; filename=\"" + String(CAMERA_ID) + ".jpg\"\r\n";
  head += "Content-Type: image/jpeg\r\n\r\n";

  // Pie del formulario multipart
  String tail = "\r\n--" + boundary + "--\r\n";

  // Longitud total del cuerpo de la peticion
  size_t totalLen = head.length() + fb->len + tail.length();

  // Enviar cabeceras HTTP POST
  client.print("POST " + path + " HTTP/1.1\r\n");
  client.print("Host: " + String(SERVER_HOST) + ":" + String(SERVER_PORT) + "\r\n");
  client.print("User-Agent: XiaoESP32S3-Parqueame/1.0\r\n");
  client.print("Content-Type: multipart/form-data; boundary=" + boundary + "\r\n");
  client.print("Content-Length: " + String(totalLen) + "\r\n");
  client.print("Connection: close\r\n\r\n");

  // Enviar inicio del formulario
  client.print(head);

  // Enviar los bytes de la imagen JPEG por bloques de 1024 bytes
  uint8_t* fbBuf = fb->buf;
  size_t fbLen = fb->len;
  for (size_t n = 0; n < fbLen; n = n + 1024) {
    if (n + 1024 < fbLen) {
      client.write(fbBuf, 1024);
      fbBuf += 1024;
    } else if (fbLen % 1024 > 0) {
      size_t remainder = fbLen % 1024;
      client.write(fbBuf, remainder);
    }
  }

  // Enviar cierre del formulario
  client.print(tail);

  // Leer respuesta del servidor
  unsigned long timeout = millis();
  while (client.connected() && millis() - timeout < 5000) {
    if (client.available()) {
      String line = client.readStringUntil('\n');
      if (line.startsWith("HTTP/1.1 200 OK") || line.startsWith("HTTP/1.0 200 OK")) {
        Serial.println("[OK] Servidor respondio: 200 OK (Imagen procesada correctamente).");
        client.stop();
        return true;
      }
    }
  }

  client.stop();
  Serial.println("[INFO] Peticion enviada al servidor.");
  return true;
}

// ==============================================================================
// 8. SETUP Y LOOP PRINCIPALES DE ARDUINO
// ==============================================================================
void setup() {
  Serial.begin(115200);
  delay(1000);

  Serial.println("==================================================");
  Serial.println("Parqueame: Firmware de Camara Xiao ESP32S3");
  Serial.println("==================================================");

  // Configuracion del pin de bateria
  pinMode(BATTERY_ADC_PIN, INPUT);

  // Inicializar camara
  if (!initCamera()) {
    Serial.println("[FATAL] La camara fallo al iniciar. Revisa la cinta flexible.");
  }

  // Conectar a Wi-Fi
  connectWiFi();
}

void loop() {
  // Asegurar que seguimos conectados a Wi-Fi
  connectWiFi();

  if (WiFi.status() == WL_CONNECTED) {
    // 1. Leer bateria
    BatteryInfo bat = readBattery();
    Serial.printf("[BATERIA] Voltaje: %.2f V | Nivel: %.1f %%\n", bat.voltage, bat.percentage);

    // 2. Tomar fotografia
    Serial.println("[CAMARA] Capturando fotografia...");
    camera_fb_t* fb = esp_camera_fb_get();

    if (!fb) {
      Serial.println("[ERROR] Fallo al capturar fotograma de la camara.");
    } else {
      Serial.printf("[CAMARA] Foto capturada: %u bytes (%dx%d px)\n", fb->len, fb->width, fb->height);

      // 3. Enviar al servidor
      sendFrameAndBattery(fb, bat);

      // 4. Liberar memoria del fotograma (MUY IMPORTANTE)
      esp_camera_fb_return(fb);
    }
  } else {
    Serial.println("[AVISO] Sin conexion Wi-Fi, esperando reconexion...");
  }

  // 5. Esperar hasta la siguiente captura
  Serial.printf("[ESPERA] Pausa de %d segundos hasta el proximo envio...\n", CAPTURE_INTERVAL_SECONDS);
  delay(CAPTURE_INTERVAL_SECONDS * 1000);
}
