// Avalon Frontend Logic
let socket = null;
let username = "";
let roomCode = "";
let isHost = false;
let isCardFlipped = false;

// DOM Elements
const views = {
    lobby: document.getElementById("lobby-view"),
    room: document.getElementById("room-view"),
    game: document.getElementById("game-view")
};

// Help Modal elements
const helpBtn = document.getElementById("help-btn");
const rulesModal = document.getElementById("rules-modal");
const closeModalBtn = document.getElementById("close-modal-btn");
const modalCloseBtn = document.getElementById("modal-close-btn");

// Lobby elements
const usernameInput = document.getElementById("username-input");
const roomNameInput = document.getElementById("room-name-input");
const hostBtn = document.getElementById("host-btn");
const roomsList = document.getElementById("rooms-list");
const noRoomsMessage = document.getElementById("no-rooms-message");

// Room elements
const roomTitle = document.getElementById("room-title");
const roomCodeDisplay = document.getElementById("room-code");
const playersList = document.getElementById("players-list");
const playerCount = document.getElementById("player-count");
const distGood = document.getElementById("dist-good");
const distEvil = document.getElementById("dist-evil");
const leaveRoomBtn = document.getElementById("leave-room-btn");
const startGameBtn = document.getElementById("start-game-btn");
const startWarning = document.getElementById("start-warning");

// Role toggles
const roleToggles = {
    merlin: document.getElementById("role-toggle-merlin"),
    percival: document.getElementById("role-toggle-percival"),
    morgana: document.getElementById("role-toggle-morgana"),
    mordred: document.getElementById("role-toggle-mordred"),
    oberon: document.getElementById("role-toggle-oberon"),
    lovers: document.getElementById("role-toggle-lovers")
};

// Game view elements
const roleCardInner = document.getElementById("role-card-inner");
const rolePortrait = document.getElementById("role-portrait");
const roleNameDisplay = document.getElementById("role-name-display");
const roleAlignmentBadge = document.getElementById("role-alignment-badge");
const roleDescription = document.getElementById("role-description");
const infoContentBox = document.getElementById("info-content-box");
const gameSizeDisplay = document.getElementById("game-size-display");
const missionTrackNodes = document.getElementById("mission-track-nodes");
const gameResetBtn = document.getElementById("game-reset-btn");
const gameLeaveBtn = document.getElementById("game-leave-btn");

// Toast
const toast = document.getElementById("toast");
const toastMessage = document.getElementById("toast-message");

// Initialize application event listeners
function init() {
    // Modal events
    helpBtn.addEventListener("click", () => showModal(true));
    closeModalBtn.addEventListener("click", () => showModal(false));
    modalCloseBtn.addEventListener("click", () => showModal(false));
    
    // Close modal on background click
    window.addEventListener("click", (e) => {
        if (e.target === rulesModal) {
            showModal(false);
        }
        if (e.target === document.getElementById("password-modal")) {
            closePasswordPrompt();
        }
        if (e.target === document.getElementById("invite-modal")) {
            declineInvite();
        }
    });

    // Password Modal Events
    document.getElementById("cancel-password-btn").addEventListener("click", closePasswordPrompt);
    document.getElementById("submit-password-btn").addEventListener("click", submitPasswordPrompt);
    document.getElementById("join-room-password-input").addEventListener("keydown", (e) => {
        if (e.key === "Enter") {
            submitPasswordPrompt();
        }
    });

    // Invite Modal Events
    document.getElementById("accept-invite-btn").addEventListener("click", acceptInvite);
    document.getElementById("decline-invite-btn").addEventListener("click", declineInvite);

    // Lobby action events
    hostBtn.addEventListener("click", handleHostRoom);
    
    // Room action events
    leaveRoomBtn.addEventListener("click", handleLeaveRoom);
    startGameBtn.addEventListener("click", handleStartGame);
    document.getElementById("random-teams-btn").addEventListener("click", () => sendEvent("randomize_teams"));
    
    // Add event listeners to all role toggles
    Object.values(roleToggles).forEach(toggle => {
        toggle.addEventListener("change", handleRoleToggleChange);
    });

    // Game action events
    gameLeaveBtn.addEventListener("click", handleLeaveRoom);
    gameResetBtn.addEventListener("click", handleResetGame);

    // Auto-fill a name if saved in session storage
    const savedName = sessionStorage.getItem("avalon_username");
    if (savedName) {
        usernameInput.value = savedName;
    }

    // Connect immediately on load to populate the active rooms list
    connectWebSocket();
}

