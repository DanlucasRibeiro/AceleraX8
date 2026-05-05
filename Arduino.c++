const int LED_VERMELHO = 5;
const int LED_AMARELO = 6;
const int LED_VERDE = 7;
const int RELE = 8;
const int LED_SAFETY = 10;

bool safetyAtivo = false;
bool estadoPiscaSafety = false;
unsigned long ultimoPiscaSafety = 0;
const unsigned long INTERVALO_SAFETY = 300;

void setup() {
  Serial.begin(9600);

  pinMode(LED_VERMELHO, OUTPUT);
  pinMode(LED_AMARELO, OUTPUT);
  pinMode(LED_VERDE, OUTPUT);
  pinMode(RELE, OUTPUT);
  pinMode(LED_SAFETY, OUTPUT);

  digitalWrite(LED_VERMELHO, LOW);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERDE, LOW);
  digitalWrite(RELE, LOW);
  digitalWrite(LED_SAFETY, LOW);
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
}

void acionarSemaforoCorrida() {
  safetyAtivo = false;
  digitalWrite(LED_SAFETY, LOW);

  // Vermelho aceso
  digitalWrite(LED_VERMELHO, HIGH);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERDE, LOW);
  delay(2000);

  // Vermelho e amarelo juntos
  digitalWrite(LED_AMARELO, HIGH);
  delay(1000);

  // Verde aceso
  digitalWrite(LED_VERMELHO, LOW);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERDE, HIGH);
  acionarRele(true);
}

void acionarRele(bool ligar) {
  digitalWrite(RELE, ligar ? HIGH : LOW);
}

void iniciarSafetyCar() {
  safetyAtivo = true;
  estadoPiscaSafety = false;
  ultimoPiscaSafety = 0;

  digitalWrite(LED_VERDE, LOW);
  digitalWrite(LED_VERMELHO, LOW);
}

void pararSafetyCar() {
  safetyAtivo = false;
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_SAFETY, LOW);
  digitalWrite(LED_VERDE, HIGH);
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
    digitalWrite(LED_SAFETY, estadoPiscaSafety ? HIGH : LOW);
  }
}

void desligarSaidas() {
  safetyAtivo = false;
  digitalWrite(LED_VERMELHO, LOW);
  digitalWrite(LED_AMARELO, LOW);
  digitalWrite(LED_VERDE, LOW);
  digitalWrite(RELE, LOW);
  digitalWrite(LED_SAFETY, LOW);
}
