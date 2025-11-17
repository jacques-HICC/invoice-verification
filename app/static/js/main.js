// app/static/js/main.js

let currentInvoice = null;
let currentPage = 0;
let totalPages = 1;

// Zoom and pan variables
let scale = 1;
let panning = false;
let pointX = 0;
let pointY = 0;
let start = { x: 0, y: 0 };
let currentImg = null;

// Console resize variables
let consoleResizing = false;
let consoleHeight = 250;

function setupConsoleResize() {
    const handle = document.querySelector('.resize-handle');
    const output = document.getElementById('sync-output');
    const main = document.getElementById('main-content');

    handle.addEventListener('mousedown', (e) => {
        e.stopPropagation();
        consoleResizing = true;
        document.body.style.userSelect = 'none';
    });

    document.addEventListener('mousemove', (e) => {
        if (!consoleResizing) return;
        
        const newHeight = window.innerHeight - e.clientY;
        if (newHeight >= 50 && newHeight <= 600) {
            consoleHeight = newHeight;
            output.style.height = `${consoleHeight}px`;
            main.style.marginBottom = `${consoleHeight + 40}px`;
        }
    });

    document.addEventListener('mouseup', () => {
        if (consoleResizing) {
            consoleResizing = false;
            document.body.style.userSelect = '';
        }
    });
}

function toggleConsole() {
    const output = document.getElementById('sync-output');
    const toggle = document.getElementById('console-toggle');
    const main = document.getElementById('main-content');
    
    if (output.classList.contains('expanded')) {
        output.classList.remove('expanded');
        output.style.height = '0';
        main.classList.remove('console-expanded');
        main.style.marginBottom = '40px';
        toggle.textContent = '▲';
    } else {
        output.classList.add('expanded');
        output.style.height = `${consoleHeight}px`;
        main.style.marginBottom = `${consoleHeight + 40}px`;
        toggle.textContent = '▼';
    }
}

async function fetchStats() {
    const res = await fetch('/sharepoint_stats');
    const data = await res.json();
    
    const total = data.total || 0;
    const aiProcessed = data.ai_processed || 0;
    const verified = data.human_validated || 0;
    const unprocessed = total - aiProcessed;
    
    document.getElementById('total-invoices').textContent = total;
    document.getElementById('ai-processed').textContent = aiProcessed;
    document.getElementById('verified').textContent = verified;
    document.getElementById('unprocessed-count').textContent = unprocessed;
    
    const slider = document.getElementById('process-count-slider');
    const input = document.getElementById('process-count-input');
    slider.max = unprocessed;
    input.max = unprocessed;
    
    const processBtn = document.getElementById('process-btn');
    processBtn.disabled = unprocessed === 0;
    if (unprocessed === 0) {
        processBtn.textContent = '✓ All Processed';
    } else {
        processBtn.textContent = '🤖 Process with AI';
    }
}

async function loadAvailableModels() {
    try {
        const response = await fetch('/api/models');
        const models = await response.json();
        
        const select = document.getElementById('model-select');
        select.innerHTML = '';
        
        if (models.length === 0) {
            select.innerHTML = '<option value="">No models found</option>';
            return;
        }
        
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.filename;
            option.textContent = `${model.display_name} (${model.size_mb} MB)`;
            if (model.is_default) {
                option.selected = true;
            }
            select.appendChild(option);
        });
    } catch (err) {
        console.error('Failed to load models:', err);
        document.getElementById('model-select').innerHTML = '<option value="">Error loading models</option>';
    }
}

