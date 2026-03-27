document.addEventListener('DOMContentLoaded', () => {
    const dropzone = document.getElementById('dropzone');
    const fileInput = document.getElementById('file-input');
    const analyzeBtn = document.getElementById('analyze-btn');
    const resetBtn = document.getElementById('reset-btn');
    
    const uploadSection = document.getElementById('upload-section');
    const loadingSection = document.getElementById('loading-section');
    const resultsSection = document.getElementById('results-section');
    const loadingText = document.getElementById('loading-text');

    let selectedFile = null;

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
        if (!file.type.startsWith('video/')) {
            alert('Por favor selecciona un archivo de video (MP4, MKV, WebM).');
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
        xhr.open('POST', '/api/analyze', true);

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
                alert(`Error: ${errorMsg}`);
                loadingSection.classList.add('hidden');
                uploadSection.classList.remove('hidden');
            }
        };

        xhr.onerror = function() {
            clearInterval(etaCountdownInterval);
            alert('Error de red al intentar conectarse con el servidor.');
            loadingSection.classList.add('hidden');
            uploadSection.classList.remove('hidden');
        };

        xhr.send(formData);

        function pollProgress(taskId) {
            let pollStartTime = Date.now();
            let lastProgress = 30; // Arranca en 30% después de subir

            const intervalId = setInterval(async () => {
                try {
                    const res = await fetch(`/api/progress/${taskId}`);
                    const data = await res.json();

                    if (data.error) {
                        clearInterval(intervalId);
                        clearInterval(etaCountdownInterval);
                        alert(`El Coach de IA detectó un error:\n\n${data.error}`);
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

                    if (data.done) {
                        clearInterval(intervalId);
                        clearInterval(etaCountdownInterval);
                        progressFill.style.width = '100%';
                        progressDetail.textContent = "¡Análisis Completado!";
                        etaBadge.classList.add('hidden');
                        
                        // Mostramos 1 seg la barra llena y renderizamos
                        setTimeout(() => {
                            renderResults(data.result);
                            loadingSection.classList.add('hidden');
                            resultsSection.classList.remove('hidden');
                        }, 500);
                    }
                } catch (e) {
                    console.error("Error consultando el progreso: ", e);
                }
            }, 1000); // Poll cada segundo
        }
    });

    // --- Render Logic --- //
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
                li.innerHTML = item; // Using innerHTML if the model naturally returns bold asterisks
                ul.appendChild(li);
            });
        } else {
            ul.innerHTML = '<li>Sin observaciones.</li>';
        }
    }

    function renderResults(data) {
        setScore('mech-score', data.mechanics_score, '#0ac8b9');
        setScore('map-score', data.map_awareness_score, '#0ac8b9');
        setScore('pos-score', data.positioning_score, '#0ac8b9');

        populateList('good-list', data.good_things);
        populateList('bad-list', data.mistakes);
        populateList('improve-list', data.advice);
        
        // Asignar Plan de Juego
        document.getElementById('game-plan-text').textContent = data.game_plan || "La IA no dedujo un plan de juego claro para la composición de la partida.";

        // Renderizar el Gráfico si hay datos
        if (data.momentum_graph && data.momentum_graph.length > 0) {
            renderChart(data.momentum_graph);
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
        resultsSection.classList.add('hidden');
        uploadSection.classList.remove('hidden');
        selectedFile = null;
        fileInput.value = '';
        dropzone.classList.remove('has-file');
        dropzone.querySelector('h2').textContent = 'Arrastra tu video aquí';
        dropzone.querySelector('p').textContent = 'O haz clic para seleccionar (MP4, MKV, WebM)';
        analyzeBtn.disabled = true;
        
        // Reset scores visual
        document.querySelectorAll('.progress-circle').forEach(c => {
            c.style.background = `conic-gradient(var(--hextech-blue) 0%, rgba(255,255,255,0.05) 0%)`;
            c.querySelector('.score-value').textContent = '0/10';
        });
    });
});