// Show views utility
function showView(viewName) {
    Object.keys(views).forEach(key => {
        if (key === viewName) {
            views[key].classList.add("active");
        } else {
            views[key].classList.remove("active");
        }
    });
}

// Toast Notifications
function showToast(message) {
    toastMessage.textContent = message;
    toast.classList.add("show");
    setTimeout(() => {
        toast.classList.remove("show");
    }, 4000);
}

// Modal control
function showModal(show) {
    if (show) {
        rulesModal.classList.add("show");
    } else {
        rulesModal.classList.remove("show");
    }
}

function switchModalTab(evt, tabId) {
    const tabContents = document.getElementsByClassName("tab-content");
    for (let i = 0; i < tabContents.length; i++) {
        tabContents[i].classList.remove("active");
    }

    const tabLinks = document.getElementsByClassName("tab-link");
    for (let i = 0; i < tabLinks.length; i++) {
        tabLinks[i].classList.remove("active");
    }

    document.getElementById(tabId).classList.add("active");
    evt.currentTarget.classList.add("active");
}

// 3D Card Reveal Flip
function flipRoleCard() {
    isCardFlipped = !isCardFlipped;
    if (isCardFlipped) {
        roleCardInner.classList.add("flipped");
    } else {
        roleCardInner.classList.remove("flipped");
    }
}

