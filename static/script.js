document.addEventListener('DOMContentLoaded', () => {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('video-upload');
    const analyzeBtn = document.getElementById('analyze-btn');
    const resetBtn = document.getElementById('reset-btn');
    
    const uploadSection = document.getElementById('upload-section');
    const loadingSection = document.getElementById('loading-section');
    const resultsSection = document.getElementById('results-section');
    const loadingText = document.getElementById('loading-text');

    let selectedFile = null;
    let currentFileId = null;
    let currentTaskId = null;

    const errorBanner = document.getElementById('error-banner');
    const errorText = document.getElementById('error-text');

    function showError(msgStr) {
        let text = msgStr;
        if (text.includes('429') || text.includes('RESOURCE_EXHAUSTED')) {
            text = "⚠️ Has consumido la cuota gratuita máxima de peticiones diarias del modelo Gemini 2.5 Flash de tu llave actual. Por favor ingresa una API Key personalizada tuya (o de un amigo) en el campo superior para usar su cuota ilimitada nueva, o espera a que tu saldo se restaure mañana de manera automática.";
        }
        errorText.textContent = text;
        if (errorBanner) errorBanner.classList.remove('hidden');
    }

    function hideError() {
        if (errorBanner) errorBanner.classList.add('hidden');
    }

    // --- Drag and Drop Logic --- //
    dropzone.addEventListener('click', () => fileInput.click());

    dropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropzone.classList.add('dragover');
    });

    dropzone.addEventListener('dragleave', () => {
        dropzone.classList.remove('dragover');
    });

    dropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropzone.classList.remove('dragover');
        
        if (e.dataTransfer.files.length > 0) {
            handleFileSelect(e.dataTransfer.files[0]);
        }
    });

    fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleFileSelect(e.target.files[0]);
        }
    });

    function handleFileSelect(file) {
        if (!file.type.startsWith('video/') && !file.type.startsWith('image/')) {
            alert('Por favor selecciona un archivo de video o imagen (MP4, MKV, WebM, JPG, PNG).');
            return;
        }
        
        // Validación de tamaño límite (API limit is 2GB)
        const MAX_SIZE = 2 * 1024 * 1024 * 1024; // 2 GB en bytes
        if (file.size > MAX_SIZE) {
            const sizeGB = (file.size / (1024 * 1024 * 1024)).toFixed(2);
            alert(`❌ Tu video pesa ${sizeGB} GB.\nEl límite máximo de la API de Google es de 2.0 GB.\n\nPor favor, usa un video más corto o recórtalo antes de subirlo para que el Coach no exceda el límite de memoria.`);
            return;
        }

        selectedFile = file;
        dropzone.classList.add('has-file');
        dropzone.querySelector('h2').textContent = file.name;
        dropzone.querySelector('p').textContent = `${(file.size / (1024 * 1024)).toFixed(2)} MB - ¡Listo para la grieta!`;
        analyzeBtn.disabled = false;
    }

    // --- API and Loading Logic --- //
    analyzeBtn.addEventListener('click', () => {
        if (!selectedFile) return;

        hideError();
        uploadSection.classList.add('hidden');
        loadingSection.classList.remove('hidden');

        const formData = new FormData();
        formData.append('video', selectedFile);
        
        const apiKeyInput = document.getElementById('custom-api-key').value;
        if (apiKeyInput) {
            formData.append('api_key', apiKeyInput);
        }

        const progressFill = document.getElementById('progress-bar-fill');
        const progressDetail = document.getElementById('progress-detail');
        const loadingText = document.getElementById('loading-text');

        progressFill.style.width = '0%';
        loadingText.textContent = 'Tranfiriendo archivo al servidor...';
        progressDetail.textContent = 'Subiendo: 0%';
        
        const etaBadge = document.getElementById('eta-badge');
        const etaText = document.getElementById('eta-text');
        etaBadge.classList.remove('hidden');
        etaText.textContent = 'Calculando...';

        let uploadStartTime = Date.now();
        let currentEtaSeconds = 0;

        function updateETA(secondsRemaining) {
            if (!isFinite(secondsRemaining) || secondsRemaining < 0) return;
            currentEtaSeconds = Math.max(0, Math.floor(secondsRemaining));
            renderEta();
        }

        function renderEta() {
            if (currentEtaSeconds <= 0) {
                etaText.textContent = "Casi listo...";
                return;
            }
            const mins = Math.floor(currentEtaSeconds / 60);
            const secs = Math.floor(currentEtaSeconds % 60);
            etaText.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
        }

        // Timer visual para que el ETA descuente visualmente cada segundo
        const etaCountdownInterval = setInterval(() => {
            if (currentEtaSeconds > 0) {
                currentEtaSeconds--;
                renderEta();
            }
        }, 1000);

        // Subida Real mediante XMLHttpRequest
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/api/detect-champions', true);

        xhr.upload.onprogress = function(e) {
            if (e.lengthComputable) {
                const percentComplete = (e.loaded / e.total) * 100;
                // El frontend ocupa el primer 30% de la barra visual total
                progressFill.style.width = `${percentComplete * 0.3}%`;
                progressDetail.textContent = `Subiendo: ${Math.round(percentComplete)}%`;
                
                // Mates de ETA para subida
                const timeElapsed = (Date.now() - uploadStartTime) / 1000;
                if (timeElapsed > 1 && e.loaded > 0) {
                    const uploadSpeed = e.loaded / timeElapsed; // bytes/sec
                    const bytesRemaining = e.total - e.loaded;
                    const secondsToUpload = bytesRemaining / uploadSpeed;
                    
                    // Asumimos ~100s para el análisis pesado en los nodos de Google como base estática
                    const totalRemaining = secondsToUpload + 100;
                    updateETA(totalRemaining);
                }
            }
        };

        xhr.onload = function() {
            if (xhr.status === 200) {
                const data = JSON.parse(xhr.responseText);
                const taskId = data.task_id;
                // Al subir con éxito, iniciar el Polling real del backend
                pollProgress(taskId);
            } else {
                clearInterval(etaCountdownInterval);
                let errorMsg = 'Error en el servidor al subir';
                try { errorMsg = JSON.parse(xhr.responseText).detail; } catch(e){}
                showError(`Error: ${errorMsg}`);
                loadingSection.classList.add('hidden');
                uploadSection.classList.remove('hidden');
            }
        };

        xhr.onerror = function() {
            clearInterval(etaCountdownInterval);
            showError('Error de red al intentar conectarse con el servidor.');
            loadingSection.classList.add('hidden');
            uploadSection.classList.remove('hidden');
        };

        xhr.send(formData);

        function pollProgress(taskId) {
            let pollStartTime = Date.now();
            let lastProgress = 30; // Arranca en 30% después de subir
            let pollingErrorCount = 0;

            const intervalId = setInterval(async () => {
                try {
                    const res = await fetch(`/api/progress/${taskId}`);
                    if (!res.ok) throw new Error("HTTP Status " + res.status);
                    const data = await res.json();
                    
                    pollingErrorCount = 0; // reset on success

                    if (data.error) {
                        clearInterval(intervalId);
                        clearInterval(etaCountdownInterval);
                        showError(`El Coach de IA detectó un error:\n\n${data.error}`);
                        loadingSection.classList.add('hidden');
                        uploadSection.classList.remove('hidden');
                        return;
                    }
                    
                    // Lógica de cálculo de ETA para backend
                    if (data.progress > lastProgress) {
                        const timeElapsed = (Date.now() - pollStartTime) / 1000;
                        const progressGained = data.progress - 30;
                        if (progressGained > 0) {
                            const velocity = progressGained / timeElapsed; // pct / segundo
                            const progressRemaining = 100 - data.progress;
                            const secondsRemaining = progressRemaining / velocity;
                            updateETA(secondsRemaining);
                        }
                        lastProgress = data.progress;
                    }

                    // Actualizar UI con el backend en tiempo real
                    progressFill.style.width = `${data.progress}%`;
                    progressDetail.textContent = data.status;
                    loadingText.textContent = 'El IA Coach está analizando el VOD...';

                    if (data.state === "REQUIRES_CONFIRMATION") {
                        clearInterval(intervalId);
                        clearInterval(etaCountdownInterval);
                        
                        currentFileId = data.result.file_id;
                        currentTaskId = taskId;
                        renderChampionsUI(data.result.champions, data.result.pov_side);
                        
                        loadingSection.classList.add('hidden');
                        document.getElementById('champions-section').classList.remove('hidden');
                    } else if (data.state === "DONE") {
                        clearInterval(intervalId);
                        clearInterval(etaCountdownInterval);
                        progressFill.style.width = '100%';
                        progressDetail.textContent = "¡Análisis Completado!";
                        
                        // Mostramos 1 seg la barra llena y renderizamos
                        setTimeout(() => {
                            try {
                                const etaBadge = document.getElementById('eta-badge');
                                if(etaBadge) etaBadge.classList.add('hidden');
                                
                                renderResults(data.result, data.champ_data);
                                loadingSection.classList.add('hidden');
                                document.getElementById('results-section').classList.remove('hidden');
                            } catch(err) {
                                console.error(err);
                                showError("Ocurrió un error inesperado al renderizar el reporte: " + err.message);
                                loadingSection.classList.add('hidden');
                                uploadSection.classList.remove('hidden');
                            }
                        }, 500);
                    }
                } catch (e) {
                    console.error("Error consultando el progreso: ", e);
                }
            }, 1000); // Poll cada segundo
        }

        function renderChampionsUI(champions, pov_side) {
            const allyList = document.getElementById('ally-list');
            const enemyList = document.getElementById('enemy-list');
            allyList.innerHTML = '';
            enemyList.innerHTML = '';
            
            // Invertir lados si somos Red Side
            const grid = document.querySelector('.champions-grid');
            if (pov_side && pov_side.toLowerCase() === 'red') {
                grid.style.flexDirection = 'row-reverse';
            } else {
                grid.style.flexDirection = 'row';
            }

            // Clasificar según prioridad de rol estándar de LoL
            champions.forEach(c => {
               const r = (c.role || "").toLowerCase();
               if(r.includes('top')) c._order = 1;
               else if(r.includes('jung') || r.includes('jg')) c._order = 2;
               else if(r.includes('mid')) c._order = 3;
               else if(r.includes('adc') || r.includes('bot') || r.includes('tira')) c._order = 4;
               else if(r.includes('sup')) c._order = 5;
               else c._order = 99;
            });
            champions.sort((a, b) => a._order - b._order);

            champions.forEach((champ, index) => {
                const cleanName = getChampImageName(champ.name);
                const isAlly = (champ.team || "").toLowerCase() === 'aliado';
                
                const card = document.createElement('div');
                card.className = 'champ-card';
                card.innerHTML = `
                    <img class="champ-img" src="https://ddragon.leagueoflegends.com/cdn/14.4.1/img/champion/${cleanName}.png" alt="${champ.name}" onerror="this.src='https://ddragon.leagueoflegends.com/cdn/14.4.1/img/profileicon/29.png'">
                    <div class="champ-info">
                        <input type="text" class="champ-name-input" value="${champ.name}" data-index="${index}" placeholder="Ej: Ahri">
                        <span class="champ-role">${champ.role}</span>
                    </div>
                    <label class="pov-selector" style="cursor: pointer; margin-right: 10px;">
                        <input type="radio" name="pov-radio" value="${index}" ${champ.is_pov ? 'checked' : ''}>
                        POV
                    </label>
                    <button class="swap-team-btn" style="background: none; border: 1px solid var(--gold); color: var(--gold); border-radius: 4px; padding: 2px 6px; cursor: pointer; font-size: 0.8rem;" title="Mover al equipo contrario">⮂ Mover</button>
                `;
                
                const input = card.querySelector('.champ-name-input');
                input.addEventListener('change', (e) => { 
                    champ.name = e.target.value;
                    const img = card.querySelector('.champ-img');
                    img.src = `https://ddragon.leagueoflegends.com/cdn/14.4.1/img/champion/${getChampImageName(champ.name)}.png`;
                });

                const radio = card.querySelector('input[type="radio"]');
                radio.addEventListener('change', (e) => {
                    champions.forEach(c => c.is_pov = false);
                    champ.is_pov = true;
                });

                const swapBtn = card.querySelector('.swap-team-btn');
                swapBtn.addEventListener('click', () => {
                    const targetTeam = isAlly ? 'Enemigo' : 'Aliado';
                    // Buscar si hay un campeón en el equipo contrario que tenga nuestro mismo rol
                    const counterpart = champions.find(c => c.team.toLowerCase() === targetTeam.toLowerCase() && c.role === champ.role);
                    
                    champ.team = targetTeam;
                    if (counterpart) {
                        counterpart.team = isAlly ? 'Aliado' : 'Enemigo';
                    }
                    renderChampionsUI(champions, pov_side); // Refresca toda la lista al instante
                });

                if (isAlly) allyList.appendChild(card);
                else enemyList.appendChild(card);
            });

            const confirmBtn = document.getElementById('confirm-champs-btn');
            const clone = confirmBtn.cloneNode(true);
            confirmBtn.parentNode.replaceChild(clone, confirmBtn);

            clone.addEventListener('click', async () => {
                document.getElementById('champions-section').classList.add('hidden');
                loadingSection.classList.remove('hidden');
                
                progressFill.style.width = '50%';
                progressDetail.textContent = 'Validando campeones y resumiendo estrategia...';
                loadingText.textContent = 'El Coach Challenger está redactando la crítica profunda...';
                
                // Reiniciar ETA estimate a unos ~30s
                updateETA(30);
                const etaBadge = document.getElementById('eta-badge');
                if(etaBadge) etaBadge.classList.remove('hidden');
                
                const apiKeyInput = document.getElementById('custom-api-key').value;
                
                const payload = {
                    task_id: currentTaskId,
                    file_id: currentFileId,
                    api_key: apiKeyInput || null,
                    champions: champions
                };

                try {
                    const res = await fetch('/api/generate-report', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(payload)
                    });
                    if (res.ok) {
                        pollProgress(currentTaskId); // Reanudar polling
                    } else {
                        showError("Error al iniciar el análisis profundo.");
                        loadingSection.classList.add('hidden');
                        uploadSection.classList.remove('hidden');
                    }
                } catch(e) {
                    showError("Error enviando campeones: " + e.message);
                    loadingSection.classList.add('hidden');
                    uploadSection.classList.remove('hidden');
                }
            });
        }
    });

    // --- Render Logic --- //
    function getChampImageName(rawName) {
        let name = (rawName || "").toLowerCase().replace(/[^a-z0-9]/g, '');
        const exceptions = {
            'wukong': 'MonkeyKing', 'monkeyking': 'MonkeyKing',
            'renataglasc': 'Renata', 'renata': 'Renata',
            'nunuwillump': 'Nunu', 'nunu': 'Nunu',
            'drmundo': 'DrMundo', 'mundo': 'DrMundo',
            'missfortune': 'MissFortune', 'mf': 'MissFortune',
            'masteryi': 'MasterYi', 'yi': 'MasterYi',
            'tahmkench': 'TahmKench', 'tahm': 'TahmKench',
            'xinzhao': 'XinZhao', 'xin': 'XinZhao',
            'aurelionsol': 'AurelionSol', 'asol': 'AurelionSol',
            'leesin': 'LeeSin', 'lee': 'LeeSin',
            'twistedfate': 'TwistedFate', 'tf': 'TwistedFate',
            'jarvaniv': 'JarvanIV', 'j4': 'JarvanIV', 'jarvan': 'JarvanIV',
            'kaisa': 'Kaisa',
            'velkoz': 'Velkoz',
            'chogath': 'Chogath',
            'khazix': 'Khazix',
            'reksai': 'RekSai',
            'kogmaw': 'KogMaw',
            'belveth': 'Belveth',
            'leblanc': 'Leblanc', 'lb': 'Leblanc',
            'ksante': 'KSante'
        };
        if (exceptions[name]) return exceptions[name];
        if (name.length > 0) return name.charAt(0).toUpperCase() + name.slice(1);
        return 'Unknown';
    }

    function setScore(id, scoreData, color) {
        const circle = document.getElementById(id);
        const valueSpan = circle.querySelector('.score-value');
        const reasonSpan = document.getElementById(`${id.split('-')[0]}-reason`);
        
        const score = scoreData?.score || 0;
        const percentage = (score / 10) * 100;
        
        valueSpan.textContent = `${score}/10`;
        reasonSpan.textContent = scoreData?.reason || 'Sin datos evaluables.';
        
        // Timeout to trigger CSS transition smoothly
        setTimeout(() => {
            circle.style.background = `conic-gradient(${color} ${percentage}%, rgba(255,255,255,0.05) 0%)`;
        }, 300);
    }

    function populateList(listId, items) {
        const ul = document.getElementById(listId);
        ul.innerHTML = '';
        if (items && items.length > 0) {
            items.forEach(item => {
                const li = document.createElement('li');
                
                // Aseguramos que sea string y parseamos los timestamps
                let htmlContent = String(item || "");
                if (currentTaskId) {
                    htmlContent = htmlContent.replace(/\[(\d{1,2}:\d{2}(?::\d{2})?)\]/g, (match, timeStr) => {
                        const safeTimeStr = timeStr ? timeStr.replace(/:/g, '_') : 'err';
                        const frameUrl = `/static/frames/${currentTaskId}_${safeTimeStr}.jpg`;
                        return `<span class="timestamp-hover" data-frame="${frameUrl}" style="color: var(--hextech-blue); font-weight: bold; cursor: help; border-bottom: 1px dashed var(--hextech-blue); padding-bottom: 1px;" onmouseenter="showFrame(event, this)" onmouseleave="hideFrame()">${match}</span>`;
                    });
                }
                
                li.innerHTML = htmlContent;
                ul.appendChild(li);
            });
        } else {
            ul.innerHTML = '<li>Sin observaciones.</li>';
        }
    }

    function renderResults(data, champData = []) {
        // Encontrar POV
        const povChamp = champData.find(c => c.is_pov) || { name: 'Desconocido', role: 'Rol' };
        
        // Cargar UI del POV
        const povImg = document.getElementById('pov-champ-img');
        const povRole = document.getElementById('pov-champ-role');
        const povName = document.getElementById('pov-champ-name');
        
        if (povImg) {
            const cleanName = getChampImageName(povChamp.name);
            povImg.src = `https://ddragon.leagueoflegends.com/cdn/14.4.1/img/champion/${cleanName}.png`;
            povImg.alt = povChamp.name;
        }
        if (povRole) povRole.textContent = (povChamp.role || 'Rol').toUpperCase();
        if (povName) povName.textContent = povChamp.name || 'Desconocido';

        // Asignar el perfil deducido
        document.getElementById('profile-tag').textContent = data.player_profile_tag || "Evaluación Básica";
        document.getElementById('profile-reason').textContent = data.player_profile_reason || "No se ha determinado un perfil psicológico particular.";

        setScore('mech-score', data.mechanics_score, '#0ac8b9');
        setScore('map-score', data.map_awareness_score, '#0ac8b9');
        setScore('pos-score', data.positioning_score, '#0ac8b9');

        populateList('good-list', data.good_things);
        populateList('bad-list', data.mistakes);
        populateList('improve-list', data.advice);
        
        // Asignar Plan de Juego
        document.getElementById('game-plan-text').textContent = data.game_plan || "La IA no dedujo un plan de juego claro para la composición de la partida.";

        // Renderizar el Gráfico si hay datos
        const chartContainer = document.querySelector('.chart-container');
        if (data.momentum_graph && data.momentum_graph.length > 0) {
            chartContainer.style.display = 'flex';
            renderChart(data.momentum_graph);
        } else {
            chartContainer.style.display = 'none';
        }
    }

    let momentumChartInstance = null;

    function renderChart(graphData) {
        const ctx = document.getElementById('momentumChart').getContext('2d');
        
        if (momentumChartInstance) {
            momentumChartInstance.destroy();
        }

        // Ordenamos cronológicamente en caso de que la IA tire datos desordenados
        graphData.sort((a, b) => a.time_minute - b.time_minute);
        
        const labels = graphData.map(d => `Min ${d.time_minute}'`);
        const dataPoints = graphData.map(d => d.momentum_score);
        const dataReasons = graphData.map(d => d.reason || "Sin detalles específicos.");

        momentumChartInstance = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Ventaja (Momentum) [1-10]',
                    data: dataPoints,
                    borderColor: '#0ac8b9',
                    backgroundColor: 'rgba(10, 200, 185, 0.15)',
                    borderWidth: 3,
                    tension: 0.4, // Curvas aerodinámicas Hextech suaves
                    fill: 'origin',
                    pointBackgroundColor: '#c89b3c',
                    pointBorderColor: '#fff',
                    pointBorderWidth: 2,
                    pointRadius: 6,
                    pointHoverRadius: 9
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                scales: {
                    y: {
                        min: 0,
                        max: 10,
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#a09b8c', stepSize: 2 }
                    },
                    x: {
                        grid: { color: 'rgba(255, 255, 255, 0.05)' },
                        ticks: { color: '#a09b8c' }
                    }
                },
                plugins: {
                    legend: { labels: { color: '#f0e6d2', font: { family: "'Inter', sans-serif" } } },
                    tooltip: {
                        titleFont: { family: "'Inter', sans-serif", size: 14 },
                        bodyFont: { family: "'Inter', sans-serif", size: 13 },
                        callbacks: {
                            label: function(context) {
                                const score = context.raw;
                                const index = context.dataIndex;
                                const reason = dataReasons[index];
                                // Devolver Array crea mutilples lineas en el tooltip.
                                return [
                                    `Puntuación: ${score}/10`,
                                    `Motivo: ${reason}`
                                ];
                            }
                        }
                    }
                }
            }
        });
    }

    // --- Reset --- //
    resetBtn.addEventListener('click', () => {
        hideError();
        resultsSection.classList.add('hidden');
        uploadSection.classList.remove('hidden');
        selectedFile = null;
        fileInput.value = '';
        dropzone.classList.remove('has-file');
        dropzone.querySelector('h2').textContent = 'Arrastra tu video o imagen aquí';
        dropzone.querySelector('p').textContent = 'O haz clic para seleccionar (MP4, MKV, JPG, PNG...)';
        analyzeBtn.disabled = true;
        
        // Reset scores visual
        document.querySelectorAll('.progress-circle').forEach(c => {
            c.style.background = `conic-gradient(var(--hextech-blue) 0%, rgba(255,255,255,0.05) 0%)`;
            c.querySelector('.score-value').textContent = '0/10';
        });

        const chatMessages = document.getElementById('chat-messages');
        if(chatMessages) {
            chatMessages.innerHTML = `
            <div style="align-self: flex-start; background: rgba(10, 200, 185, 0.1); border-left: 2px solid var(--hextech-blue); padding: 0.8rem 1rem; border-radius: 4px; color: var(--text-main); font-size: 0.95rem; line-height: 1.5;">
                <strong>Challenger Coach:</strong> ¡Hola! Revisé el material. Si no te queda claro por qué deberías comprar un ítem o por qué dije que posicionaste mal, preguntame.
            </div>`;
        }
    });

    // --- Chat Logic --- //
    const chatInput = document.getElementById('chat-input');
    const chatSendBtn = document.getElementById('chat-send-btn');
    const chatMessages = document.getElementById('chat-messages');

    if (chatSendBtn) {
        chatSendBtn.addEventListener('click', async () => {
            const message = chatInput.value.trim();
            if (!message || !currentTaskId) return;

            // Mostrar el mensaje del usuario
            const userDiv = document.createElement('div');
            userDiv.style.cssText = 'align-self: flex-end; background: rgba(200, 155, 60, 0.1); border-right: 2px solid var(--gold); padding: 0.8rem 1rem; border-radius: 4px; color: var(--text-main); font-size: 0.95rem; line-height: 1.5; max-width: 85%; margin-left: auto;';
            userDiv.innerHTML = `<strong>Tú:</strong> ${message}`;
            chatMessages.appendChild(userDiv);
            
            chatInput.value = '';
            chatInput.disabled = true;
            chatSendBtn.disabled = true;

            const loadingDiv = document.createElement('div');
            loadingDiv.style.cssText = 'align-self: flex-start; padding: 0.8rem 1rem; color: var(--text-muted); font-size: 0.9rem; font-style: italic;';
            loadingDiv.textContent = 'Coach escribiendo...';
            chatMessages.appendChild(loadingDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;

            try {
                const apiKeyInput = document.getElementById('custom-api-key').value;
                const res = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ task_id: currentTaskId, message: message, api_key: apiKeyInput || null })
                });

                chatMessages.removeChild(loadingDiv);
                
                if (res.ok) {
                    const data = await res.json();
                    const coachDiv = document.createElement('div');
                    coachDiv.style.cssText = 'align-self: flex-start; background: rgba(10, 200, 185, 0.1); border-left: 2px solid var(--hextech-blue); padding: 0.8rem 1rem; border-radius: 4px; color: var(--text-main); font-size: 0.95rem; line-height: 1.5; max-width: 85%;';
                    // Convert markdown generic bold format
                    let formattedText = data.reply.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
                    formattedText = formattedText.replace(/\n/g, '<br>');
                    coachDiv.innerHTML = `<strong>Challenger Coach:</strong><br>${formattedText}`;
                    chatMessages.appendChild(coachDiv);
                } else {
                    const errorData = await res.json();
                    alert('No se pudo enviar el mensaje: ' + errorData.detail);
                }
            } catch (e) {
                if(chatMessages.contains(loadingDiv)) chatMessages.removeChild(loadingDiv);
                alert('Error de conexión con el Coach.');
            }

            chatInput.disabled = false;
            chatSendBtn.disabled = false;
            chatInput.focus();
            chatMessages.scrollTop = chatMessages.scrollHeight;
        });

        chatInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') chatSendBtn.click();
        });
    }
});

// Funciones globales para el Tooltip flotante 
window.showFrame = function(e, element) {
    const tooltip = document.getElementById('hover-tooltip');
    const hoverImg = document.getElementById('hover-image');
    
    // Comprobamos la imagen antes de mostrar el bloque (evita cuadros vacíos rotos si hay error de cv2)
    const frameSrc = element.getAttribute('data-frame');
    hoverImg.src = frameSrc;
    hoverImg.onerror = function() {
        hoverImg.src = '';
        tooltip.style.display = 'none'; // Si no existía la imagen localmente, la escondemos
    };
    hoverImg.onload = function() {
        tooltip.style.display = 'block';
    };
    
    const rect = element.getBoundingClientRect();
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    
    // Posicionar debajo del span interactivo
    tooltip.style.top = (rect.bottom + scrollTop + 10) + 'px';
    tooltip.style.left = Math.max(0, rect.left - 100) + 'px'; // Prevenir que se salga de la pantalla izq
};

window.hideFrame = function() {
    const tooltip = document.getElementById('hover-tooltip');
    tooltip.style.display = 'none';
};
