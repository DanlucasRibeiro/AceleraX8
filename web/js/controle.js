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

function coletarCorredores() {
    const corredores = {};
    document.querySelectorAll("[data-cor]").forEach(input => {
        const nome = input.value.trim();

        if (nome) {
            corredores[input.dataset.cor] = nome;
        }
    });
    return corredores;
}

function validarCorredores(corredores) {
    if (Object.keys(corredores).length > 0) {
        return true;
    }

    alert("Informe o nome de pelo menos um corredor para iniciar a corrida.");
    return false;
}

function iniciarCorrida() {
    const corredores = coletarCorredores();
    if (!validarCorredores(corredores)) return;
    const tempoLimiteSegundos = Number(document.getElementById("tempoLimite").value) * 60;

    enviar("start", {
        voltas_limite: Number(document.getElementById("voltasLimite").value),
        tempo_limite: tempoLimiteSegundos,
        corredores
    });
}

function reiniciarCorrida() {
    const corredores = coletarCorredores();
    if (!validarCorredores(corredores)) return;
    const tempoLimiteSegundos = Number(document.getElementById("tempoLimite").value) * 60;

    enviar("restart", {
        voltas_limite: Number(document.getElementById("voltasLimite").value),
        tempo_limite: tempoLimiteSegundos,
        corredores
    });
}

function zerarCorrida() {
    enviar("reset");
}

function alternarSafetyCar() {
    enviar("safety_toggle");
}

function finalizarCorrida() {
    enviar("finish");
}

function reconectarSistema() {
    enviar("camera_reconnect");

    if (ws) {
        ws.onclose = null;
        ws.close();
    }

    setTimeout(conectar, 250);
}

function atualizarCorrida(corrida) {
    if (!corrida) return;

    document.getElementById("raceStatus").innerText = corrida.status || "aguardando";
    document.getElementById("raceTime").innerText = formatarRelogio(corrida.tempo_restante);
    document.getElementById("cameraStatus").innerText = corrida.camera_conectada ? "Conectada" : "Desconectada";
    const corridaEmAndamento = ["preparando", "correndo"].includes(corrida.status);
    document.getElementById("btnStart").disabled = corridaEmAndamento;
    document.getElementById("btnRestart").disabled = false;
    document.getElementById("btnReset").disabled = corrida.status === "aguardando";
    document.getElementById("btnFinish").disabled = !corridaEmAndamento;

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

function escaparHtml(valor) {
    return String(valor || "").replace(/[&<>"']/g, caractere => ({
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;"
    }[caractere]));
}

function atualizarTabela(data) {
    const tbody = document.getElementById("tbody");
    const ranking = [...data].sort((a, b) => {
        if (b.voltas !== a.voltas) return b.voltas - a.voltas;
        return (a.melhor || 999999) - (b.melhor || 999999);
    });

    if (ranking.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty-table">Informe pelo menos um corredor</td></tr>`;
        ultimoEstado = {};
        return;
    }

    const emptyRow = tbody.querySelector(".empty-table");
    if (emptyRow) {
        emptyRow.closest("tr").remove();
    }

    ranking.forEach((carro, i) => {
        let tr = document.getElementById("row-" + carro.cor);

        if (!tr) {
            tr = document.createElement("tr");
            tr.id = "row-" + carro.cor;
        }

        tr.className = "";
        if (i === 0) tr.classList.add("pos1");
        if (i === 1) tr.classList.add("pos2");
        if (i === 2) tr.classList.add("pos3");

        const cor = escaparHtml(carro.cor);
        const nome = escaparHtml(carro.nome);

        tr.innerHTML = `
            <td>${i + 1}</td>
            <td><span class="color-name">${cor}</span> ${nome}</td>
            <td>${carro.voltas}</td>
            <td>${formatarTempo(carro.ultima)}</td>
            <td>${formatarTempo(carro.melhor)}</td>
        `;

        tbody.appendChild(tr);
    });

    Object.keys(ultimoEstado).forEach(nome => {
        if (!ranking.find(c => c.cor === nome)) {
            const el = document.getElementById("row-" + nome);
            if (el) el.remove();
        }
    });

    ultimoEstado = {};
    ranking.forEach(c => ultimoEstado[c.cor] = c);
}

conectar();
