import csv
import os
import sys
import time
import webbrowser

import cv2
import numpy as np

from anti_duplicate import AntiDuplicate
from aruco_detector import ArucoDetector
from server import comandos, config_corrida, estado_corrida, start_server_background

try:
    import serial
except ImportError:
    serial = None

try:
    import winsound
except ImportError:
    winsound = None

# =========================
# CONFIGURACOES GERAIS
# =========================

CAMERA_INDEX = None  # None = procurar camera automaticamente. Use 0, 1, 2... para fixar.
ARDUINO_PORT = None  # None = procurar automaticamente. Exemplo manual: "COM3"
ARDUINO_BAUD = 9600
TEMPO_SEMAFORO = 3.0
TEMPO_TELAO_ESTATICO = 300
CAMERA_RECONNECT_INTERVAL = 2.0
AUDIO_LARGADA = os.path.join("assets", "ContagemRegressiva.wav")
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
TARGET_FPS = 60
CAMERA_ORIENTATION = "rotate_180"  # normal, rotate_180, flip_horizontal, flip_vertical

LINHA_Y = 300
FAIXA_ALTURA = 80
COOLDOWN = 2.0

# =========================
# CONFIGURACAO ARUCO
# =========================

CARROS_ARUCO = {
    1: {"cor": "vermelho", "nome": "Carro vermelho", "cor_bgr": (0, 0, 255)},
    2: {"cor": "verde", "nome": "Carro verde", "cor_bgr": (0, 255, 0)},
    3: {"cor": "amarelo", "nome": "Carro amarelo", "cor_bgr": (0, 255, 255)},
    4: {"cor": "azul", "nome": "Carro azul", "cor_bgr": (255, 0, 0)},
    5: {"cor": "marrom", "nome": "Carro marrom", "cor_bgr": (42, 42, 165)},
    6: {"cor": "roxo", "nome": "Carro roxo", "cor_bgr": (128, 0, 128)},
}

COR_POR_ID = {marker_id: dados["cor"] for marker_id, dados in CARROS_ARUCO.items()}
CONFIG_POR_COR = {dados["cor"]: dados for dados in CARROS_ARUCO.values()}

# =========================
# ESTADO DOS CARROS
# =========================

estado = estado_corrida

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

