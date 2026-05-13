#include <Adafruit_NeoPixel.h>

const int LED_VERMELHO = 5;
const int LED_AMARELO = 6;
const int LED_VERDE = 7;
const int RELE = 8;
const int LED_SAFETY = 10;

const int SAFETY_PIXELS = 1;
const int BRILHO_SAFETY = 80;

Adafruit_NeoPixel safetyPixel(SAFETY_PIXELS, LED_SAFETY, NEO_GRB + NEO_KHZ800);

bool safetyAtivo = false;
bool estadoPiscaSafety = false;
bool arcoIrisAtivo = true;

unsigned long ultimoPiscaSafety = 0;
unsigned long ultimoArcoIris = 0;
uint8_t posicaoArcoIris = 0;

const unsigned long INTERVALO_SAFETY = 300;
const unsigned long INTERVALO_ARCO_IRIS = 25;

void iniciarLedSafety();
void ledSafetyCor(uint8_t vermelho, uint8_t verde, uint8_t azul);
void ledSafetyDesligar();
void ledSafetyVermelho();
void ledSafetyAmarelo();
void ledSafetyVerde();
void iniciarArcoIrisSafety();
void pararArcoIrisSafety();
void atualizarArcoIrisSafety();
uint32_t corArcoIris(uint8_t posicao);
void acionarSemaforoCorrida();
void acionarRele(bool ligar);
void iniciarSafetyCar();
void pararSafetyCar();
void atualizarSafetyCar();
void desligarSaidas();

void setup() {
  Serial.begin(9600);

  pinMode(LED_VERMELHO, OUTPUT);
  pinMode(LED_AMARELO, OUTPUT);
  pinMode(LED_VERDE, OUTPUT);
  pinMode(RELE, OUTPUT);

  iniciarLedSafety();

  digitalWrite(LED_VERMELHO, LOW);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERDE, LOW);
  digitalWrite(RELE, LOW);
  acionarRele(true);
}

void loop() {
  if (Serial.available() > 0) {
    String comando = Serial.readStringUntil('\n');
    comando.trim();

    if (comando == "START") {
      acionarSemaforoCorrida();
    }

    if (comando == "SAFETY_ON") {
      iniciarSafetyCar();
    }

    if (comando == "SAFETY_OFF") {
      pararSafetyCar();
    }

    if (comando == "STOP") {
      desligarSaidas();
    }
  }

  atualizarSafetyCar();
  atualizarArcoIrisSafety();
}

void iniciarLedSafety() {
  safetyPixel.begin();
  safetyPixel.setBrightness(BRILHO_SAFETY);
  safetyPixel.clear();
  safetyPixel.show();
}

void ledSafetyCor(uint8_t vermelho, uint8_t verde, uint8_t azul) {
  safetyPixel.setPixelColor(0, safetyPixel.Color(vermelho, verde, azul));
  safetyPixel.show();
}

void ledSafetyDesligar() {
  safetyPixel.clear();
  safetyPixel.show();
}

void ledSafetyVermelho() {
  ledSafetyCor(255, 0, 0);
}

void ledSafetyAmarelo() {
  ledSafetyCor(255, 180, 0);
}

void ledSafetyVerde() {
  ledSafetyCor(0, 255, 0);
}

void iniciarArcoIrisSafety() {
  arcoIrisAtivo = true;
  safetyAtivo = false;
}

void pararArcoIrisSafety() {
  arcoIrisAtivo = false;
}

void atualizarArcoIrisSafety() {
  if (!arcoIrisAtivo || safetyAtivo) {
    return;
  }

  unsigned long agora = millis();

  if (agora - ultimoArcoIris >= INTERVALO_ARCO_IRIS) {
    ultimoArcoIris = agora;
    safetyPixel.setPixelColor(0, corArcoIris(posicaoArcoIris));
    safetyPixel.show();
    posicaoArcoIris++;
  }
}

uint32_t corArcoIris(uint8_t posicao) {
  posicao = 255 - posicao;

  if (posicao < 85) {
    return safetyPixel.Color(255 - posicao * 3, 0, posicao * 3);
  }

  if (posicao < 170) {
    posicao -= 85;
    return safetyPixel.Color(0, posicao * 3, 255 - posicao * 3);
  }

  posicao -= 170;
  return safetyPixel.Color(posicao * 3, 255 - posicao * 3, 0);
}

void acionarSemaforoCorrida() {
  pararArcoIrisSafety();
  acionarRele(false);
  safetyAtivo = false;

  digitalWrite(LED_VERMELHO, HIGH);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERDE, LOW);
  ledSafetyVermelho();
  delay(2000);

  digitalWrite(LED_AMARELO, HIGH);
  ledSafetyAmarelo();
  delay(1000);

  digitalWrite(LED_VERMELHO, LOW);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERDE, HIGH);
  ledSafetyVerde();
  acionarRele(true);
}

void acionarRele(bool ligar) {
  digitalWrite(RELE, ligar ? LOW : HIGH);
}

void iniciarSafetyCar() {
  pararArcoIrisSafety();
  safetyAtivo = true;
  estadoPiscaSafety = false;
  ultimoPiscaSafety = 0;

  digitalWrite(LED_VERDE, LOW);
  digitalWrite(LED_VERMELHO, LOW);
}

void pararSafetyCar() {
  safetyAtivo = false;
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERDE, HIGH);
  ledSafetyVerde();
}

void atualizarSafetyCar() {
  if (!safetyAtivo) {
    return;
  }

  unsigned long agora = millis();

  if (agora - ultimoPiscaSafety >= INTERVALO_SAFETY) {
    ultimoPiscaSafety = agora;
    estadoPiscaSafety = !estadoPiscaSafety;

    digitalWrite(LED_AMARELO, estadoPiscaSafety ? HIGH : LOW);

    if (estadoPiscaSafety) {
      ledSafetyAmarelo();
    } else {
      ledSafetyDesligar();
    }
  }
}

void desligarSaidas() {
  safetyAtivo = false;
  digitalWrite(LED_VERMELHO, LOW);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERDE, LOW);
  digitalWrite(RELE, LOW);
  iniciarArcoIrisSafety();
}
