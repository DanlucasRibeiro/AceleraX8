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

try:
    import winsound
except ImportError:
    winsound = None

from server import comandos, config_corrida, estado_corrida, start_server_background

# =========================
# CONFIGURAÇÕES GERAIS
# =========================

CAMERA_INDEX = 0  # None = procurar camera automaticamente. Use 0, 1, 2... para fixar.
ARDUINO_PORT = None  # None = procurar automaticamente. Exemplo manual: "COM3"
ARDUINO_BAUD = 9600
TEMPO_SEMAFORO = 3.0  # segundos ate a largada apos enviar START ao Arduino
TEMPO_TELAO_ESTATICO = 300  # segundos mantendo o telao aberto apos finalizar pelo botao
CAMERA_RECONNECT_INTERVAL = 2.0
AUDIO_LARGADA = os.path.join("assets", "ContagemRegressiva.wav")
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720

LINHA_Y = 300  # posição da linha de chegada (ajustar!)
COOLDOWN = 15.0  # tempo mínimo entre voltas (segundos)
AREA_MIN = 800  # área mínima para considerar objeto

# =========================
# CONFIGURAÇÃO DAS CORES (HSV)
# AJUSTAR CONFORME NECESSÁRIO
# =========================

carros = {
    "vermelho": {
        "ranges": [
            (np.array([0, 170, 120]), np.array([8, 255, 255])),
            (np.array([170, 170, 120]), np.array([179, 255, 255])),
        ],
        "cor_bgr": (0, 0, 255)
    },
    "azul": {
        "lower": np.array([95, 100, 60]),
        "upper": np.array([130, 255, 255]),
        "cor_bgr": (255, 0, 0)
    },
    "verde": {
        "lower": np.array([40, 80, 50]),
        "upper": np.array([85, 255, 255]),
        "cor_bgr": (0, 255, 0)
    },
    "amarelo": {
        "lower": np.array([20, 130, 130]),
        "upper": np.array([35, 255, 255]),
        "cor_bgr": (0, 255, 255)
    },
    "roxo": {
        "lower": np.array([125, 60, 30]),
        "upper": np.array([160, 255, 170]),
        "cor_bgr": (128, 0, 128)
    },
    "marrom": {
        "lower": np.array([5, 70, 35]),
        "upper": np.array([25, 255, 150]),
        "cor_bgr": (42, 42, 165)
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
resultado_exportado = False
cap = None
ultima_tentativa_camera = 0

for nome in carros:
    estado[nome] = {
        "cor": nome,
        "nome": nome,
        "ultima_pos": None,
        "ultima_passagem": 0,
        "voltas": 0,
        "melhor_volta": None,
        "ultima_volta": None,
        "largou": False,
        "tempo_inicio": time.perf_counter()
    }

start_server_background()

config_corrida["camera_conectada"] = False

def caminho_recurso(nome_arquivo):
    base = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base, nome_arquivo)

telao_web = caminho_recurso(os.path.join("web", "index.html")).replace(os.sep, "/")
controle_web = caminho_recurso(os.path.join("web", "controle.html")).replace(os.sep, "/")
webbrowser.open(f"file:///{telao_web}")
webbrowser.open(f"file:///{controle_web}")
print("Telao e painel de controle abertos no navegador.")

def resetar_corrida():
    agora = time.perf_counter()

    for dados in estado.values():
        dados["ultima_pos"] = None
        dados["ultima_passagem"] = agora
        dados["voltas"] = 0
        dados["melhor_volta"] = None
        dados["ultima_volta"] = None
        dados["largou"] = False
        dados["tempo_inicio"] = agora

def aplicar_nomes_corredores(nomes_corredores):
    if not isinstance(nomes_corredores, dict):
        return

    for cor, nome_digitado in nomes_corredores.items():
        if cor not in estado:
            continue

        nome_limpo = str(nome_digitado).strip()
        estado[cor]["nome"] = nome_limpo or cor

def exportar_resultado():
    global resultado_exportado

    output_dir = os.path.join(os.path.abspath("."), "output")
    os.makedirs(output_dir, exist_ok=True)
    resultado_csv = os.path.join(output_dir, "resultado_corrida.csv")

    with open(resultado_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Posicao", "Carro", "Voltas", "Ultima Volta", "Melhor Volta"])

        ranking_final = sorted(
            estado.items(),
            key=lambda x: (-x[1]["voltas"], x[1]["melhor_volta"] or 9999)
        )

        for posicao, (nome, dados) in enumerate(ranking_final, start=1):
            writer.writerow([
                posicao,
                dados.get("nome") or nome,
                dados["voltas"],
                round(dados["ultima_volta"], 2) if dados["ultima_volta"] else 0,
                round(dados["melhor_volta"], 2) if dados["melhor_volta"] else 0
            ])

    resultado_exportado = True
    print(f"Resultado exportado para {resultado_csv}")

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
    tocar_som_largada()

def tocar_som_largada():
    if winsound is None:
        print("Som de largada indisponivel neste sistema.")
        return

    caminho_audio = caminho_recurso(AUDIO_LARGADA)

    if not os.path.exists(caminho_audio):
        print(f"Audio de largada nao encontrado: {caminho_audio}")
        return

    winsound.PlaySound(caminho_audio, winsound.SND_FILENAME | winsound.SND_ASYNC)

def enviar_arduino(comando):
    if arduino and arduino.is_open:
        arduino.write(f"{comando}\n".encode("ascii"))
        print(f"Comando {comando} enviado ao Arduino.")

def iniciar_corrida(comando):
    global corrida_inicio, aguardando_largada_ate, voltas_limite, tempo_limite
    global tempo_pausado_total, safety_inicio, resultado_exportado

    voltas_limite = comando["voltas_limite"]
    tempo_limite = comando["tempo_limite"]
    tempo_pausado_total = 0
    safety_inicio = None
    resultado_exportado = False
    aplicar_nomes_corredores(comando.get("corredores"))
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

def zerar_corrida():
    global corrida_inicio, aguardando_largada_ate, tempo_pausado_total, safety_inicio
    global resultado_exportado

    if config_corrida.get("safety_car"):
        enviar_arduino("SAFETY_OFF")

    enviar_arduino("STOP")
    corrida_inicio = None
    aguardando_largada_ate = None
    tempo_pausado_total = 0
    safety_inicio = None
    resultado_exportado = False
    resetar_corrida()
    config_corrida.update({
        "status": "aguardando",
        "tempo_restante": tempo_limite,
        "safety_car": False
    })
    print("Corrida zerada. Sistema pronto para iniciar novamente.")

def finalizar_corrida(manter_telao=True):
    global corrida_inicio, aguardando_largada_ate, manter_telao_estatico, safety_inicio

    if config_corrida.get("safety_car"):
        enviar_arduino("SAFETY_OFF")

    enviar_arduino("STOP")
    corrida_inicio = None
    aguardando_largada_ate = None
    config_corrida["status"] = "finalizada"
    config_corrida["safety_car"] = False
    safety_inicio = None
    manter_telao_estatico = manter_telao
    exportar_resultado()
    print("Corrida finalizada. Sistema continua aberto para zerar ou iniciar novamente.")

def processar_comandos():
    while comandos:
        comando = comandos.pop(0)
        if comando.get("tipo") in ("start", "restart"):
            iniciar_corrida(comando)
        elif comando.get("tipo") == "safety_toggle":
            alternar_safety_car()
        elif comando.get("tipo") == "finish":
            finalizar_corrida(manter_telao=True)
        elif comando.get("tipo") == "reset":
            zerar_corrida()
        elif comando.get("tipo") == "camera_reconnect":
            reconectar_camera(forcar=True)

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

def reconectar_camera(forcar=False):
    global cap, ultima_tentativa_camera

    agora = time.perf_counter()
    if not forcar and agora - ultima_tentativa_camera < CAMERA_RECONNECT_INTERVAL:
        return cap is not None

    ultima_tentativa_camera = agora

    if cap is not None:
        cap.release()
        cap = None

    try:
        cap = abrir_camera()
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        config_corrida["camera_conectada"] = True
        print("Camera conectada.")
        return True
    except RuntimeError as erro:
        config_corrida["camera_conectada"] = False
        print(f"Falha ao conectar camera: {erro}")
        return False

reconectar_camera(forcar=True)

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

    ret, frame = cap.read() if cap is not None else (False, None)
    if not ret:
        config_corrida["camera_conectada"] = False
        reconectar_camera()
        frame = np.zeros((FRAME_HEIGHT, FRAME_WIDTH, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            "Camera desconectada - use Reconectar no painel",
            (70, FRAME_HEIGHT // 2),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (255, 255, 255),
            2
        )
        cv2.imshow("Sistema de Corrida RC", frame)
        key = cv2.waitKey(1)

        if key == 27:
            manter_telao_estatico = False
            break

        continue

    config_corrida["camera_conectada"] = True

    frame = cv2.flip(frame, 0)  # ajustar se necessário
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    agora = time.perf_counter()

    # desenhar linha de chegada
    cv2.line(frame, (0, LINHA_Y), (FRAME_WIDTH, LINHA_Y), (255, 255, 255), 2)

    for nome, config in carros.items():
        if "ranges" in config:
            mask = np.zeros(hsv.shape[:2], dtype=np.uint8)

            for lower, upper in config["ranges"]:
                mask = cv2.bitwise_or(mask, cv2.inRange(hsv, lower, upper))
        else:
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
                        if not estado[nome]["largou"]:
                            estado[nome]["largou"] = True
                            estado[nome]["tempo_inicio"] = agora
                            estado[nome]["ultima_passagem"] = agora
                            print(f"{nome} - Inicio registrado.")
                        else:
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
        nome_exibicao = dados.get("nome") or nome
        texto = f"{i+1}º {nome_exibicao} | Voltas: {dados['voltas']} | Ult: {dados['ultima_volta'] or 0:.2f}s | Best: {dados['melhor_volta'] or 0:.2f}s"
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

if not resultado_exportado:
    exportar_resultado()

if cap is not None:
    cap.release()
if arduino and arduino.is_open:
    arduino.close()
cv2.destroyAllWindows()

if manter_telao_estatico:
    print(f"Telao mantido estatico por {TEMPO_TELAO_ESTATICO} segundos.")
    time.sleep(TEMPO_TELAO_ESTATICO)
