import random
import string
from fastapi import APIRouter, HTTPException, Depends
from supabase import Client
from typing import List, Dict

from models import GameSettings, GameStateResponse, PlayerAction, GameCreationResponse, JoinResponse, ValidActionsResponse
from database import get_db
from game_logic import create_deck, shuffle_deck, get_player_positions

router = APIRouter()

# --- Helper Functions ---

def generate_game_code(length: int = 6) -> str:
    """Generates a unique 6-digit alphanumeric game code."""
    # For now, it's a simple random generator. In a production environment,
    # you'd want to ensure this code is unique in the database.
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))


def start_new_hand(game_id: str, players: List[Dict], settings: Dict, db: Client):
    """
    Initializes a new hand by shuffling, dealing, and posting blinds.
    """
    # 1. Shuffle deck and deal cards
    deck = shuffle_deck(create_deck())
    for player in players:
        # Deal two cards from the top of the deck
        cards_to_deal = [deck.pop(), deck.pop()]
        db.table("seats").update({"cards": cards_to_deal}).eq("id", player['id']).execute()

    # 2. Determine dealer position (for now, random on first hand)
    # A more robust solution would track the dealer button in the 'game_state' table
    # and move it to the next player each hand.
    dealer_seat = random.choice([p['seat_number'] for p in players])

    # 3. Determine blinds and first player to act using our game_logic function
    sb_seat, bb_seat, utg_seat = get_player_positions(players, dealer_seat)

    # 4. Post blinds and update chip counts
    small_blind_amount = settings['small_blind']
    big_blind_amount = settings['big_blind']

    # In a production app, this would be a single, atomic database transaction or RPC.
    # Here, we update each player and the pot sequentially.
    
    # Update small blind player
    sb_player = next((p for p in players if p['seat_number'] == sb_seat), None)
    db.table("seats").update({"chip_count": sb_player['chip_count'] - small_blind_amount}).eq("id", sb_player['id']).execute()
    
    # Update big blind player
    bb_player = next((p for p in players if p['seat_number'] == bb_seat), None)
    db.table("seats").update({"chip_count": bb_player['chip_count'] - big_blind_amount}).eq("id", bb_player['id']).execute()

    # 5. Update the main game_state
    pot_size = small_blind_amount + big_blind_amount
    
    # Find the user_id for the player who is UTG (Under the Gun)
    utg_player = next((p for p in players if p['seat_number'] == utg_seat), None)
    if not utg_player:
        # This should ideally never happen with 2+ players
        raise Exception("Could not determine the first player to act.")

    game_state_update = {
        "dealer_position": dealer_seat,
        "pot_size": pot_size,
        "current_bet": big_blind_amount,
        "community_cards": [],
        "current_player_turn": utg_player['user_id']
    }
    db.table("game_state").update(game_state_update).eq("game_id", game_id).execute()


# --- API Endpoints ---

@router.post("/games/create", status_code=201, response_model=GameCreationResponse)
def create_game(settings: GameSettings, db: Client = Depends(get_db)):
    """
    Creates a new poker game and sets the creator as the host.
    """
    # For this example, we'll use a placeholder for the authenticated user ID.
    # In a real app, this would come from a dependency that verifies a JWT.
    host_id = "a1b2c3d4-e5f6-7890-1234-567890abcdef" # Placeholder UUID

    if settings.big_blind < settings.small_blind:
        raise HTTPException(status_code=400, detail="Big blind must be greater than or equal to small blind.")

    # In a real app, you would also check user's bank_balance if use_real_chips is true.

    game_code = generate_game_code()

    try:
        # --- Database Transaction ---
        # 1. Insert into 'games' table
        game_data = {
            "game_code": game_code,
            "host_id": host_id,
            "settings": settings.dict()
        }
        game_res = db.table("games").insert(game_data).execute()
        game_id = game_res.data[0]['id']

        # 2. Insert into 'game_state' table
        db.table("game_state").insert({"game_id": game_id}).execute()

        # 3. Insert host into 'seats' table
        host_seat_data = {
            "game_id": game_id,
            "user_id": host_id,
            "seat_number": 1, # Host always starts at seat 1
            "chip_count": settings.buy_in,
            "status": "playing"
        }
        db.table("seats").insert(host_seat_data).execute()

        # If use_real_chips was true, you would update the host's profile.bank_balance here.

        return {"game_id": game_id, "game_code": game_code}

    except Exception as e:
        # If any part of the transaction fails, you might want to roll back the changes.
        # Supabase doesn't have built-in transactions in the Python client,
        # so this would be handled with PostgreSQL functions (RPC).
        print(f"Error creating game: {e}")
        raise HTTPException(status_code=500, detail="Could not create game.")