// Setup and establish WebSocket connection
function connectWebSocket(onConnectedCallback) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        if (onConnectedCallback) onConnectedCallback();
        return;
    }

    // Determine WS protocol based on page protocol
    const wsProtocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`;
    
    socket = new WebSocket(wsUrl);

    socket.onopen = () => {
        console.log("WebSocket connection established");
        
        // Auto-rejoin room if connection was lost
        const savedRoom = sessionStorage.getItem("avalon_room_code");
        const savedName = sessionStorage.getItem("avalon_username");
        if (savedRoom && savedName) {
            username = savedName;
            roomCode = savedRoom;
            console.log(`Auto-rejoining room ${roomCode} as ${username}`);
            sendEvent("join_room", { username: username, room_id: roomCode });
        }
        
        if (onConnectedCallback) onConnectedCallback();
    };

    socket.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log("Received socket event:", data);
        handleServerMessage(data);
    };

    socket.onclose = (event) => {
        console.log("WebSocket connection closed", event);
        showToast("Lost connection to Avalon court. Reconnecting...");
        setTimeout(() => connectWebSocket(), 3000);
        showView("lobby");
    };

    socket.onerror = (error) => {
        console.error("WebSocket error:", error);
    };
}

// Send event through socket with auto-reconnect fallback
function sendEvent(type, payload = {}) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type, ...payload }));
    } else {
        showToast("Reconnecting to Avalon Court...");
        connectWebSocket(() => {
            if (socket && socket.readyState === WebSocket.OPEN) {
                socket.send(JSON.stringify({ type, ...payload }));
            }
        });
    }
}

// Validate Username before proceeding
function getAndValidateUsername() {
    const val = usernameInput.value.trim();
    if (!val) {
        showToast("You must enter a noble name to enter Camelot!");
        usernameInput.focus();
        return null;
    }
    username = val;
    return username;
}

let activeJoinCode = null;
let activeJoinSpectator = false;

function showPasswordPrompt(code, isSpectator, message = "") {
    activeJoinCode = code;
    activeJoinSpectator = isSpectator;
    
    const passwordModal = document.getElementById("password-modal");
    const passwordInput = document.getElementById("join-room-password-input");
    
    passwordInput.value = "";
    passwordModal.style.display = "flex";
    passwordInput.focus();
}

function closePasswordPrompt() {
    const passwordModal = document.getElementById("password-modal");
    passwordModal.style.display = "none";
    activeJoinCode = null;
}

function submitPasswordPrompt() {
    if (!activeJoinCode) return;
    
    const passwordInput = document.getElementById("join-room-password-input");
    const passcode = passwordInput.value.trim();
    if (!passcode) {
        showToast("Enter the passcode to enter the court!");
        passwordInput.focus();
        return;
    }
    
    sendEvent("join_room", { 
        username: username, 
        room_id: activeJoinCode, 
        spectator: activeJoinSpectator, 
        password: passcode 
    });
    
    closePasswordPrompt();
}

let activeRequester = null;

function showInvitePrompt(requesterName) {
    activeRequester = requesterName;
    const inviteModal = document.getElementById("invite-modal");
    const inviteMsg = document.getElementById("invite-message");
    inviteMsg.textContent = `${requesterName} wishes to form an alliance with you for this match.`;
    inviteModal.style.display = "flex";
}

function acceptInvite() {
    if (activeRequester) {
        sendEvent("accept_partner_request", { requester: activeRequester });
    }
    closeInvitePrompt();
}

function declineInvite() {
    if (activeRequester) {
        sendEvent("decline_partner_request", { requester: activeRequester });
    }
    closeInvitePrompt();
}

function closeInvitePrompt() {
    const inviteModal = document.getElementById("invite-modal");
    inviteModal.style.display = "none";
    activeRequester = null;
}

let hostSelectedPlayer = null;

function handleHostPairingClick(pName) {
    if (!isHost) return;
    
    if (hostSelectedPlayer === null) {
        hostSelectedPlayer = pName;
        showToast(`Select partner for ${pName}...`);
        const el = document.getElementById("player-row-" + pName);
        if (el) el.classList.add("host-selection-pending");
    } else if (hostSelectedPlayer === pName) {
        const el = document.getElementById("player-row-" + pName);
        if (el) el.classList.remove("host-selection-pending");
        hostSelectedPlayer = null;
        showToast("Teaming selection cancelled.");
    } else {
        sendEvent("host_partner_up", { player1: hostSelectedPlayer, player2: pName });
        hostSelectedPlayer = null;
    }
}

function handleHostBreakTeam(pName) {
    if (!isHost) return;
    sendEvent("leave_team", { target: pName });
}

function handlePartnerUp(targetName) {
    sendEvent("request_partner", { target: targetName });
    showToast(`alliance request sent to ${targetName}. Waiting...`);
}

function handleLeaveTeam() {
    sendEvent("leave_team");
}

// UI Actions
function handleHostRoom() {
    if (!getAndValidateUsername()) return;
    
    const roomName = roomNameInput.value.trim() || `${username}'s Great Hall`;
    const passwordVal = document.getElementById("host-room-password").value.trim();
    sessionStorage.setItem("avalon_username", username);
    const isSpectator = document.getElementById("spectator-toggle").checked;
    
    sendEvent("create_room", { username: username, room_name: roomName, spectator: isSpectator, password: passwordVal });
}

function handleJoinRoom(code, hasPassword = false) {
    if (!getAndValidateUsername()) return;
    sessionStorage.setItem("avalon_username", username);
    const isSpectator = document.getElementById("spectator-toggle").checked;
    
    if (hasPassword) {
        showPasswordPrompt(code, isSpectator);
    } else {
        sendEvent("join_room", { username: username, room_id: code, spectator: isSpectator });
    }
}

function handleLeaveRoom() {
    sendEvent("leave_room");
}

function handleRoleToggleChange() {
    if (!isHost) return;
    
    const toggles = {
        merlin: true, // Always required
        percival: roleToggles.percival.checked,
        morgana: roleToggles.morgana.checked,
        mordred: roleToggles.mordred.checked,
        oberon: roleToggles.oberon.checked,
        lovers: roleToggles.lovers.checked
    };
    
    sendEvent("update_roles", { toggles });
}

function handleStartGame() {
    sendEvent("start_game");
}

function handleResetGame() {
    sendEvent("reset_game");
}