function setupPanZoom() {
    const display = document.getElementById('invoice-display');

    // Mouse wheel zoom
    display.addEventListener('wheel', (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.1 : 0.1;
        const newScale = Math.max(0.5, Math.min(5, scale + delta));
        
        if (currentImg) {
            const rect = display.getBoundingClientRect();
            const offsetX = e.clientX - rect.left;
            const offsetY = e.clientY - rect.top;
            
            zoom(newScale, offsetX, offsetY);
        }
    });

    // Pan with mouse drag
    display.addEventListener('mousedown', (e) => {
        e.preventDefault();
        start = { x: e.clientX - pointX, y: e.clientY - pointY };
        panning = true;
    });

    display.addEventListener('mousemove', (e) => {
        if (!panning) return;
        e.preventDefault();
        pointX = e.clientX - start.x;
        pointY = e.clientY - start.y;
        updateTransform();
    });

    display.addEventListener('mouseup', () => {
        panning = false;
    });

    display.addEventListener('mouseleave', () => {
        panning = false;
    });

    // Touch support
    let lastDistance = 0;
    display.addEventListener('touchstart', (e) => {
        if (e.touches.length === 2) {
            lastDistance = getDistance(e.touches[0], e.touches[1]);
        } else if (e.touches.length === 1) {
            start = { 
                x: e.touches[0].clientX - pointX, 
                y: e.touches[0].clientY - pointY 
            };
            panning = true;
        }
    });

    display.addEventListener('touchmove', (e) => {
        e.preventDefault();
        if (e.touches.length === 2) {
            const distance = getDistance(e.touches[0], e.touches[1]);
            const delta = (distance - lastDistance) * 0.01;
            const newScale = Math.max(0.5, Math.min(5, scale + delta));
            zoom(newScale, display.offsetWidth / 2, display.offsetHeight / 2);
            lastDistance = distance;
        } else if (e.touches.length === 1 && panning) {
            pointX = e.touches[0].clientX - start.x;
            pointY = e.touches[0].clientY - start.y;
            updateTransform();
        }
    });

    display.addEventListener('touchend', () => {
        panning = false;
    });
}

function getDistance(touch1, touch2) {
    const dx = touch1.clientX - touch2.clientX;
    const dy = touch1.clientY - touch2.clientY;
    return Math.sqrt(dx * dx + dy * dy);
}

function zoom(newScale, offsetX, offsetY) {
    if (!currentImg) return;
    
    const oldScale = scale;
    scale = newScale;

    // Adjust pan to zoom towards cursor position
    pointX = offsetX - (offsetX - pointX) * (scale / oldScale);
    pointY = offsetY - (offsetY - pointY) * (scale / oldScale);

    updateTransform();
    updateZoomDisplay();
}

function updateTransform() {
    if (currentImg) {
        currentImg.style.transform = `translate(${pointX}px, ${pointY}px) scale(${scale})`;
    }
}

function updateZoomDisplay() {
    document.getElementById('zoom-level').textContent = Math.round(scale * 100) + '%';
}

function zoomIn() {
    const display = document.getElementById('invoice-display');
    const newScale = Math.min(5, scale + 0.2);
    zoom(newScale, display.offsetWidth / 2, display.offsetHeight / 2);
}

function zoomOut() {
    const display = document.getElementById('invoice-display');
    const newScale = Math.max(0.5, scale - 0.2);
    zoom(newScale, display.offsetWidth / 2, display.offsetHeight / 2);
}

function resetZoom() {
    scale = 1;
    pointX = 0;
    pointY = 0;
    updateTransform();
    updateZoomDisplay();
}

function fitToWidth() {
    if (!currentImg) return;
    const display = document.getElementById('invoice-display');
    const containerWidth = display.offsetWidth - 20;
    const imageWidth = currentImg.naturalWidth;
    scale = containerWidth / imageWidth;
    pointX = 10;
    pointY = 10;
    updateTransform();
    updateZoomDisplay();
}

async function loadInvoicePage(nodeId, page) {
    try {
        const img = document.createElement('img');
        img.src = `/api/invoice_image/${nodeId}/${page}`;
        img.alt = `Invoice page ${page + 1}`;
        
        img.onload = () => {
            currentImg = img;
            resetZoom();
        };
        
        document.getElementById('invoice-display').innerHTML = '';
        document.getElementById('invoice-display').appendChild(img);
        
        currentPage = page;
        updatePageNavigation();
        
    } catch (err) {
        console.error('Error loading page:', err);
    }
}