@router.post("/games/{game_code}/join", status_code=200, response_model=JoinResponse)
def join_game(game_code: str, db: Client = Depends(get_db)):
    """
    Allows a player to join an existing game. The server will assign the first
    available seat.
    """
    player_id = "f0e9d8c7-b6a5-4321-fedc-ba9876543210" # Placeholder user ID

    try:
        # Fetch the game by its code
        game_res = db.table("games").select("id, status, settings").eq("game_code", game_code).single().execute()
        if not game_res.data:
            raise HTTPException(status_code=404, detail="Game not found.")

        game = game_res.data
        game_id = game['id']
        max_players = game['settings']['max_players']

        if game['status'] != 'waiting':
            raise HTTPException(status_code=403, detail="Game is already in progress.")

        # --- Find first available seat ---
        seats_res = db.table("seats").select("user_id, seat_number").eq("game_id", game_id).execute()
        
        if len(seats_res.data) >= max_players:
            raise HTTPException(status_code=403, detail="Game is full.")

        # Check if player is already in the game
        if any(seat['user_id'] == player_id for seat in seats_res.data):
             raise HTTPException(status_code=400, detail="You are already in this game.")

        taken_seats = {seat['seat_number'] for seat in seats_res.data}
        
        available_seat = -1
        # Iterate from seat 1 up to the max number of players to find an open spot.
        for seat_num in range(1, max_players + 1):
            if seat_num not in taken_seats:
                available_seat = seat_num
                break
        
        if available_seat == -1:
            # This case should be rare if the 'game is full' check works, but it's a good safeguard.
            raise HTTPException(status_code=500, detail="Could not find an available seat, the game might be full.")

        # Add player to the 'seats' table
        player_seat_data = {
            "game_id": game_id,
            "user_id": player_id,
            "seat_number": available_seat,
            "chip_count": game['settings']['buy_in'],
            "status": "playing"
        }
        db.table("seats").insert(player_seat_data).execute()

        return {"seat_number": available_seat}

    except HTTPException as he:
        raise he # Re-raise known HTTP exceptions
    except Exception as e:
        print(f"Error joining game: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while trying to join the game.")


@router.post("/games/{game_code}/start", status_code=200)
def start_game(game_code: str, db: Client = Depends(get_db)):
    """
    Starts the game. Can only be initiated by the host.
    """
    host_id = "a1b2c3d4-e5f6-7890-1234-567890abcdef" # Placeholder host ID

    try:
        # 1. Fetch game and validate requester is the host
        game_res = db.table("games").select("id, host_id, status, settings").eq("game_code", game_code).single().execute()
        if not game_res.data:
            raise HTTPException(status_code=404, detail="Game not found.")
        
        game = game_res.data
        if game['host_id'] != host_id:
            raise HTTPException(status_code=403, detail="Only the host can start the game.")
        if game['status'] != 'waiting':
            raise HTTPException(status_code=400, detail="Game has already started or is finished.")

        # 2. Fetch players and validate there are enough to start
        seats_res = db.table("seats").select("id, user_id, seat_number, status, chip_count").eq("game_id", game['id']).execute()
        players = seats_res.data
        if len(players) < 2:
            raise HTTPException(status_code=400, detail="Cannot start a game with fewer than 2 players.")

        # 3. Update game status to 'in_progress'
        db.table("games").update({"status": "in_progress"}).eq("id", game['id']).execute()

        # 4. Start the first hand of the game
        start_new_hand(game['id'], players, game['settings'], db)

        return {"detail": "Game started successfully."}

    except HTTPException as he:
        raise he # Re-raise known HTTP exceptions
    except Exception as e:
        print(f"Error starting game: {e}")
        raise HTTPException(status_code=500, detail="An error occurred while starting the game.")


@router.get("/games/{game_code}", response_model=GameStateResponse)
def get_game_state(game_code: str, db: Client = Depends(get_db)):
    """
    Fetches the complete current state of a game for a player in the game.
    """
    # Verify user is a participant
    # (Database query to be added here)

    # Query and join the games, game_state, and seats tables.
    # (Detailed database logic to be added here)
    
    # Construct and return the GameStateResponse
    raise HTTPException(status_code=501, detail="Endpoint not fully implemented.")


@router.post("/games/{game_code}/action")
def perform_action(game_code: str, action: PlayerAction, db: Client = Depends(get_db)):
    """
    A player submits a game action (e.g., fold, check, bet).
    """
    # Validate it's the player's turn
    # Validate the action is legal
    # Update database tables (seats, game_state)
    # Determine if the betting round is over and proceed
    
    raise HTTPException(status_code=501, detail="Endpoint not fully implemented.")
