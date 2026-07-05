import random
from typing import Dict, List, Set, Tuple, Optional

# Roles constants
MERLIN = "Merlin"
PERCIVAL = "Percival"
LOYAL_SERVANT = "Loyal Servant of Arthur"

ASSASSIN = "Assassin"
MORGANA = "Morgana"
MORDRED = "Mordred"
OBERON = "Oberon"
MINION = "Minion of Mordred"
LOVER = "Lover"

# Role descriptions
ROLE_DESCRIPTIONS = {
    MERLIN: "You are Merlin. You know the agents of Evil, but you must guide the Good players subtly. If Evil guesses your identity at the end, they win.",
    PERCIVAL: "You are Percival. You know who Merlin and Morgana are, but you do not know which is which. Protect Merlin!",
    LOYAL_SERVANT: "You are a Loyal Servant of Arthur. You have no special powers, but your vote and voice are crucial to the success of Good.",
    ASSASSIN: "You are the Assassin. At the end of the game, if Good has succeeded in 3 missions, you get one chance to guess Merlin's identity. If you are correct, Evil wins.",
    MORGANA: "You are Morgana. You appear to Percival as if you were Merlin, confusing their guidance. You also know the other Evil players.",
    MORDRED: "You are Mordred. You are the leader of Evil, and your identity is hidden from Merlin. You also know the other Evil players.",
    OBERON: "You are Oberon. You are an agent of Evil, but you do not know the other Evil players, nor do they know you. However, Merlin knows your identity.",
    MINION: "You are a Minion of Mordred. You are an agent of Evil. You know who the other Evil players are.",
    LOVER: "You are a Lover. You are on the side of Good. You know the other Lover, and you must protect them. Keep your affection hidden from Evil's gaze!",
    "God Mode": "You are a Spectator in God Mode. You can see the secret roles of all active players."
}

ROLE_ALIGNMENTS = {
    MERLIN: "Good",
    PERCIVAL: "Good",
    LOYAL_SERVANT: "Good",
    ASSASSIN: "Evil",
    MORGANA: "Evil",
    MORDRED: "Evil",
    OBERON: "Evil",
    MINION: "Evil",
    LOVER: "Good",
    "God Mode": "Neutral"
}

# Portraits file names (we will save these locally)
ROLE_PORTRAITS = {
    MERLIN: "merlin.png",
    PERCIVAL: "percival.png",
    LOYAL_SERVANT: "loyal_servant.png",
    ASSASSIN: "assassin.png",
    MORGANA: "morgana.png",
    MORDRED: "mordred.png",
    OBERON: "oberon.png",
    MINION: "minion.png",
    LOVER: "lovers.png",
    "God Mode": "god_mode.png"
}

def get_game_distribution(num_players: int) -> Tuple[int, int]:
    """Returns (num_good, num_evil) based on the number of players."""
    if num_players < 5:
        return (3, 2) # Fallback / minimum
    distributions = {
        5: (3, 2),
        6: (4, 2),
        7: (4, 3),
        8: (5, 3),
        9: (6, 3),
        10: (6, 4)
    }
    return distributions.get(num_players, (6, 4)) # Fallback to 10 players

def get_mission_track(num_players: int) -> List[Dict]:
    """
    Returns the mission sizes and rules for the given player count.
    Each mission has:
    - size: number of players required
    - fails_required: number of fail cards required (usually 1, but for 7+ players, the 4th mission requires 2 fails)
    """
    # 5 players: 2, 3, 2, 3, 3
    # 6 players: 2, 3, 4, 3, 4
    # 7 players: 2, 3, 3, 4*, 4
    # 8-10 players: 3, 4, 4, 5*, 5
    if num_players == 5:
        sizes = [2, 3, 2, 3, 3]
    elif num_players == 6:
        sizes = [2, 3, 4, 3, 4]
    elif num_players == 7:
        sizes = [2, 3, 3, 4, 4]
    else:
        sizes = [3, 4, 4, 5, 5]
        
    track = []
    for i, size in enumerate(sizes):
        # 4th mission (index 3) requires 2 fails if players >= 7
        fails_req = 1
        if i == 3 and num_players >= 7:
            fails_req = 2
        track.append({
            "mission_num": i + 1,
            "size": size,
            "fails_required": fails_req
        })
    return track