async function loadNextInvoice() {
    try {
        const response = await fetch('/api/next_invoice');
        
        if (!response.ok) {
            if (response.status === 404) {
                const aiProcessed = parseInt(document.getElementById('ai-processed').textContent);
                if (aiProcessed === 0) {
                    document.getElementById('invoice-display').innerHTML = 
                        '<div class="no-invoices">📋 No invoices to verify yet.<br><br>Process some invoices with AI first!</div>';
                } else {
                    document.getElementById('invoice-display').innerHTML = 
                        '<div class="no-invoices">🎉 No invoices to validate! All done.</div>';
                }
                document.getElementById('page-navigation').style.display = 'none';
                document.getElementById('gcdocs-btn').style.display = 'none';
                disableForm();
                return;
            }
            throw new Error('Failed to load invoice');
        }
        
        currentInvoice = await response.json();
        currentPage = 0;
        
        // Show GCDocs button
        document.getElementById('gcdocs-btn').style.display = 'flex';
        
        // Get page count
        const pageCountResponse = await fetch(`/api/invoice_page_count/${currentInvoice.node_id}`);
        const pageCountData = await pageCountResponse.json();
        totalPages = pageCountData.page_count || 1;
        
        // ALWAYS show page navigation and update total pages
        const pageNav = document.getElementById('page-navigation');
        pageNav.style.display = 'flex';
        document.getElementById('total-pages').textContent = totalPages;
        document.getElementById('current-page').textContent = '1';
        
        // Load first page
        await loadInvoicePage(currentInvoice.node_id, 0);
        
        // Populate form
        document.getElementById('node-id').value = currentInvoice.node_id;
        document.getElementById('company-name').value = currentInvoice.ai_company_name || '';
        document.getElementById('invoice-number').value = currentInvoice.ai_invoice_number || '';
        document.getElementById('invoice-date').value = currentInvoice.ai_invoice_date || '';
        document.getElementById('total-amount').value = currentInvoice.ai_total_amount || '';
        document.getElementById('notes').value = '';
        
        enableForm();
        
    } catch (err) {
        console.error('Error loading invoice:', err);
        document.getElementById('invoice-display').innerHTML = 
            `<div class="no-invoices">❌ Error loading invoice: ${err.message}</div>`;
    }
}

async function refreshInvoice() {
    const refreshBtn = document.getElementById('refresh-btn');
    const originalText = refreshBtn.textContent;
    refreshBtn.textContent = '🔄 Loading...';
    
    await fetchStats();
    await loadNextInvoice();
    
    refreshBtn.textContent = originalText;
}

function previousPage() {
    if (currentPage > 0 && currentInvoice) {
        loadInvoicePage(currentInvoice.node_id, currentPage - 1);
    }
}

function nextPage() {
    if (currentPage < totalPages - 1 && currentInvoice) {
        loadInvoicePage(currentInvoice.node_id, currentPage + 1);
    }
}

function updatePageNavigation() {
    document.getElementById('current-page').textContent = currentPage + 1;
    document.getElementById('prev-page-btn').disabled = currentPage === 0;
    document.getElementById('next-page-btn').disabled = currentPage >= totalPages - 1;
}

