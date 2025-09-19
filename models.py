from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from uuid import UUID

# This model represents the structure of the 'settings' JSONB object in the 'games' table.
class GameSettings(BaseModel):
    game_name: str = Field(..., max_length=50)
    buy_in: int = Field(..., gt=0)
    small_blind: int = Field(..., gt=0)
    big_blind: int = Field(..., gt=0)
    use_real_chips: bool = False
    max_players: int = Field(..., ge=2, le=8)

# Model for a player submitting an action during a game.
class PlayerAction(BaseModel):
    action: Literal["fold", "check", "call", "bet", "raise"]
    amount: Optional[int] = Field(None, gt=0)


# --- Response Models ---

# Model for the response when a player successfully joins a game.
class JoinResponse(BaseModel):
    seat_number: int

# Model for the valid actions a player can take.
class ValidActionsResponse(BaseModel):
    actions: List[Literal["fold", "check", "call", "bet", "raise"]]
    call_amount: Optional[int] = None
    min_raise_amount: Optional[int] = None

# Corresponds to a row in the 'seats' table, joined with 'profiles'
class Player(BaseModel):
    user_id: UUID
    display_name: str
    seat_number: int
    chip_count: int
    status: Literal["playing", "folded", "all_in", "sitting_out"]
    is_turn: bool
    cards: Optional[List[str]] = None # e.g., ["AS", "KH"]

# A composite view of the 'games', 'game_state', and 'seats' tables for the client.
class GameStateResponse(BaseModel):
    game_id: UUID
    game_code: str
    status: Literal["waiting", "in_progress", "paused", "finished"]
    host_id: UUID
    players: List[Player]
    community_cards: List[str]
    pot_size: int
    current_bet: int
    current_player_turn: Optional[UUID]
    dealer_position: Optional[int]

class GameCreationResponse(BaseModel):
    game_id: UUID
    game_code: str
