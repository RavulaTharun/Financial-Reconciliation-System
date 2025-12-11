let currentRunId = null;
let pollInterval = null;

const startBtn = document.getElementById('startBtn');
const runInfo = document.getElementById('runInfo');
const runIdEl = document.getElementById('runId');
const statusBadge = document.getElementById('statusBadge');
const progressSection = document.getElementById('progressSection');
const progressFill = document.getElementById('progressFill');
const progressPercent = document.getElementById('progressPercent');
const currentStep = document.getElementById('currentStep');
const logsContainer = document.getElementById('logsContainer');
const logCount = document.getElementById('logCount');
const downloadSection = document.getElementById('downloadSection');
const downloadBtn = document.getElementById('downloadBtn');

const agentStepMap = {
    'ingest_bank': 'agent-ingest_bank',
    'ingest_bank_complete': 'agent-ingest_bank',
    'ingest_erp': 'agent-ingest_erp',
    'ingest_erp_complete': 'agent-ingest_erp',
    'dedupe': 'agent-dedupe',
    'dedupe_complete': 'agent-dedupe',
    'matcher': 'agent-matcher',
    'matcher_complete': 'agent-matcher',
    'classifier': 'agent-classifier',
    'classifier_complete': 'agent-classifier',
    'explain': 'agent-explain',
    'explain_complete': 'agent-explain',
    'output': 'agent-output',
    'output_complete': 'agent-output'
};

async function startReconciliation() {
    try {
        startBtn.disabled = true;
        startBtn.textContent = 'Starting...';
        
        const response = await fetch('/api/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        });
        
        if (!response.ok) {
            throw new Error('Failed to start reconciliation');
        }
        
        const data = await response.json();
        currentRunId = data.run_id;
        
        runIdEl.textContent = currentRunId;
        runInfo.classList.remove('hidden');
        progressSection.classList.remove('hidden');
        downloadSection.classList.add('hidden');
        
        updateStatus('running');
        startBtn.textContent = 'Running...';
        
        logsContainer.innerHTML = '<p class="logs-placeholder">Fetching logs...</p>';
        
        resetAgentNodes();
        
        pollInterval = setInterval(pollStatus, 2000);
        pollLogs();
        
    } catch (error) {
        console.error('Error starting reconciliation:', error);
        startBtn.disabled = false;
        startBtn.textContent = 'Start Reconciliation';
        alert('Failed to start reconciliation: ' + error.message);
    }
}

async function pollStatus() {
    if (!currentRunId) return;
    
    try {
        const response = await fetch(`/api/status/${currentRunId}`);
        if (!response.ok) return;
        
        const data = await response.json();
        
        progressFill.style.width = `${data.progress}%`;
        progressPercent.textContent = `${data.progress}%`;
        currentStep.textContent = formatStepName(data.current_step);
        
        updateAgentNodes(data.current_step, data.steps_completed);
        
        if (data.status === 'completed') {
            updateStatus('completed');
            clearInterval(pollInterval);
            startBtn.disabled = false;
            startBtn.textContent = 'Start New Reconciliation';
            
            downloadBtn.href = `/api/download/${currentRunId}`;
            downloadSection.classList.remove('hidden');
            
            pollLogs();
            
        } else if (data.status === 'failed') {
            updateStatus('failed');
            clearInterval(pollInterval);
            startBtn.disabled = false;
            startBtn.textContent = 'Retry Reconciliation';
            
            if (data.errors.length > 0) {
                alert('Reconciliation failed: ' + data.errors.join('\n'));
            }
        }
        
    } catch (error) {
        console.error('Error polling status:', error);
    }
}

async function pollLogs() {
    if (!currentRunId) return;
    
    try {
        const response = await fetch(`/api/logs/${currentRunId}`);
        if (!response.ok) return;
        
        const data = await response.json();
        
        logCount.textContent = `(${data.total_logs})`;
        
        if (data.logs.length === 0) {
            logsContainer.innerHTML = '<p class="logs-placeholder">Waiting for agent logs...</p>';
            return;
        }
        
        logsContainer.innerHTML = data.logs.map(log => `
            <div class="log-entry">
                <div class="log-timestamp">${formatTimestamp(log.timestamp)}</div>
                <div class="log-agent">[${log.agent_name}]</div>
                <div class="log-message">${log.decision || log.input_summary}</div>
            </div>
        `).join('');
        
        logsContainer.scrollTop = logsContainer.scrollHeight;
        
    } catch (error) {
        console.error('Error polling logs:', error);
    }
}

function updateStatus(status) {
    statusBadge.textContent = status.charAt(0).toUpperCase() + status.slice(1);
    statusBadge.className = 'status-badge ' + status;
}

function formatStepName(step) {
    if (!step) return 'Initializing...';
    return step.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
}

function formatTimestamp(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString();
}

function resetAgentNodes() {
    document.querySelectorAll('.agent-node').forEach(node => {
        node.classList.remove('active', 'completed');
    });
}

function updateAgentNodes(currentStep, completedSteps) {
    resetAgentNodes();
    
    const completedAgents = new Set();
    (completedSteps || []).forEach(step => {
        const agentId = agentStepMap[step];
        if (agentId) {
            completedAgents.add(agentId);
        }
    });
    
    completedAgents.forEach(agentId => {
        const node = document.getElementById(agentId);
        if (node) {
            node.classList.add('completed');
        }
    });
    
    if (currentStep) {
        const activeAgentId = agentStepMap[currentStep];
        if (activeAgentId) {
            const activeNode = document.getElementById(activeAgentId);
            if (activeNode && !activeNode.classList.contains('completed')) {
                activeNode.classList.add('active');
            }
        }
    }
}

startBtn.addEventListener('click', startReconciliation);

setInterval(() => {
    if (currentRunId && pollInterval) {
        pollLogs();
    }
}, 3000);
