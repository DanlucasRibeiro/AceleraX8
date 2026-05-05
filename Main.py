import cv2
import numpy as np
import time
import csv
import os
import sys
import webbrowser

try:
    import serial
except ImportError:
    serial = None

from server import comandos, config_corrida, estado_corrida, start_server_background

# =========================
# CONFIGURAÇÕES GERAIS
# =========================

CAMERA_INDEX = None  # None = procurar camera automaticamente. Use 0, 1, 2... para fixar.
ARDUINO_PORT = None  # None = procurar automaticamente. Exemplo manual: "COM3"
ARDUINO_BAUD = 9600
TEMPO_SEMAFORO = 3.0  # segundos ate a largada apos enviar START ao Arduino
TEMPO_TELAO_ESTATICO = 300  # segundos mantendo o telao aberto apos finalizar pelo botao
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

LINHA_Y = 300  # posição da linha de chegada (ajustar!)
COOLDOWN = 2.0  # tempo mínimo entre voltas (segundos)
AREA_MIN = 800  # área mínima para considerar objeto

# =========================
# CONFIGURAÇÃO DAS CORES (HSV)
# AJUSTAR CONFORME NECESSÁRIO
# =========================

carros = {
    "vermelho": {
        "lower": np.array([0, 150, 100]),
        "upper": np.array([10, 255, 255]),
        "cor_bgr": (0, 0, 255)
    },
    "azul": {
        "lower": np.array([100, 150, 50]),
        "upper": np.array([130, 255, 255]),
        "cor_bgr": (255, 0, 0)
    },
    "verde": {
        "lower": np.array([40, 100, 50]),
        "upper": np.array([80, 255, 255]),
        "cor_bgr": (0, 255, 0)
    },
    "amarelo": {
        "lower": np.array([20, 150, 150]),
        "upper": np.array([35, 255, 255]),
        "cor_bgr": (0, 255, 255)
    },
    "roxo": {
        "lower": np.array([130, 80, 80]),
        "upper": np.array([160, 255, 255]),
        "cor_bgr": (255, 0, 255)
    },
    "laranja": {
        "lower": np.array([10, 150, 150]),
        "upper": np.array([20, 255, 255]),
        "cor_bgr": (0, 165, 255)
    },
}

# =========================
# ESTADO DOS CARROS
# =========================

estado = estado_corrida  # referência ao estado compartilhado com o servidor

arduino = None
corrida_inicio = None
aguardando_largada_ate = None
tempo_pausado_total = 0
safety_inicio = None
encerrar_camera = False
manter_telao_estatico = False
voltas_limite = config_corrida["voltas_limite"]
tempo_limite = config_corrida["tempo_limite"]

for nome in carros:
    estado[nome] = {
        "ultima_pos": None,
        "ultima_passagem": 0,
        "voltas": 0,
        "melhor_volta": None,
        "ultima_volta": None,
        "tempo_inicio": time.perf_counter()
    }

start_server_background()

def caminho_recurso(nome_arquivo):
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, nome_arquivo)

painel_web = caminho_recurso("index.html").replace(os.sep, "/")
webbrowser.open(f"file:///{painel_web}")
print("Painel web aberto no navegador.")

def resetar_corrida():
    agora = time.perf_counter()

    for dados in estado.values():
        dados["ultima_pos"] = None
        dados["ultima_passagem"] = agora
        dados["voltas"] = 0
        dados["melhor_volta"] = None
        dados["ultima_volta"] = None
        dados["tempo_inicio"] = agora

def abrir_arduino():
    if serial is None:
        print("PySerial nao instalado. Semaforo do Arduino nao sera acionado.")
        return None

    portas = [ARDUINO_PORT] if ARDUINO_PORT else [f"COM{i}" for i in range(1, 21)]

    for porta in portas:
        try:
            conexao = serial.Serial(porta, ARDUINO_BAUD, timeout=1)
            time.sleep(2)
            print(f"Arduino conectado em {porta}.")
            return conexao
        except serial.SerialException:
            pass

    print("Arduino nao encontrado. A corrida inicia, mas o semaforo nao sera acionado.")
    return None