def assign_roles(player_names: List[str], toggles: Dict[str, bool]) -> Dict[str, str]:
    """
    Randomly assigns roles to players based on the toggles and player count.
    Returns a dictionary mapping player name to role.
    """
    num_players = len(player_names)
    num_good, num_evil = get_game_distribution(num_players)
    
    # 1. Construct Good Pool with random selection if special roles exceed slots count
    good_options = []
    if toggles.get("lovers", False):
        good_options.append(("Lovers", 2))
    if toggles.get("merlin", True):
        good_options.append(("Merlin", 1))
    if toggles.get("percival", True):
        good_options.append(("Percival", 1))
        
    random.shuffle(good_options)
    
    good_pool = []
    for role_name, cost in good_options:
        if len(good_pool) + cost <= num_good:
            if role_name == "Lovers":
                good_pool.extend([LOVER, LOVER])
            elif role_name == "Merlin":
                good_pool.append(MERLIN)
            elif role_name == "Percival":
                good_pool.append(PERCIVAL)
                
    # Fill remaining good slots with Loyal Servants
    while len(good_pool) < num_good:
        good_pool.append(LOYAL_SERVANT)
        
    # 2. Construct Evil Pool with random selection if special roles exceed slots count
    evil_options = []
    # Assassin is a special evil role
    evil_options.append(ASSASSIN)
    if toggles.get("morgana", True):
        evil_options.append(MORGANA)
    if toggles.get("mordred", True):
        evil_options.append(MORDRED)
    if toggles.get("oberon", True):
        evil_options.append(OBERON)
        
    # De-duplicate
    unique_evil_options = []
    for r in evil_options:
        if r not in unique_evil_options:
            unique_evil_options.append(r)
            
    random.shuffle(unique_evil_options)
    
    # Select the first num_evil special roles
    unique_evil_pool = unique_evil_options[:num_evil]
    
    # Fill remaining evil slots with Minions of Mordred
    while len(unique_evil_pool) < num_evil:
        unique_evil_pool.append(MINION)
        
    # Combine pools
    final_role_pool = good_pool + unique_evil_pool
    random.shuffle(final_role_pool)
    
    # Assign roles to players
    assignments = {}
    for i, name in enumerate(player_names):
        assignments[name] = final_role_pool[i]
        
    return assignments

def get_role_info(player_name: str, assignments: Dict[str, str], partners: Dict[str, Optional[str]]) -> Dict:
    """
    Returns the secret information visible to the player.
    """
    my_role = assignments.get(player_name)
    if not my_role:
        return {}
        
    alignment = ROLE_ALIGNMENTS[my_role]
    description = ROLE_DESCRIPTIONS[my_role]
    portrait = ROLE_PORTRAITS[my_role]
    
    # Information list
    info_lines = []
    
    # Helper to check if a role is evil
    def is_evil(role_name):
        return ROLE_ALIGNMENTS.get(role_name) == "Evil"
        
    # Helper to group a list of player names by partners
    def group_by_partners(names: List[str]) -> List[str]:
        grouped = []
        visited = set()
        for name in names:
            if name in visited:
                continue
            partner = partners.get(name)
            if partner and partner in names:
                grouped.append(f"{name} & {partner}")
                visited.add(name)
                visited.add(partner)
            else:
                grouped.append(name)
                visited.add(name)
        return grouped

    # Teammate check
    my_partner = partners.get(player_name)
    if my_partner:
        info_lines.append(f"Your Teammate is: {my_partner} (you share this role!).")
        
    # Gather other players
    other_players = {name: role for name, role in assignments.items() if name != player_name}
    
    if my_role == MERLIN:
        # Merlin sees all Evil players, EXCEPT Mordred
        evils_seen = []
        for name, role in other_players.items():
            if is_evil(role) and role != MORDRED:
                evils_seen.append(name)
        if evils_seen:
            # Shuffle names to hide order of entry
            random.shuffle(evils_seen)
            grouped_evils = group_by_partners(evils_seen)
            info_lines.append("Evil players:")
            for item in grouped_evils:
                info_lines.append(f"* {item}")
        else:
            info_lines.append("You see no Evil players (they might be hidden or Mordred is the only evil player).")
            
    elif my_role == PERCIVAL:
        # Percival sees Merlin and Morgana, but doesn't know who is who
        merlins_seen = []
        for name, role in other_players.items():
            if role in (MERLIN, MORGANA):
                merlins_seen.append(name)
        # Also check self just in case (though Percival can't be Merlin)
        if assignments.get(player_name) in (MERLIN, MORGANA):
            merlins_seen.append(player_name)
            
        if merlins_seen:
            random.shuffle(merlins_seen)
            info_lines.append(f"You see Merlin or Morgana in these players: {', '.join(merlins_seen)}")
        else:
            info_lines.append("You do not see Merlin or Morgana.")
            
    elif my_role in (ASSASSIN, MORGANA, MORDRED, MINION):
        # Evils see each other, EXCEPT Oberon
        other_evils = []
        for name, role in other_players.items():
            if is_evil(role) and role != OBERON:
                other_evils.append(name)
        if other_evils:
            random.shuffle(other_evils)
            grouped_evils = group_by_partners(other_evils)
            info_lines.append("Evil people:")
            for item in grouped_evils:
                info_lines.append(f"* {item}")
        else:
            info_lines.append("You are the only Evil player (excluding Oberon, if present).")
            
    elif my_role == OBERON:
        # Oberon sees no one
        info_lines.append("As Oberon, you do not know who the other Evil players are, and they do not know you.")
        
    elif my_role == LOYAL_SERVANT:
        # Loyal Servants see no one
        info_lines.append("You have no special information. Work with other Good players to figure out who to trust!")
        
    elif my_role == LOVER:
        # Lovers see each other
        other_lovers = []
        for name, role in other_players.items():
            if role == LOVER:
                other_lovers.append(name)
        if other_lovers:
            info_lines.append(f"Your beloved Lover is: {', '.join(other_lovers)}")
        else:
            info_lines.append("You are alone in your love (no other Lover was assigned).")
            
    elif my_role == "God Mode":
        # God Mode sees everyone's role
        info_lines.append("Active roles in this match:")
        for name, role in assignments.items():
            if role != "God Mode":
                info_lines.append(f"{name}: {role}")
        
    return {
        "role": my_role,
        "alignment": alignment,
        "description": description,
        "portrait": f"/static/images/{portrait}",
        "info": info_lines
    }