for marker_id, config in CARROS_ARUCO.items():
    cor = config["cor"]
    estado[cor] = {
        "id_aruco": marker_id,
        "cor": cor,
        "nome": config["nome"],
        "ultima_pos": None,
        "ultima_passagem": 0,
        "voltas": 0,
        "melhor_volta": None,
        "ultima_volta": None,
        "largou": False,
        "ativo": False,
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
    participantes = 0

    for cor, dados in estado.items():
        dados["ativo"] = False
        dados["nome"] = CONFIG_POR_COR[cor]["nome"]

    if not isinstance(nomes_corredores, dict):
        return 0

    for cor, nome_digitado in nomes_corredores.items():
        if cor not in estado:
            continue

        nome_limpo = str(nome_digitado).strip()
        if not nome_limpo:
            continue

        estado[cor]["nome"] = nome_limpo
        estado[cor]["ativo"] = True
        participantes += 1

    return participantes


def proximo_arquivo_resultado(output_dir):
    data_hoje = time.strftime("%d-%m-%Y")
    numero = 1

    while True:
        nome_arquivo = f"Corrida{numero:02d}-{data_hoje}.csv"
        caminho = os.path.join(output_dir, nome_arquivo)

        if not os.path.exists(caminho):
            return caminho

        numero += 1


def exportar_resultado():
    global resultado_exportado

    output_dir = os.path.join(os.path.abspath("."), "output")
    os.makedirs(output_dir, exist_ok=True)
    resultado_csv = proximo_arquivo_resultado(output_dir)

    with open(resultado_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Posicao", "Carro", "ID ArUco", "Voltas", "Ultima Volta", "Melhor Volta"])

        ranking_final = sorted(
            ((cor, dados) for cor, dados in estado.items() if dados.get("ativo")),
            key=lambda x: (-x[1]["voltas"], x[1]["melhor_volta"] or 9999)
        )

        for posicao, (cor, dados) in enumerate(ranking_final, start=1):
            writer.writerow([
                posicao,
                dados.get("nome") or cor,
                dados.get("id_aruco", ""),
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


def tocar_som_largada():
    if winsound is None:
        print("Som de largada indisponivel neste sistema.")
        return

    caminho_audio = caminho_recurso(AUDIO_LARGADA)

    if not os.path.exists(caminho_audio):
        print(f"Audio de largada nao encontrado: {caminho_audio}")
        return

    winsound.PlaySound(caminho_audio, winsound.SND_FILENAME | winsound.SND_ASYNC)


def acionar_semaforo():
    if arduino and arduino.is_open:
        arduino.write(b"START\n")
        print("Comando START enviado ao Arduino.")
    tocar_som_largada()


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
    participantes = aplicar_nomes_corredores(comando.get("corredores"))
    if participantes == 0:
        config_corrida.update({
            "status": "aguardando",
            "tempo_restante": tempo_limite,
            "safety_car": False
        })
        print("Informe pelo menos um corredor antes de iniciar a corrida.")
        return

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

    finalizou_voltas = any(
        dados["voltas"] >= voltas_limite
        for dados in estado.values()
        if dados.get("ativo")
    )

    if restante <= 0 or finalizou_voltas:
        config_corrida["tempo_restante"] = restante
        finalizar_corrida(manter_telao=True)
        print("Corrida finalizada.")


def corrida_ativa():
    return config_corrida["status"] == "correndo"


# =========================
# CAMERA E DETECCAO
# =========================

def gpu_available():
    try:
        count = cv2.cuda.getCudaEnabledDeviceCount()
        return count > 0
    except Exception:
        return False


def abrir_camera():
    indices = [CAMERA_INDEX] if CAMERA_INDEX is not None else range(5)

    for indice in indices:
        camera = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
        camera.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        camera.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        camera.set(cv2.CAP_PROP_FPS, TARGET_FPS)

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
        cap.set(cv2.CAP_PROP_FPS, TARGET_FPS)
        config_corrida["camera_conectada"] = True
        print("Camera conectada.")
        return True
    except RuntimeError as erro:
        config_corrida["camera_conectada"] = False
        print(f"Falha ao conectar camera: {erro}")
        return False


def preprocess_frame(frame, use_gpu=False):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.equalizeHist(gray)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    if use_gpu:
        try:
            gpu_mat = cv2.cuda_GpuMat()
            gpu_mat.upload(gray)
            gpu_result = cv2.cuda.GaussianBlur(gpu_mat, (5, 5), 0)
            return gpu_result.download()
        except Exception:
            pass

    return cv2.GaussianBlur(gray, (5, 5), 0)


def ajustar_orientacao_camera(frame):
    if CAMERA_ORIENTATION == "normal":
        return frame

    if CAMERA_ORIENTATION == "rotate_180":
        return cv2.rotate(frame, cv2.ROTATE_180)

    if CAMERA_ORIENTATION == "flip_horizontal":
        return cv2.flip(frame, 1)

    if CAMERA_ORIENTATION == "flip_vertical":
        return cv2.flip(frame, 0)

    print(f"Orientacao de camera invalida: {CAMERA_ORIENTATION}. Usando imagem normal.")
    return frame


def get_finish_zone(frame):
    height, width = frame.shape[:2]
    line_y = min(max(LINHA_Y, 0), height)
    half_zone = FAIXA_ALTURA // 2
    return (0, max(0, line_y - half_zone), width, min(height, line_y + half_zone))


def draw_finish_zone(frame, zone):
    x1, y1, x2, y2 = zone
    overlay = frame.copy()

    cv2.rectangle(overlay, (x1, y1), (x2, y2), (255, 180, 0), -1)
    cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
    cv2.rectangle(frame, (x1, y1), (x2, y2), (255, 180, 0), 2)
    cv2.line(frame, (x1, LINHA_Y), (x2, LINHA_Y), (255, 255, 255), 2)
    cv2.putText(
        frame,
        "FAIXA DE CONTAGEM ARUCO",
        (10, max(25, y1 - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.7,
        (255, 255, 0),
        2,
        cv2.LINE_AA,
    )


def draw_detection(frame, detection, cor, nome_exibicao):
    config = CONFIG_POR_COR[cor]
    corners = detection["corners"].astype(int)
    center = (detection["x"], detection["y"])

    cv2.polylines(frame, [corners], True, config["cor_bgr"], 2)
    cv2.circle(frame, center, 5, config["cor_bgr"], -1)
    cv2.putText(
        frame,
        f"{nome_exibicao} | ID {detection['id']}",
        (corners[0][0], max(20, corners[0][1] - 10)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.6,
        config["cor_bgr"],
        2,
        cv2.LINE_AA,
    )


def registrar_passagem(cor, agora):
    dados = estado[cor]
    nome_exibicao = dados.get("nome") or cor

    if not dados["largou"]:
        dados["largou"] = True
        dados["tempo_inicio"] = agora
        dados["ultima_passagem"] = agora
        print(f"{nome_exibicao} - Inicio registrado.")
        return

    dados["voltas"] += 1

    tempo_volta = agora - dados["ultima_passagem"]
    dados["ultima_passagem"] = agora
    dados["ultima_volta"] = tempo_volta

    if dados["melhor_volta"] is None or tempo_volta < dados["melhor_volta"]:
        dados["melhor_volta"] = tempo_volta

    print(f"{nome_exibicao} - Volta {dados['voltas']} - {tempo_volta:.2f}s")


def desenhar_ranking(frame):
    ranking = sorted(
        ((cor, dados) for cor, dados in estado.items() if dados.get("ativo")),
        key=lambda x: (-x[1]["voltas"], x[1]["melhor_volta"] or 9999)
    )

    y_texto = 30

    for i, (cor, dados) in enumerate(ranking):
        nome_exibicao = dados.get("nome") or cor
        texto = (
            f"{i + 1}o {nome_exibicao} | ID {dados.get('id_aruco')} | "
            f"Voltas: {dados['voltas']} | Ult: {dados['ultima_volta'] or 0:.2f}s | "
            f"Best: {dados['melhor_volta'] or 0:.2f}s"
        )
        cv2.putText(frame, texto, (10, y_texto), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
        y_texto += 25


reconectar_camera(forcar=True)
arduino = abrir_arduino()
detector = ArucoDetector()
anti_duplicate = AntiDuplicate(cooldown=COOLDOWN)
use_gpu = gpu_available()

if use_gpu:
    print("GPU detectada. Usando pre-processamento com GPU quando possivel.")
else:
    print("GPU nao detectada. Usando CPU para captura e deteccao.")

print("Deteccao ArUco ativa.")
print("IDs configurados: 1 vermelho, 2 verde, 3 amarelo, 4 azul, 5 marrom, 6 roxo.")

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

    frame = ajustar_orientacao_camera(frame)
    agora = time.perf_counter()
    finish_zone = get_finish_zone(frame)

    gray_frame = preprocess_frame(frame, use_gpu=use_gpu)
    detections = detector.detect(gray_frame)

    draw_finish_zone(frame, finish_zone)

    for detection in detections:
        marker_id = detection["id"]
        cor = COR_POR_ID.get(marker_id)

        if cor is None:
            cv2.putText(
                frame,
                f"ID {marker_id} nao configurado",
                (detection["x"] + 10, detection["y"]),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 0, 255),
                2,
                cv2.LINE_AA,
            )
            continue

        dados = estado[cor]
        if not dados.get("ativo"):
            continue

        nome_exibicao = dados.get("nome") or CONFIG_POR_COR[cor]["nome"]

        draw_detection(frame, detection, cor, nome_exibicao)
        dados["ultima_pos"] = (detection["x"], detection["y"])

        if corrida_ativa() and anti_duplicate.process_zone(marker_id, detection["x"], detection["y"], finish_zone):
            registrar_passagem(cor, agora)

    desenhar_ranking(frame)

    cv2.imshow("Sistema de Corrida RC", frame)

    key = cv2.waitKey(1)

    if key == 27:
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
