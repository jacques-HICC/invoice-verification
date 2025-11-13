// Toggle console visibility
function toggleConsole() {
    const output = document.getElementById('sync-output');
    const toggle = document.getElementById('console-toggle');
    const main = document.getElementById('main-content');
    
    output.classList.toggle('expanded');
    main.classList.toggle('console-expanded');
    toggle.textContent = output.classList.contains('expanded') ? '▼' : '▲';
}

// Fetch and display stats
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
    
    // Update modal max value
    const slider = document.getElementById('process-count-slider');
    const input = document.getElementById('process-count-input');
    slider.max = unprocessed;
    input.max = unprocessed;
    
    // Disable process button if nothing to process
    const processBtn = document.getElementById('process-btn');
    processBtn.disabled = unprocessed === 0;
    if (unprocessed === 0) {
        processBtn.textContent = '✓ All Processed';
    } else {
        processBtn.textContent = '🤖 Process with AI';
    }
}

// Load available models from backend
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

// Sync invoices from GCDocs to SharePoint (streaming)
async function startSync() {
    const output = document.getElementById('sync-output');
    
    // Auto-expand console when sync starts
    if (!output.classList.contains('expanded')) {
        toggleConsole();
    }
    
    output.textContent = '🔄 Starting sync...\n';

    const response = await fetch('/sync_to_sharepoint'); // GET request for stream
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

// Open the processing modal
function openProcessDialog() {
    const unprocessed = parseInt(document.getElementById('unprocessed-count').textContent);
    if (unprocessed === 0) return;
    
    const modal = document.getElementById('process-modal');
    const slider = document.getElementById('process-count-slider');
    const input = document.getElementById('process-count-input');
    
    // Set initial value to min(10, unprocessed)
    const initialValue = Math.min(10, unprocessed);
    slider.value = initialValue;
    input.value = initialValue;
    updateProcessCount(initialValue);
    
    modal.classList.add('active');
}

// Close the processing modal
function closeProcessDialog() {
    document.getElementById('process-modal').classList.remove('active');
}

// Update the displayed process count
function updateProcessCount(value) {
    const unprocessed = parseInt(document.getElementById('unprocessed-count').textContent);
    const count = Math.min(parseInt(value), unprocessed);
    
    document.getElementById('process-count-display').textContent = count;
    document.getElementById('process-count-slider').value = count;
    document.getElementById('process-count-input').value = count;
}

// Set process count to a specific value
function setProcessCount(value) {
    const unprocessed = parseInt(document.getElementById('unprocessed-count').textContent);
    const count = value === 'all' ? unprocessed : Math.min(value, unprocessed);
    updateProcessCount(count);
}

// Start AI processing (streaming)
async function startProcessing() {
    const count = parseInt(document.getElementById('process-count-input').value);
    const model = document.getElementById('model-select').value;
    
    if (!model) {
        alert('Please select a model first');
        return;
    }
    
    closeProcessDialog();
    
    // Open console
    const output = document.getElementById('sync-output');
    if (!output.classList.contains('expanded')) {
        toggleConsole();
    }
    
    output.textContent = `🤖 Starting AI processing for ${count} invoices using ${model}...\n`;
    
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

// Placeholder functions for validation (not implemented yet)
function prevInvoice() {
    console.log('Previous invoice - not implemented yet');
}

function nextInvoice() {
    console.log('Next invoice - not implemented yet');
}

function saveAndNext() {
    console.log('Save and next - not implemented yet');
}

function flagForReview() {
    console.log('Flag for review - not implemented yet');
}

// Initialize on page load
fetchStats();
loadAvailableModels();