// Process Server Events
function handleServerMessage(data) {
    switch (data.type) {
        case "lobby_update":
            renderLobbyRooms(data.rooms);
            break;
            
        case "room_joined":
            roomCode = data.room_id;
            isHost = data.is_host;
            sessionStorage.setItem("avalon_room_code", roomCode);
            
            // Adjust role toggle inputs for host/non-host
            Object.keys(roleToggles).forEach(key => {
                if (key !== "merlin" && key !== "assassin") {
                    roleToggles[key].disabled = !isHost;
                }
            });
            
            showView("room");
            break;
            
        case "room_update":
            renderRoomDetails(data);
            break;
            
        case "game_start":
            renderGameView(data);
            break;
            
        case "left_room":
            roomCode = "";
            isHost = false;
            sessionStorage.removeItem("avalon_room_code");
            showView("lobby");
            break;
            
        case "password_required":
            const isSpec = document.getElementById("spectator-toggle").checked;
            showPasswordPrompt(data.room_id, isSpec, data.message || "Passcode required.");
            break;
            
        case "partner_request":
            showInvitePrompt(data.requester);
            break;
            
        case "partner_request_declined":
            showToast(`${data.target} declined your alliance request.`);
            break;
            
        case "error":
            showToast(data.message);
            break;
    }
}

// Render Room Lists in Lobby
function renderLobbyRooms(rooms) {
    roomsList.innerHTML = "";
    if (rooms.length === 0) {
        noRoomsMessage.style.display = "flex";
        return;
    }
    
    noRoomsMessage.style.display = "none";
    rooms.forEach(room => {
        const item = document.createElement("div");
        item.className = "room-item";
        
        const stateTag = room.state === "STARTED" ? 
            `<span class="badge-evil" style="font-size:0.65rem;">In Progress</span>` : 
            `<span class="badge" style="border-color:#10b981; color:#10b981; font-size:0.65rem;">Lobby</span>`;
            
        const lockIcon = room.has_password ? 
            `<i class="fa-solid fa-lock" style="color: var(--gold); margin-left: 6px; font-size: 0.8rem;" title="Passcode Protected"></i>` : "";
            
        item.innerHTML = `
            <div class="room-info">
                <span class="room-name-lbl" style="display: inline-flex; align-items: center; gap: 4px;">
                    ${escapeHtml(room.name)} ${lockIcon}
                </span>
                <span class="room-meta-lbl">Code: <strong>${room.room_id}</strong> &bull; Host: ${escapeHtml(room.host)} &bull; ${stateTag}</span>
            </div>
            <div class="room-item-actions">
                <span class="badge">${room.active_count}/20 Players${room.spec_count > 0 ? ` + ${room.spec_count} Spectators` : ''}</span>
                <button class="btn btn-secondary room-join-btn" ${room.active_count >= 20 || room.state === 'STARTED' ? 'disabled' : ''} onclick="handleJoinRoom('${room.room_id}', ${room.has_password})">
                    Join
                </button>
            </div>
        `;
        roomsList.appendChild(item);
    });
}

