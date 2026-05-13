import cv2


LIMITE_INDICES = 10
LARGURA_TESTE = 640
ALTURA_TESTE = 480


def testar_camera(indice):
    camera = cv2.VideoCapture(indice, cv2.CAP_DSHOW)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, LARGURA_TESTE)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, ALTURA_TESTE)

    aberta = camera.isOpened()
    ret, frame = camera.read() if aberta else (False, None)

    if ret and frame is not None:
        altura, largura = frame.shape[:2]
        print(f"Camera encontrada: indice {indice} ({largura}x{altura})")
        resultado = True
    else:
        resultado = False

    camera.release()
    return resultado


def main():
    encontradas = []

    print("Procurando cameras...")

    for indice in range(LIMITE_INDICES):
        if testar_camera(indice):
            encontradas.append(indice)

    if encontradas:
        print("\nUse um destes indices no Main.py:")
        for indice in encontradas:
            print(f"CAMERA_INDEX = {indice}")
    else:
        print("Nenhuma camera encontrada.")


if __name__ == "__main__":
    main()
