import asyncio
import websockets
import json
import threading

clients = set()
estado_corrida = {}
comandos = []
config_corrida = {
    "status": "aguardando",
    "voltas_limite": 10,
    "tempo_limite": 300,
    "tempo_restante": 300,
    "safety_car": False,
    "camera_conectada": False
}

async def processar_mensagem(message):
    try:
        dados = json.loads(message)
    except json.JSONDecodeError:
        return

    if dados.get("tipo") in ("start", "restart"):
        voltas = max(1, int(dados.get("voltas_limite", 10)))
        tempo = max(1, int(dados.get("tempo_limite", 300)))

        config_corrida.update({
            "status": "preparando",
            "voltas_limite": voltas,
            "tempo_limite": tempo,
            "tempo_restante": tempo,
            "safety_car": False
        })

        comandos.append({
            "tipo": dados.get("tipo"),
            "voltas_limite": voltas,
            "tempo_limite": tempo,
            "corredores": dados.get("corredores", {})
        })

    if dados.get("tipo") == "safety_toggle":
        comandos.append({
            "tipo": "safety_toggle"
        })

    if dados.get("tipo") == "finish":
        comandos.append({
            "tipo": "finish"
        })

    if dados.get("tipo") == "reset":
        config_corrida.update({
            "status": "aguardando",
            "tempo_restante": config_corrida.get("tempo_limite", 300),
            "safety_car": False
        })
        comandos.append({
            "tipo": "reset"
        })

    if dados.get("tipo") == "camera_reconnect":
        comandos.append({
            "tipo": "camera_reconnect"
        })

# -------------------------
# Conexão de clientes
# -------------------------
async def handler(websocket):
    clients.add(websocket)
    try:
        async for message in websocket:
            await processar_mensagem(message)
    finally:
        clients.discard(websocket)

# -------------------------
# Broadcast contínuo
# -------------------------
async def broadcast():
    while True:
        if clients:
            carros = []

            for nome, d in list(estado_corrida.items()):
                carros.append({
                    "cor": d.get("cor", nome),
                    "nome": d.get("nome") or nome,
                    "voltas": d["voltas"],
                    "ultima": d["ultima_volta"] or 0,
                    "melhor": d["melhor_volta"] or 0,
                    "largou": d.get("largou", False)
                })

            carros.sort(key=lambda x: (-x["voltas"], x["melhor"] or 9999))

            msg = json.dumps({
                "tipo": "estado",
                "corrida": config_corrida,
                "carros": carros
            })

            # envia para todos conectados
            await asyncio.gather(*[c.send(msg) for c in clients], return_exceptions=True)

        await asyncio.sleep(0.1)

# -------------------------
# MAIN CORRETO
# -------------------------
async def main():
    server = await websockets.serve(handler, "0.0.0.0", 8765)

    print("Servidor WebSocket rodando em ws://localhost:8765")

    # cria task paralela
    asyncio.create_task(broadcast())

    # mantém servidor vivo
    await asyncio.Future()

# -------------------------
# START
# -------------------------
def start_server_background():
    thread = threading.Thread(target=lambda: asyncio.run(main()), daemon=True)
    thread.start()
    return thread

if __name__ == "__main__":
    asyncio.run(main())