// Render Joined Room Details
function renderRoomDetails(data) {
    roomTitle.textContent = escapeHtml(data.name);
    roomCodeDisplay.textContent = data.room_id;
    
    // Calculate active and spectator counts
    const activePlayers = data.players.filter(p => typeof p === "string" ? true : !p.spectator);
    const spectators = data.players.filter(p => typeof p === "string" ? false : p.spectator);
    
    let displayCount = `${activePlayers.length}/20`;
    if (spectators.length > 0) {
        displayCount += ` + ${spectators.length} spectator${spectators.length > 1 ? 's' : ''}`;
    }
    playerCount.textContent = displayCount;
    
    // Good/Evil distributions
    distGood.textContent = data.good_count;
    distEvil.textContent = data.evil_count;
    
    // Update role settings toggles visual states based on backend sync
    Object.keys(data.toggles).forEach(key => {
        if (roleToggles[key]) {
            roleToggles[key].checked = data.toggles[key];
        }
    });

    // Draw player list
    playersList.innerHTML = "";
    
    // Get partner of the current user
    const mePlayer = data.players.find(p => (typeof p === "string" ? p : p.username) === username);
    const myPartnerName = (mePlayer && typeof mePlayer !== "string") ? mePlayer.partner : null;

    data.players.forEach(p => {
        const pName = typeof p === "string" ? p : p.username;
        const isOnline = typeof p === "string" ? true : p.online;
        const isSpectator = typeof p === "string" ? false : p.spectator;
        const partnerName = typeof p === "string" ? null : p.partner;
        
        const li = document.createElement("li");
        li.className = `player-item ${data.host === pName ? 'is-host-item' : ''}`;
        li.id = `player-row-${pName}`;
        if (isHost && hostSelectedPlayer === pName) {
            li.classList.add("host-selection-pending");
        }
        if (!isOnline) {
            li.style.opacity = "0.5";
        }
        
        const isMe = pName === username;
        const hostTag = data.host === pName ? `<span class="host-indicator"><i class="fa-solid fa-crown"></i> Host</span>` : "";
        const meTag = isMe ? `<span class="me-indicator">(You)</span>` : "";
        const offlineTag = !isOnline ? `<span class="text-muted" style="font-size:0.75rem; margin-left: 6px; font-style:italic;">(disconnected)</span>` : "";
        const spectatorTag = isSpectator ? `<span class="badge" style="border-color:#a855f7; color:#c084fc; font-size:0.65rem; padding: 2px 6px; margin-left: 6px;">Spectator</span>` : "";
        
        // Team tags and actions
        let teamTag = "";
        let actionBtn = "";
        
        if (!isSpectator) {
            if (partnerName) {
                teamTag = `<span class="badge" style="border-color: var(--gold); color: var(--gold); font-size: 0.65rem; padding: 2px 6px; margin-left: 6px;"><i class="fa-solid fa-handshake"></i> Partner: ${escapeHtml(partnerName)}</span>`;
                if (isMe) {
                    actionBtn = `<button class="btn btn-secondary btn-icon-only" style="padding: 2px 6px; font-size: 0.7rem; margin-left: auto;" onclick="handleLeaveTeam()" title="Leave Team"><i class="fa-solid fa-link-slash"></i></button>`;
                } else if (isHost) {
                    actionBtn = `<button class="btn btn-secondary btn-icon-only" style="padding: 2px 6px; font-size: 0.7rem; margin-left: auto;" onclick="handleHostBreakTeam('${escapeHtml(pName)}')" title="Break Team"><i class="fa-solid fa-link-slash"></i></button>`;
                }
            } else {
                if (isHost) {
                    actionBtn = `<button class="btn btn-secondary" style="padding: 2px 6px; font-size: 0.7rem; margin-left: auto;" onclick="handleHostPairingClick('${escapeHtml(pName)}')"><i class="fa-solid fa-link"></i> Team Up</button>`;
                } else if (!myPartnerName && !isMe) {
                    actionBtn = `<button class="btn btn-secondary" style="padding: 2px 6px; font-size: 0.7rem; margin-left: auto;" onclick="handlePartnerUp('${escapeHtml(pName)}')"><i class="fa-solid fa-link"></i> Team Up</button>`;
                }
            }
        }
        
        li.innerHTML = `
            <div style="display:flex; align-items:center; width: 100%;">
                <span>${meTag}${escapeHtml(pName)}${offlineTag}${spectatorTag}${teamTag}</span>
                ${hostTag}
                ${actionBtn}
            </div>
        `;
        playersList.appendChild(li);
    });

    const randomTeamsBtn = document.getElementById("random-teams-btn");

    // Host capabilities adjustments
    if (isHost) {
        startGameBtn.style.display = "inline-flex";
        randomTeamsBtn.style.display = "inline-flex";
        
        // Calculate entities count (teams of 2 and solo players)
        let entityCount = 0;
        const counted = new Set();
        activePlayers.forEach(p => {
            const pName = typeof p === "string" ? p : p.username;
            if (counted.has(pName)) return;
            const partnerName = typeof p === "string" ? null : p.partner;
            if (partnerName) {
                entityCount += 1;
                counted.add(pName);
                counted.add(partnerName);
            } else {
                entityCount += 1;
                counted.add(pName);
            }
        });
        
        if (activePlayers.length >= 5 && entityCount >= 5 && entityCount <= 10) {
            startGameBtn.removeAttribute("disabled");
            startWarning.style.display = "none";
        } else {
            startGameBtn.setAttribute("disabled", "true");
            if (activePlayers.length < 5) {
                startWarning.textContent = "Need at least 5 active players to start.";
            } else if (entityCount > 10) {
                startWarning.textContent = `Currently ${entityCount} entities (teams/individuals). Group up more to bring it down to 10 entities!`;
            } else {
                startWarning.textContent = `Need between 5 and 10 teams/players to start. (Currently ${entityCount})`;
            }
            startWarning.style.display = "block";
        }
    } else {
        startGameBtn.style.display = "none";
        randomTeamsBtn.style.display = "none";
        startWarning.style.display = "none";
    }

    // If game has moved to started, adjust buttons
    if (data.state === "STARTED") {
        // Wait for specific role information payload to handle transition,
        // but just in case, ensure UI isn't stuck on lobby
    }
}

