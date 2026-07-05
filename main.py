import asyncio
import json
import logging
import random
import string
from typing import Dict, List, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

from game_logic import (
    assign_roles, 
    get_role_info, 
    get_mission_track, 
    get_game_distribution
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("avalon_server")

app = FastAPI(title="Avalon Game Server")

# Mount the static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Redirection from root to static index.html
@app.get("/")
async def get_root():
    return RedirectResponse(url="/static/index.html")

# In-memory database of active players and rooms
class ConnectionManager:
    def __init__(self):
        # Maps websocket to username
        self.active_connections: Dict[WebSocket, str] = {}
        # Maps username to room_id
        self.player_rooms: Dict[str, str] = {}
        # List of websockets in the main lobby (not in any room)
        self.lobby_sockets: Set[WebSocket] = set()

    def connect_socket(self, websocket: WebSocket):
        self.active_connections[websocket] = None
        self.lobby_sockets.add(websocket)
        logger.info("New anonymous socket connected to lobby")

    def register_username(self, websocket: WebSocket, username: str):
        self.active_connections[websocket] = username
        logger.info(f"Registered username '{username}' for socket")

    def disconnect(self, websocket: WebSocket) -> tuple[str, str]:
        username = self.active_connections.pop(websocket, None)
        self.lobby_sockets.discard(websocket)
        room_id = self.player_rooms.pop(username, None) if username else None
        logger.info(f"Player {username} disconnected from room {room_id}")
        return username, room_id

    def move_to_room(self, username: str, room_id: str, websocket: WebSocket):
        self.player_rooms[username] = room_id
        self.lobby_sockets.discard(websocket)

    def move_to_lobby(self, username: str, websocket: WebSocket):
        self.player_rooms.pop(username, None)
        self.lobby_sockets.add(websocket)

    async def broadcast_lobby(self, rooms_summary: List[Dict]):
        payload = json.dumps({
            "type": "lobby_update",
            "rooms": rooms_summary
        })
        for ws in self.lobby_sockets:
            try:
                await ws.send_text(payload)
            except Exception as e:
                logger.error(f"Error broadcasting to lobby socket: {e}")

manager = ConnectionManager()

# Global Room storage
# Structure:
# {
#     "room_id": {
#         "name": "Room Name",
#         "host": "username",
#         "players": [{"username": "...", "ws": WebSocket}],
#         "state": "LOBBY" | "STARTED",
#         "toggles": {"merlin": True, "percival": True, ...},
#         "assignments": {"username": "role"},
#         "mission_track": [...]
#     }
# }
rooms: Dict[str, Dict] = {}

def generate_room_id() -> str:
    """Generates a 4-letter unique room code."""
    while True:
        code = "".join(random.choices(string.ascii_uppercase, k=4))
        if code not in rooms:
            return code

def get_rooms_summary() -> List[Dict]:
    """Returns a list of rooms with details for the lobby view."""
    summary = []
    for r_id, room in rooms.items():
        players = room["players"]
        active_count = len([p for p in players if not p.get("is_spectator")])
        spec_count = len([p for p in players if p.get("is_spectator")])
        summary.append({
            "room_id": r_id,
            "name": room["name"],
            "active_count": active_count,
            "spec_count": spec_count,
            "state": room["state"],
            "host": room["host"],
            "has_password": bool(room.get("password"))
        })
    return summary

async def delayed_remove_player(username: str, room_id: str, old_ws: WebSocket):
    """Wait for a grace period, then remove player from room if they haven't reconnected."""
    await asyncio.sleep(120) # 120 seconds (2 minutes) reconnect window
    room = rooms.get(room_id)
    if not room:
        return
        
    for p in room["players"]:
        if p["username"] == username:
            if p["ws"] is None or p["ws"] == old_ws:
                # If the game has started, do NOT automatically remove active (non-spectator) players!
                if room["state"] == "STARTED" and not p.get("is_spectator"):
                    logger.info(f"Player {username} disconnected during active game. Keeping their slot.")
                    break
                # Still offline/disconnected, remove permanently
                await remove_player_from_room(username, room_id, old_ws)
                logger.info(f"Grace period expired. Removed player {username} from room {room_id}")
                break

async def broadcast_room_update(room_id: str):
    """Broadcasts current room state to all players in the room."""
    room = rooms.get(room_id)
    if not room:
        return

    # Send objects containing name, online status, spectator status, and partner status
    player_list = [{
        "username": p["username"], 
        "online": p["ws"] is not None, 
        "spectator": p.get("is_spectator", False),
        "partner": p.get("partner")
    } for p in room["players"]]
    
    # Good/Evil count is determined by active players only
    active_player_count = len([p for p in room["players"] if not p.get("is_spectator", False)])
    good_count, evil_count = get_game_distribution(active_player_count)

    payload = {
        "type": "room_update",
        "room_id": room_id,
        "name": room["name"],
        "host": room["host"],
        "players": player_list,
        "state": room["state"],
        "toggles": room["toggles"],
        "good_count": good_count,
        "evil_count": evil_count
    }

    for p in room["players"]:
        ws = p["ws"]
        if not ws: # Skip disconnected players
            continue
        try:
            await ws.send_text(json.dumps(payload))
        except Exception as e:
            logger.error(f"Error sending room update to {p['username']}: {e}")

def get_room_entities(room: Dict) -> List[List[str]]:
    """
    Groups active players in the room into entities.
    Each entity is a list of player names (either 1 or 2 names).
    """
    active_players = [p for p in room["players"] if not p.get("is_spectator")]
    entities = []
    visited = set()
    
    # First, add paired entities
    for p in active_players:
        name = p["username"]
        if name in visited:
            continue
        partner_name = p.get("partner")
        if partner_name:
            # Check if partner is also in active_players and hasn't been visited
            partner_p = next((x for x in active_players if x["username"] == partner_name), None)
            if partner_p and partner_name not in visited:
                entities.append([name, partner_name])
                visited.add(name)
                visited.add(partner_name)
                
    # Next, add remaining solo players
    for p in active_players:
        name = p["username"]
        if name not in visited:
            entities.append([name])
            visited.add(name)
            
    return entities

async def start_avalon_game(room_id: str):
    """Assigns roles and notifies all players in the room."""
    room = rooms.get(room_id)
    if not room:
        return

    # Group players into entities (teams of 2 and solo players)
    entities = get_room_entities(room)
    num_entities = len(entities)
    
    if num_entities < 5 or num_entities > 10:
        # Invalid entity count
        return

    # 1. Assign roles to entities
    entity_keys = [ent[0] for ent in entities]
    assignments = assign_roles(entity_keys, room["toggles"])
    
    # 2. Map role assignments back to all individual players in each entity
    room_assignments = {}
    for ent in entities:
        role = assignments[ent[0]]
        for player_name in ent:
            room_assignments[player_name] = role
            
    # Assign God Mode to spectators
    for p in room["players"]:
        if p.get("is_spectator"):
            room_assignments[p["username"]] = "God Mode"
            
    room["assignments"] = room_assignments
    room["state"] = "STARTED"
    room["mission_track"] = get_mission_track(num_entities)

    active_names = [p["username"] for p in room["players"] if not p.get("is_spectator")]

    # 3. Notify each player with their specific role info (including partner name if sharing role)
    partners = {pl["username"]: pl.get("partner") for pl in room["players"]}
    for p in room["players"]:
        username = p["username"]
        ws = p["ws"]
        if not ws: # Skip disconnected players
            continue
            
        role_info = get_role_info(username, room_assignments, partners)
        
        start_payload = json.dumps({
            "type": "game_start",
            "role_info": role_info,
            "mission_track": room["mission_track"],
            "players": active_names
        })
        try:
            await ws.send_text(start_payload)
        except Exception as e:
            logger.error(f"Error sending game start to {username}: {e}")

    # Broadcast room update to ensure state is synchronized
    await broadcast_room_update(room_id)

async def remove_player_from_room(username: str, room_id: str, ws: WebSocket):
    """Removes a player from a room, handling host transfer or room closure."""
    room = rooms.get(room_id)
    if not room:
        return

    # Check if leaving player is spectator
    is_spec = False
    for p in room["players"]:
        if p["username"] == username:
            is_spec = p.get("is_spectator", False)
            break

    # Remove player
    room["players"] = [p for p in room["players"] if p["username"] != username]
    manager.move_to_lobby(username, ws)

    if not room["players"]:
        # Room is empty, delete it
        del rooms[room_id]
        logger.info(f"Room {room_id} deleted because it is empty")
    else:
        # If host left, assign new host
        if room["host"] == username:
            room["host"] = room["players"][0]["username"]
            logger.info(f"Host transferred to {room['host']} in room {room_id}")
        
        # Only reset the game if the leaving player was an active (non-spectator) player
        if room["state"] == "STARTED" and not is_spec:
            room["state"] = "LOBBY"
            room["assignments"] = {}
            room["mission_track"] = []
            
        await broadcast_room_update(room_id)

    # Broadcast changes to lobby
    await manager.broadcast_lobby(get_rooms_summary())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    username = None
    room_id = None
    try:
        # Accept connection first
        await websocket.accept()
        manager.connect_socket(websocket)
        
        # Send initial lobby rooms list
        await websocket.send_text(json.dumps({
            "type": "lobby_update",
            "rooms": get_rooms_summary()
        }))

        # Main communication loop
        while True:
            data_str = await websocket.receive_text()
            data = json.loads(data_str)
            action = data.get("type")

            if action == "create_room":
                username = data.get("username", "").strip()
                if not username:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Name is required to host a room."
                    }))
                    continue
                
                room_name = data.get("room_name", f"{username}'s Castle").strip()
                if not room_name:
                    room_name = f"{username}'s Castle"
                
                manager.register_username(websocket, username)
                
                room_id = generate_room_id()
                rooms[room_id] = {
                    "name": room_name,
                    "host": username,
                    "players": [{"username": username, "ws": websocket, "is_spectator": data.get("spectator", False), "partner": None}],
                    "state": "LOBBY",
                    "password": data.get("password", "").strip() or None,
                    "toggles": {
                        "merlin": True,
                        "percival": True,
                        "morgana": True,
                        "mordred": False,
                        "oberon": False,
                        "lovers": False
                    },
                    "assignments": {},
                    "mission_track": []
                }
                
                manager.move_to_room(username, room_id, websocket)
                
                await websocket.send_text(json.dumps({
                    "type": "room_joined",
                    "room_id": room_id,
                    "is_host": True
                }))
                
                await broadcast_room_update(room_id)
                await manager.broadcast_lobby(get_rooms_summary())

            elif action == "join_room":
                username = data.get("username", "").strip()
                if not username:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Name is required to join a room."
                    }))
                    continue
                
                target_room_id = data.get("room_id", "").upper().strip()
                room = rooms.get(target_room_id)
                
                if not room:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Room not found."
                    }))
                    continue
                
                # Check for existing disconnected player reassociation
                existing_player = None
                for p in room["players"]:
                    if p["username"] == username:
                        existing_player = p
                        break
                        
                if existing_player:
                    # Close old websocket if still active to prevent leaks
                    old_ws = existing_player["ws"]
                    if old_ws and old_ws != websocket:
                        try:
                            await old_ws.close(code=4001, reason="Reassociated from new connection")
                        except Exception:
                            pass
                            
                    # Reassociate player connection
                    existing_player["ws"] = websocket
                    manager.register_username(websocket, username)
                    manager.move_to_room(username, target_room_id, websocket)
                    room_id = target_room_id
                    
                    await websocket.send_text(json.dumps({
                        "type": "room_joined",
                        "room_id": room_id,
                        "is_host": (room["host"] == username)
                    }))
                    
                    # If game has already started, immediately restore role details
                    if room["state"] == "STARTED":
                        partners = {pl["username"]: pl.get("partner") for pl in room["players"]}
                        role_info = get_role_info(username, room["assignments"], partners)
                        await websocket.send_text(json.dumps({
                            "type": "game_start",
                            "role_info": role_info,
                            "mission_track": room["mission_track"],
                            "players": [pl["username"] for pl in room["players"]]
                        }))
                        
                    await broadcast_room_update(room_id)
                    await manager.broadcast_lobby(get_rooms_summary())
                    continue

                # Password validation (bypass for existing reassociating player)
                room_pass = room.get("password")
                if room_pass:
                    client_pass = data.get("password", "").strip()
                    if client_pass != room_pass:
                        await websocket.send_text(json.dumps({
                            "type": "password_required",
                            "room_id": target_room_id,
                            "message": "Passcode required or incorrect passcode." if client_pass else "Passcode required."
                        }))
                        continue

                # Max 20 players limit only counts active (non-spectator) players.
                # Joining spectators are exempt, and active players are blocked only if active players >= 20.
                is_joining_as_spectator = data.get("spectator", False)
                active_players_count = len([p for p in room["players"] if not p.get("is_spectator")])
                
                if not is_joining_as_spectator and active_players_count >= 20:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Room is full (max 20 active players)."
                    }))
                    continue
                
                if room["state"] == "STARTED":
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Game has already started in that room."
                    }))
                    continue

                # Check for duplicate username in room
                if any(p["username"] == username for p in room["players"]):
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "A player with your name is already in this room."
                    }))
                    continue

                manager.register_username(websocket, username)

                # Join room
                room_id = target_room_id
                room["players"].append({
                    "username": username, 
                    "ws": websocket, 
                    "is_spectator": data.get("spectator", False),
                    "partner": None
                })
                manager.move_to_room(username, room_id, websocket)
                
                await websocket.send_text(json.dumps({
                    "type": "room_joined",
                    "room_id": room_id,
                    "is_host": False
                }))
                
                await broadcast_room_update(room_id)
                await manager.broadcast_lobby(get_rooms_summary())

            elif action == "request_partner":
                if not room_id:
                    continue
                room = rooms.get(room_id)
                if not room or room["state"] == "STARTED":
                    continue
                
                target_name = data.get("target")
                if not target_name or target_name == username:
                    continue
                
                # Check if both players exist, are active, and don't already have partners
                me_player = next((p for p in room["players"] if p["username"] == username), None)
                target_player = next((p for p in room["players"] if p["username"] == target_name), None)
                
                if me_player and target_player:
                    if not me_player.get("is_spectator") and not target_player.get("is_spectator"):
                        if me_player.get("partner") or target_player.get("partner"):
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "message": "Cannot request partner. One of you is already teamed up."
                            }))
                            continue
                        
                        # Find target's socket and forward request
                        target_ws = target_player["ws"]
                        if target_ws:
                            try:
                                await target_ws.send_text(json.dumps({
                                    "type": "partner_request",
                                    "requester": username
                                }))
                            except Exception as e:
                                logger.error(f"Error forwarding partner request from {username} to {target_name}: {e}")
                        else:
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "message": f"{target_name} is currently offline."
                            }))

            elif action == "accept_partner_request":
                if not room_id:
                    continue
                room = rooms.get(room_id)
                if not room or room["state"] == "STARTED":
                    continue
                
                requester_name = data.get("requester")
                if not requester_name or requester_name == username:
                    continue
                
                me_player = next((p for p in room["players"] if p["username"] == username), None)
                requester_player = next((p for p in room["players"] if p["username"] == requester_name), None)
                
                if me_player and requester_player:
                    if not me_player.get("is_spectator") and not requester_player.get("is_spectator"):
                        # If either already teamed up, send failure
                        if me_player.get("partner") or requester_player.get("partner"):
                            await websocket.send_text(json.dumps({
                                "type": "error",
                                "message": "Pact failed. One of you has already formed a team."
                            }))
                            continue
                        
                        # Pair them up
                        me_player["partner"] = requester_name
                        requester_player["partner"] = username
                        await broadcast_room_update(room_id)

            elif action == "decline_partner_request":
                if not room_id:
                    continue
                room = rooms.get(room_id)
                if not room or room["state"] == "STARTED":
                    continue
                
                requester_name = data.get("requester")
                if not requester_name or requester_name == username:
                    continue
                
                requester_player = next((p for p in room["players"] if p["username"] == requester_name), None)
                if requester_player and requester_player["ws"]:
                    try:
                        await requester_player["ws"].send_text(json.dumps({
                            "type": "partner_request_declined",
                            "target": username
                        }))
                    except Exception as e:
                        logger.error(f"Error sending decline notification to {requester_name}: {e}")

            elif action == "host_partner_up":
                if not room_id:
                    continue
                room = rooms.get(room_id)
                if not room or room["host"] != username or room["state"] == "STARTED":
                    continue
                
                p1_name = data.get("player1")
                p2_name = data.get("player2")
                if not p1_name or not p2_name or p1_name == p2_name:
                    continue
                
                p1 = next((p for p in room["players"] if p["username"] == p1_name), None)
                p2 = next((p for p in room["players"] if p["username"] == p2_name), None)
                
                if p1 and p2:
                    if not p1.get("is_spectator") and not p2.get("is_spectator"):
                        # Clear old partners first
                        for px in (p1, p2):
                            old_partner = px.get("partner")
                            if old_partner:
                                p_old = next((p for p in room["players"] if p["username"] == old_partner), None)
                                if p_old:
                                    p_old["partner"] = None
                                px["partner"] = None
                                
                        p1["partner"] = p2_name
                        p2["partner"] = p1_name
                        await broadcast_room_update(room_id)

            elif action == "leave_team":
                if not room_id:
                    continue
                room = rooms.get(room_id)
                if not room or room["state"] == "STARTED":
                    continue
                
                target_username = data.get("target")
                exec_username = target_username if (target_username and room["host"] == username) else username
                
                me_player = next((p for p in room["players"] if p["username"] == exec_username), None)
                if me_player:
                    partner_name = me_player.get("partner")
                    if partner_name:
                        partner_player = next((p for p in room["players"] if p["username"] == partner_name), None)
                        if partner_player:
                            partner_player["partner"] = None
                        me_player["partner"] = None
                        
                        await broadcast_room_update(room_id)

            elif action == "randomize_teams":
                if not room_id:
                    continue
                room = rooms.get(room_id)
                if not room or room["host"] != username or room["state"] == "STARTED":
                    continue
                
                # Get all active (non-spectator) players
                active_players = [p for p in room["players"] if not p.get("is_spectator")]
                
                # Reset partners for all active players
                for p in active_players:
                    p["partner"] = None
                    
                random.shuffle(active_players)
                
                # Pair them up
                for i in range(0, len(active_players) - 1, 2):
                    p1 = active_players[i]
                    p2 = active_players[i+1]
                    p1["partner"] = p2["username"]
                    p2["partner"] = p1["username"]
                    
                await broadcast_room_update(room_id)

            elif action == "leave_room":
                if room_id:
                    await remove_player_from_room(username, room_id, websocket)
                    room_id = None
                    await websocket.send_text(json.dumps({
                        "type": "left_room"
                    }))

            elif action == "update_roles":
                if not room_id:
                    continue
                room = rooms.get(room_id)
                if not room or room["host"] != username:
                    continue
                
                # Update settings
                room["toggles"] = data.get("toggles", {})
                await broadcast_room_update(room_id)

            elif action == "start_game":
                if not room_id:
                    continue
                room = rooms.get(room_id)
                if not room or room["host"] != username:
                    continue
                
                active_players_count = len([p for p in room["players"] if not p.get("is_spectator")])
                if active_players_count < 5:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": "Cannot start game. Need at least 5 active players."
                    }))
                    continue
                    
                entities = get_room_entities(room)
                num_entities = len(entities)
                if num_entities < 5 or num_entities > 10:
                    await websocket.send_text(json.dumps({
                        "type": "error",
                        "message": f"Cannot start game. Currently have {num_entities} teams/individuals playing. Must have between 5 and 10 total teams/individuals."
                    }))
                    continue
                
                await start_avalon_game(room_id)
                await manager.broadcast_lobby(get_rooms_summary())

            elif action == "reset_game":
                if not room_id:
                    continue
                room = rooms.get(room_id)
                if not room or room["host"] != username:
                    continue
                
                room["state"] = "LOBBY"
                room["assignments"] = {}
                room["mission_track"] = []
                
                await broadcast_room_update(room_id)
                await manager.broadcast_lobby(get_rooms_summary())

    except WebSocketDisconnect:
        logger.info(f"WebSocket connection closed for {username}")
        disc_username, disc_room_id = manager.disconnect(websocket)
        if disc_username and disc_room_id:
            # Mark player as disconnected instead of removing immediately
            room = rooms.get(disc_room_id)
            if room:
                for p in room["players"]:
                    if p["username"] == disc_username:
                        # CRITICAL: Only set to None if the disconnected socket is the active socket!
                        # This prevents old closed sockets from breaking a new re-associated connection.
                        if p["ws"] == websocket:
                            p["ws"] = None
                            await broadcast_room_update(disc_room_id)
                            asyncio.create_task(delayed_remove_player(disc_username, disc_room_id, websocket))
                        break

    except Exception as e:
        logger.error(f"Error in websocket loop: {e}", exc_info=True)
        disc_username, disc_room_id = manager.disconnect(websocket)
        if disc_username and disc_room_id:
            # Mark player as disconnected instead of removing immediately
            room = rooms.get(disc_room_id)
            if room:
                for p in room["players"]:
                    if p["username"] == disc_username:
                        # CRITICAL: Only set to None if the disconnected socket is the active socket!
                        if p["ws"] == websocket:
                            p["ws"] = None
                            await broadcast_room_update(disc_room_id)
                            asyncio.create_task(delayed_remove_player(disc_username, disc_room_id, websocket))
                        break

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