def acionar_semaforo():
    if arduino and arduino.is_open:
        arduino.write(b"START\n")
        print("Comando START enviado ao Arduino.")

def enviar_arduino(comando):
    if arduino and arduino.is_open:
        arduino.write(f"{comando}\n".encode("ascii"))
        print(f"Comando {comando} enviado ao Arduino.")

def iniciar_corrida(comando):
    global corrida_inicio, aguardando_largada_ate, voltas_limite, tempo_limite
    global tempo_pausado_total, safety_inicio

    voltas_limite = comando["voltas_limite"]
    tempo_limite = comando["tempo_limite"]
    tempo_pausado_total = 0
    safety_inicio = None
    resetar_corrida()
    acionar_semaforo()

    aguardando_largada_ate = time.perf_counter() + TEMPO_SEMAFORO
    corrida_inicio = None
    config_corrida.update({
        "status": "preparando",
        "voltas_limite": voltas_limite,
        "tempo_limite": tempo_limite,
        "tempo_restante": tempo_limite,
        "safety_car": False
    })
    print(f"Corrida preparada: {voltas_limite} voltas ou {tempo_limite}s.")

def alternar_safety_car():
    global tempo_pausado_total, safety_inicio

    if config_corrida["status"] != "correndo":
        return

    agora = time.perf_counter()

    if config_corrida.get("safety_car"):
        tempo_pausado_total += agora - safety_inicio
        safety_inicio = None
        config_corrida["safety_car"] = False
        enviar_arduino("SAFETY_OFF")
        print("Safety Car encerrado. Cronometro retomado.")
    else:
        safety_inicio = agora
        config_corrida["safety_car"] = True
        enviar_arduino("SAFETY_ON")
        print("Safety Car acionado. Cronometro pausado.")

def finalizar_corrida(manter_telao=True):
    global encerrar_camera, manter_telao_estatico, safety_inicio

    if config_corrida.get("safety_car"):
        enviar_arduino("SAFETY_OFF")

    enviar_arduino("STOP")
    config_corrida["status"] = "finalizada"
    config_corrida["safety_car"] = False
    safety_inicio = None
    encerrar_camera = True
    manter_telao_estatico = manter_telao
    print("Finalizacao solicitada. Camera sera encerrada e relatorio sera gerado.")

def processar_comandos():
    while comandos:
        comando = comandos.pop(0)
        if comando.get("tipo") == "start":
            iniciar_corrida(comando)
        elif comando.get("tipo") == "safety_toggle":
            alternar_safety_car()
        elif comando.get("tipo") == "finish":
            finalizar_corrida(manter_telao=True)

def atualizar_estado_corrida():
    global corrida_inicio, aguardando_largada_ate

    agora = time.perf_counter()

    if aguardando_largada_ate is not None and agora >= aguardando_largada_ate:
        corrida_inicio = agora
        aguardando_largada_ate = None
        config_corrida["status"] = "correndo"
        print("Corrida iniciada.")

    if config_corrida["status"] != "correndo" or corrida_inicio is None:
        return

    relogio_agora = safety_inicio if config_corrida.get("safety_car") else agora
    decorrido = relogio_agora - corrida_inicio - tempo_pausado_total
    restante = max(0, tempo_limite - decorrido)
    config_corrida["tempo_restante"] = restante

    finalizou_voltas = any(dados["voltas"] >= voltas_limite for dados in estado.values())

    if restante <= 0 or finalizou_voltas:
        config_corrida["tempo_restante"] = restante
        finalizar_corrida(manter_telao=True)
        print("Corrida finalizada.")

def corrida_ativa():
    return config_corrida["status"] == "correndo"

# =========================
# INICIALIZAÇÃO DA CÂMERA
# =========================

def abrir_camera():
    indices = [CAMERA_INDEX] if CAMERA_INDEX is not None else range(5)

    for indice in indices:
        camera = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

        if camera.isOpened():
            ret, _ = camera.read()
            if ret:
                print(f"Camera encontrada no indice {indice}.")
                return camera

        camera.release()

    raise RuntimeError(
        "Nenhuma camera disponivel foi encontrada. "
        "Verifique se a camera esta conectada e nao esta aberta em outro programa."
    )

