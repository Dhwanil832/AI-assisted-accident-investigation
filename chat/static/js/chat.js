// FINAL chat.js — Consolidated with all functionality

// ---------------- GLOBAL VARIABLES ----------------
let chatbox, userInput, sendButton;

// Dropdown data
const severityOptions = [
    "Minor - No injury",
    "Moderate - First aid required",
    "Serious - Medical treatment needed",
    "Critical - Hospitalization required",
    "Severe - Long-term disability possible",
    "Fatal - Death"
];

const fieldOptions = {
    accident_type: ["Caught Between", "Caught In", "Caught On", "Contact By", "Contact With", "Exposure", "Exposure (Suspected)", "Fall Below", "Fall Same Level", "Foreign Body Eye", "Slip (No Fall)", "Slip/Trip/Fall", "Strain/Overexertion", "Struck Against", "Struck By"],
    accident_agent: ["Action of Employee", "AGV (Automated Guided Vehicle)", "Asbestos", "Attaching a curtain to the rib", "Automated Welder (Pedestal/Spot)", "Banding/Wrapping Materials&Equipt", "Beam", "Belt", "Bin", "Bins/Totes/Racks or Gaylords", "Blower Fan (Heater/AC)", "Bulldozers", "Bumper Handrail", "Burning/Welding, Lancing Equipment", "Cable", "Chainfall, Come-a-long", "Chemicals Other", "Chemicals: Corrosive", "Chemicals: Toxic", "Chisel"],
    injury_type: ["Abrasion", "Amputation", "Asphyxiation", "Avulsion", "Burn", "Concussion", "Conjunctivitis", "Contusion", "Crushing", "Dermatitis", "Dislocation", "Electric Flash", "Electric Shock/Burns", "Foreign Body", "Fracture", "Frostbite", "Hearing Loss", "Heat Related", "Hernia", "Insect Sting"],
    injury_agent: ["Rib", "Rock", "Rock Truck Cab", "Roller", "Roller flange", "Roof bolt plates", "Roof bolts", "SARS-CoV-2", "Scaffold", "Scooters, Buggies", "Scrap", "Shell Rock", "Shuttle Car", "Slats and Clevises", "Sledgehammer", "Slivers/Burrs", "Stairs/Railing", "Steam / Hot Water", "Steering wheel", "Test Samples"]
};

// ---------------- MAIN INIT ----------------
document.addEventListener("DOMContentLoaded", function () {
    chatbox = document.getElementById("chatbox");
    userInput = document.getElementById("userInput");
    sendButton = document.querySelector(".input-container button");

    // Bind events
    userInput.addEventListener("keypress", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });

    sendButton.addEventListener("click", sendMessage);

    $("#datepicker").datepicker({ dateFormat: 'yy-mm-dd', changeMonth: true, changeYear: true });
    setupSeverityAutocomplete();
    checkUnfinishedReport();
});

