let ws;
let ultimoEstado = {};

function conectar() {
    const host = window.location.hostname || "localhost";
    ws = new WebSocket(`ws://${host}:8765`);

    ws.onopen = () => {
        document.getElementById("status").innerText = "Conectado";
        document.getElementById("status").className = "status connected";
    };

    ws.onclose = () => {
        document.getElementById("status").innerText = "Reconectando...";
        document.getElementById("status").className = "status disconnected";
        setTimeout(conectar, 2000);
    };

    ws.onerror = () => {
        ws.close();
    };

    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            atualizarCorrida(data.corrida);
            atualizarTabela(data.carros || []);
        } catch (e) {
            console.error("Erro ao processar dados:", e);
        }
    };
}

function enviar(tipo, dados = {}) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ tipo, ...dados }));
}

function iniciarCorrida() {
    enviar("start", {
        voltas_limite: Number(document.getElementById("voltasLimite").value),
        tempo_limite: Number(document.getElementById("tempoLimite").value)
    });
}

function alternarSafetyCar() {
    enviar("safety_toggle");
}

function finalizarCorrida() {
    enviar("finish");
}

function atualizarCorrida(corrida) {
    if (!corrida) return;

    document.getElementById("raceStatus").innerText = corrida.status || "aguardando";
    document.getElementById("raceTime").innerText = formatarRelogio(corrida.tempo_restante);
    document.getElementById("btnStart").disabled = ["preparando", "correndo"].includes(corrida.status);
    document.getElementById("btnFinish").disabled = !["preparando", "correndo"].includes(corrida.status);

    const safetyAtivo = Boolean(corrida.safety_car);
    const btnSafety = document.getElementById("btnSafety");
    btnSafety.disabled = corrida.status !== "correndo";
    btnSafety.innerText = safetyAtivo ? "Encerrar Safety Car" : "Safety Car";
    btnSafety.classList.toggle("active", safetyAtivo);
}

function formatarRelogio(segundos) {
    if (segundos === undefined || segundos === null) return "--";
    const total = Math.max(0, Math.ceil(segundos));
    const min = Math.floor(total / 60);
    const sec = total % 60;
    return `${min}:${String(sec).padStart(2, "0")}`;
}

function formatarTempo(valor) {
    if (!valor || valor === 0) return "--";
    return valor.toFixed(2) + " s";
}

function atualizarTabela(data) {
    const tbody = document.getElementById("tbody");
    const ranking = [...data].sort((a, b) => {
        if (b.voltas !== a.voltas) return b.voltas - a.voltas;
        return (a.melhor || 999999) - (b.melhor || 999999);
    });

    ranking.forEach((carro, i) => {
        let tr = document.getElementById("row-" + carro.nome);

        if (!tr) {
            tr = document.createElement("tr");
            tr.id = "row-" + carro.nome;
        }

        tr.className = "";
        if (i === 0) tr.classList.add("pos1");
        if (i === 1) tr.classList.add("pos2");
        if (i === 2) tr.classList.add("pos3");

        tr.innerHTML = `
            <td>${i + 1}</td>
            <td>${carro.nome}</td>
            <td>${carro.voltas}</td>
            <td>${formatarTempo(carro.ultima)}</td>
            <td>${formatarTempo(carro.melhor)}</td>
        `;

        tbody.appendChild(tr);
    });

    Object.keys(ultimoEstado).forEach(nome => {
        if (!ranking.find(c => c.nome === nome)) {
            const el = document.getElementById("row-" + nome);
            if (el) el.remove();
        }
    });

    ultimoEstado = {};
    ranking.forEach(c => ultimoEstado[c.nome] = c);
}

conectar();