cap = abrir_camera()
cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

kernel = np.ones((5, 5), np.uint8)
arduino = abrir_arduino()

# =========================
# FUNÇÃO: DETECTAR CENTRO
# =========================

def detectar_centro(mask):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        maior = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(maior)

        if area > AREA_MIN:
            x, y, w, h = cv2.boundingRect(maior)
            cx = int(x + w / 2)
            cy = int(y + h / 2)
            return cx, cy, x, y, w, h

    return None

# =========================
# LOOP PRINCIPAL
# =========================

while True:
    processar_comandos()
    atualizar_estado_corrida()

    if encerrar_camera:
        break

    ret, frame = cap.read()
    if not ret:
        break

    frame = cv2.flip(frame, 0)  # ajustar se necessário
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    agora = time.perf_counter()

    # desenhar linha de chegada
    cv2.line(frame, (0, LINHA_Y), (FRAME_WIDTH, LINHA_Y), (255, 255, 255), 2)

    for nome, config in carros.items():
        mask = cv2.inRange(hsv, config["lower"], config["upper"])
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        resultado = detectar_centro(mask)

        if resultado:
            cx, cy, x, y, w, h = resultado

            # desenhar bounding box
            cv2.rectangle(frame, (x, y), (x+w, y+h), config["cor_bgr"], 2)
            cv2.circle(frame, (cx, cy), 5, config["cor_bgr"], -1)

            prev = estado[nome]["ultima_pos"]

            # DETECÇÃO DE CRUZAMENTO
            if corrida_ativa() and prev is not None:
                if prev > LINHA_Y and cy <= LINHA_Y:
                    tempo_desde_ultima = agora - estado[nome]["ultima_passagem"]

                    if tempo_desde_ultima > COOLDOWN:
                        estado[nome]["voltas"] += 1

                        tempo_volta = agora - estado[nome]["ultima_passagem"]
                        estado[nome]["ultima_passagem"] = agora
                        estado[nome]["ultima_volta"] = tempo_volta

                        if (estado[nome]["melhor_volta"] is None or 
                            tempo_volta < estado[nome]["melhor_volta"]):
                            estado[nome]["melhor_volta"] = tempo_volta

                        print(f"{nome} - Volta {estado[nome]['voltas']} - {tempo_volta:.2f}s")

            estado[nome]["ultima_pos"] = cy

    # =========================
    # RANKING
    # =========================

    ranking = sorted(
        estado.items(),
        key=lambda x: (-x[1]["voltas"], x[1]["melhor_volta"] or 9999)
    )

    y_texto = 30

    for i, (nome, dados) in enumerate(ranking):
        texto = f"{i+1}º {nome} | Voltas: {dados['voltas']} | Ult: {dados['ultima_volta'] or 0:.2f}s | Best: {dados['melhor_volta'] or 0:.2f}s"
        cv2.putText(frame, texto, (10, y_texto), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,255), 2)
        y_texto += 25

    cv2.imshow("Sistema de Corrida RC", frame)

    key = cv2.waitKey(1)

    if key == 27:  # ESC para sair
        manter_telao_estatico = False
        break

# =========================
# EXPORTAR CSV
# =========================

with open("resultado_corrida.csv", "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["Posicao", "Carro", "Voltas", "Ultima Volta", "Melhor Volta"])

    ranking_final = sorted(
        estado.items(),
        key=lambda x: (-x[1]["voltas"], x[1]["melhor_volta"] or 9999)
    )

    for posicao, (nome, dados) in enumerate(ranking_final, start=1):
        writer.writerow([
            posicao,
            nome,
            dados["voltas"],
            round(dados["ultima_volta"], 2) if dados["ultima_volta"] else 0,
            round(dados["melhor_volta"], 2) if dados["melhor_volta"] else 0
        ])

print("Resultado exportado para resultado_corrida.csv")

cap.release()
if arduino and arduino.is_open:
    arduino.close()
cv2.destroyAllWindows()

if manter_telao_estatico:
    print(f"Telao mantido estatico por {TEMPO_TELAO_ESTATICO} segundos.")
    time.sleep(TEMPO_TELAO_ESTATICO)