// ---------------- CORE FUNCTIONS ----------------
function sendMessage(customMessage = null) {
    let message = customMessage || userInput.value.trim();
    if (!message && customMessage === null) return;

    // Check if action widget is visible
    if (document.getElementById("actions-taken-widget").style.display !== "none") {
        let selectedActions = [];
        document.querySelectorAll("#suggested-actions input:checked").forEach(cb => selectedActions.push(cb.value));
        let customAction = document.getElementById("custom-action").value.trim();
        if (customAction) selectedActions.push(customAction);
        document.getElementById("actions-taken-widget").style.display = "none";
        message = JSON.stringify({ actions_taken: selectedActions });
    }

    appendMessage("user", message);
    userInput.value = "";

    const sessionId = getSessionId();
    const loadingDiv = document.createElement("div");
    loadingDiv.className = 'message bot-message';
    loadingDiv.id = 'loading-indicator';
    loadingDiv.innerHTML = `<div class="typing-indicator"><span></span><span></span><span></span></div>`;
    chatbox.appendChild(loadingDiv);

    userInput.disabled = true;
    sendButton.disabled = true;

    fetch(`/api/chat/?session_id=${sessionId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: message })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById("loading-indicator")?.remove();
        userInput.disabled = false;
        sendButton.disabled = false;

        if (data.response) appendMessage("bot", data.response);
        if (data.extracted) updateSidebarFromExtracted(data.extracted);
        if (data.summary) showSummary(data.summary);
        if (data.show_widget === "actions-taken-widget") {
            showActionsTakenWidget(data.suggestions || []);
            return;
        }
        handleWidgets(data);

        if (data.response && data.response.includes("successfully recorded")) {
            clearSession();
        }
    })
    .catch(err => {
        console.error("Error:", err);
        document.getElementById("loading-indicator")?.remove();
        userInput.disabled = false;
        sendButton.disabled = false;
        appendMessage("bot", "Sorry, something went wrong.");
    });
}

// ---------------- UI HELPERS ----------------
function appendMessage(sender, message) {
    let bubble = document.createElement("div");
    bubble.classList.add("chat-bubble", sender === "user" ? "user-bubble" : "bot-bubble");
    bubble.innerHTML = `<strong>${sender === "user" ? "You" : "Bot"}:</strong> ${message}`;
    chatbox.appendChild(bubble);
    chatbox.scrollTop = chatbox.scrollHeight;
}

function showActionsTakenWidget(suggestions) {
    const container = document.getElementById("suggested-actions");
    container.innerHTML = "";

    if (!Array.isArray(suggestions) || suggestions.length === 0) {
        container.innerHTML = "<em>No suggested actions available.</em>";
    } else {
        suggestions.forEach((action, index) => {
            const checkbox = document.createElement("input");
            checkbox.type = "checkbox";
            checkbox.value = action;
            checkbox.id = `action-${index}`;

            const label = document.createElement("label");
            label.htmlFor = checkbox.id;
            label.innerText = action;

            const line = document.createElement("div");
            line.appendChild(checkbox);
            line.appendChild(label);

            container.appendChild(line);
        });
    }

    document.getElementById("actions-taken-widget").style.display = "block";
}

function showSummary(summary) {
    appendMessage("bot", `<strong>Summary:</strong> ${JSON.stringify(summary, null, 2)}`);
    appendMessage("bot", "Does everything look correct? Type 'yes' to confirm or correct any field.");
}

function updateSidebarFromExtracted(extracted) {
    if (extracted.basic_info) {
        for (const [key, value] of Object.entries(extracted.basic_info)) {
            const el = document.getElementById(`field-${key}`);
            if (el) el.textContent = value || 'Missing';
        }
    }
    if (extracted.injury_data) {
        for (const [key, value] of Object.entries(extracted.injury_data)) {
            const el = document.getElementById(`field-${key}`);
            if (el) el.textContent = value || 'Missing';
        }
    }
}

function handleWidgets(data) {
    const mapping = {
        'date-picker': '#date-picker-widget',
        'severity-picker': '#severity-picker',
        'person-type-picker': '#person-type-picker',
        'accident-agent-picker': '#accident-agent-picker',
        'accident-type-picker': '#accident-type-picker',
        'injury-type-picker': '#injury-type-picker',
        'injury-agent-picker': '#injury-agent-picker'
    };

    hideAllWidgets();
    if (data.show_widget && mapping[data.show_widget]) {
        document.querySelector(mapping[data.show_widget]).style.display = "block";
        userInput.disabled = true;
    }
}

function hideAllWidgets() {
    ["date-picker-widget", "severity-picker", "person-type-picker", "accident-agent-picker", "accident-type-picker", "injury-type-picker", "injury-agent-picker", "actions-taken-widget", "confirm-buttons", "summary-buttons", "additional-info"].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.style.display = "none";
    });
}

// ---------------- SESSION HELPERS ----------------
function getSessionId() {
    let sessionId = localStorage.getItem('incident_report_session_id');
    if (!sessionId) {
        sessionId = 'session_' + Date.now();
        localStorage.setItem('incident_report_session_id', sessionId);
    }
    return sessionId;
}

function clearSession() {
    localStorage.removeItem('incident_report_session_id');
}

function checkUnfinishedReport() {
    const sessionId = getSessionId();
    fetch(`/api/chat/?session_id=${sessionId}&check_unfinished=true`)
        .then(res => res.json())
        .then(data => {
            if (data.has_unfinished) {
                console.log("[DEBUG] Found unfinished report.");
                // optional logic to prompt restore
            }
        });
}

// ---------------- AUTOCOMPLETE ----------------
function setupSeverityAutocomplete() {
    const input = document.getElementById('severity-input');
    const dropdown = document.getElementById('severity-dropdown');

    input.addEventListener('input', function () {
        const value = this.value.toLowerCase();
        dropdown.innerHTML = '';
        const matches = severityOptions.filter(opt => opt.toLowerCase().includes(value));

        matches.forEach(match => {
            const div = document.createElement('div');
            div.className = 'dropdown-item';
            div.textContent = match;
            div.onclick = function () {
                input.value = match;
                dropdown.style.display = 'none';
            };
            dropdown.appendChild(div);
        });
        dropdown.style.display = matches.length > 0 ? 'block' : 'none';
    });

    document.addEventListener('click', function (e) {
        if (!input.contains(e.target) && !dropdown.contains(e.target)) {
            dropdown.style.display = 'none';
        }
    });
}