async function saveAndNext() {
    if (!currentInvoice) return;
    
    const data = {
        node_id: document.getElementById('node-id').value,
        company_name: document.getElementById('company-name').value,
        invoice_number: document.getElementById('invoice-number').value,
        invoice_date: document.getElementById('invoice-date').value,
        total_amount: parseFloat(document.getElementById('total-amount').value) || 0,
        notes: document.getElementById('notes').value,
        flagged: false
    };
    
    try {
        document.getElementById('save-next-btn').disabled = true;
        document.getElementById('save-next-btn').textContent = '💾 Saving...';
        
        const response = await fetch('/api/save_validation', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        
        if (!response.ok) throw new Error('Save failed');
        
        document.getElementById('save-next-btn').textContent = '✅ Saved!';
        
        await fetchStats();
        
        setTimeout(() => {
            document.getElementById('save-next-btn').textContent = '💾 Save & Next ➡️';
            document.getElementById('save-next-btn').disabled = false;
            loadNextInvoice();
        }, 800);
        
    } catch (err) {
        console.error('Save error:', err);
        alert('Failed to save: ' + err.message);
        document.getElementById('save-next-btn').disabled = false;
        document.getElementById('save-next-btn').textContent = '💾 Save & Next ➡️';
    }
}

function disableForm() {
    document.getElementById('save-next-btn').disabled = true;
    document.querySelectorAll('#validation-form input, #validation-form textarea').forEach(el => {
        el.disabled = true;
    });
}

function enableForm() {
    document.getElementById('save-next-btn').disabled = false;
    document.querySelectorAll('#validation-form input, #validation-form textarea').forEach(el => {
        el.disabled = false;
    });
}

function openProcessDialog() {
    const unprocessed = parseInt(document.getElementById('unprocessed-count').textContent);
    if (unprocessed === 0) return;
    
    const modal = document.getElementById('process-modal');
    const slider = document.getElementById('process-count-slider');
    const input = document.getElementById('process-count-input');
    
    const initialValue = Math.min(10, unprocessed);
    slider.value = initialValue;
    input.value = initialValue;
    updateProcessCount(initialValue);
    
    modal.classList.add('active');
}

function closeProcessDialog() {
    document.getElementById('process-modal').classList.remove('active');
}

function updateProcessCount(value) {
    const unprocessed = parseInt(document.getElementById('unprocessed-count').textContent);
    const count = Math.min(parseInt(value), unprocessed);
    
    document.getElementById('process-count-display').textContent = count;
    document.getElementById('process-count-slider').value = count;
    document.getElementById('process-count-input').value = count;
}

function setProcessCount(value) {
    const unprocessed = parseInt(document.getElementById('unprocessed-count').textContent);
    const count = value === 'all' ? unprocessed : Math.min(value, unprocessed);
    updateProcessCount(count);
}

async function startProcessing() {
    const count = parseInt(document.getElementById('process-count-input').value);
    const model = document.getElementById('model-select').value;
    closeProcessDialog();
    
    const output = document.getElementById('sync-output');
    if (!output.classList.contains('expanded')) {
        toggleConsole();
    }
    
    output.textContent = `🤖 Starting AI processing for ${count} invoices...\n`;
    
    try {
        const response = await fetch('/process_with_ai', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ count: count, model: model })
        });
        
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value);
            const lines = chunk.split("\n\n");
            
            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    const msg = line.replace("data: ", "").trim();
                    if (msg === "[DONE]") {
                        output.textContent += "\n✅ AI processing complete!\n";
                        fetchStats();
                        loadNextInvoice();
                        return;
                    }
                    output.textContent += msg + "\n";
                    output.scrollTop = output.scrollHeight;
                }
            }
        }
    } catch (err) {
        output.textContent += `\n❌ Error: ${err}\n`;
    }
}

async function startSync() {
    const output = document.getElementById('sync-output');
    
    if (!output.classList.contains('expanded')) {
        toggleConsole();
    }
    
    output.textContent = 'Starting sync...\n';

    const response = await fetch('/sync_to_sharepoint');
    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split("\n\n");
        for (const line of lines) {
            if (line.startsWith("data: ")) {
                const msg = line.replace("data: ", "").trim();
                if (msg === "[DONE]") {
                    output.textContent += "\n✅ Sync complete!\n";
                    fetchStats();
                    return;
                }
                output.textContent += msg + "\n";
                output.scrollTop = output.scrollHeight;
            }
        }
    }
}

function openInGCDocs() {
    if (currentInvoice && currentInvoice.node_id) {
        window.open(`/api/download_pdf/${currentInvoice.node_id}`, '_blank');
    }
}

// Initialize on page load
setupConsoleResize();
setupPanZoom();
fetchStats();
loadAvailableModels();
loadNextInvoice();