// Render active game view
function renderGameView(data) {
    const roleInfo = data.role_info;
    const missionTrack = data.mission_track;
    const numPlayers = data.players.length;

    // Reset card flip
    isCardFlipped = false;
    roleCardInner.classList.remove("flipped");

    // Populate role details
    roleNameDisplay.textContent = roleInfo.role;
    roleDescription.textContent = roleInfo.description;
    
    // Reset/assign portrait image with fallback handler
    rolePortrait.src = roleInfo.portrait;
    rolePortrait.onerror = function() {
        // Simple letter representation if no portrait exists yet
        this.src = `https://placehold.co/300x400/1a1a2e/ffffff?text=${encodeURIComponent(roleInfo.role)}`;
    };

    // Alignment coloring
    if (roleInfo.alignment === "Good") {
        roleAlignmentBadge.textContent = "Good";
        roleAlignmentBadge.className = "alignment-badge good";
        roleNameDisplay.className = "role-title font-good";
    } else {
        roleAlignmentBadge.textContent = "Evil";
        roleAlignmentBadge.className = "alignment-badge evil";
        roleNameDisplay.className = "role-title font-evil";
    }

    // Populate insights box
    infoContentBox.innerHTML = "";
    if (roleInfo.info && roleInfo.info.length > 0) {
        roleInfo.info.forEach(line => {
            const p = document.createElement("p");
            p.className = "info-line";
            
            // Format highlights (e.g. bolding player names or alignments)
            let formattedLine = escapeHtml(line);
            formattedLine = formattedLine.replace(/(Evil|Good)/g, '<strong class="font-$1">$1</strong>');
            
            p.innerHTML = `<i class="fa-solid fa-eye-low-vision" style="margin-right:8px; color:var(--gold);"></i> ${formattedLine}`;
            infoContentBox.appendChild(p);
        });
    } else {
        infoContentBox.innerHTML = `<p class="info-line text-muted">You have no visions. Use deduction to find your allies.</p>`;
    }

    // Draw Mission Track
    gameSizeDisplay.textContent = numPlayers;
    missionTrackNodes.innerHTML = "";
    
    missionTrack.forEach((mission, idx) => {
        const node = document.createElement("div");
        let nodeClass = "mission-node";
        
        // Highlight current/first mission
        if (idx === 0) {
            nodeClass += " current";
        }
        
        // Check if double failures are required (7+ players mission 4)
        if (mission.fails_required === 2) {
            nodeClass += " fail-two";
        }
        
        node.className = nodeClass;
        node.innerHTML = `
            <span class="mission-label">Q${mission.mission_num}</span>
            <span class="mission-count">${mission.size}</span>
        `;
        
        missionTrackNodes.appendChild(node);
    });

    // Control buttons visibility
    if (isHost) {
        gameResetBtn.style.display = "inline-flex";
    } else {
        gameResetBtn.style.display = "none";
    }

    showView("game");
}

// Utility to escape HTML and prevent XSS
function escapeHtml(str) {
    if (typeof str !== "string") return str;
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

// Global Window handlers for dynamic onclick actions
window.handlePartnerUp = (targetName) => {
    handlePartnerUp(targetName);
};

window.handleLeaveTeam = () => {
    handleLeaveTeam();
};

window.handleHostPairingClick = (targetName) => {
    handleHostPairingClick(targetName);
};

window.handleHostBreakTeam = (targetName) => {
    handleHostBreakTeam(targetName);
};

// Run application
document.addEventListener("DOMContentLoaded", init);
