import random
from typing import List, Tuple, Dict

# Standard 52-card deck
SUITS = ["H", "D", "C", "S"] # Hearts, Diamonds, Clubs, Spades
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]

def create_deck() -> List[str]:
    """Creates a standard 52-card deck."""
    return [rank + suit for suit in SUITS for rank in RANKS]

def shuffle_deck(deck: List[str]) -> List[str]:
    """Shuffles the deck."""
    random.shuffle(deck)
    return deck

def get_player_positions(
    players: List[Dict], dealer_seat: int
) -> Tuple[int, int, int]:
    """
    Determines the seat numbers for the small blind, big blind, and under-the-gun players.
    
    Args:
        players: A list of player dictionaries, each with a 'seat_number'.
        dealer_seat: The seat number of the current dealer.

    Returns:
        A tuple containing the seat numbers for (small_blind, big_blind, under_the_gun).
    """
    # Sort players by seat number to create a predictable turn order
    active_players = sorted([p for p in players if p.get('status') == 'playing'], key=lambda x: x['seat_number'])
    
    # Create a circular list of seat numbers for easier wrapping
    player_seats = [p['seat_number'] for p in active_players]
    
    # Find the index of the dealer in the active player list
    try:
        dealer_index = player_seats.index(dealer_seat)
    except ValueError:
        # If the dealer is not in the active list, start from the first active player
        dealer_index = 0

    # Handle heads-up (2 players) case separately for blinds
    if len(player_seats) == 2:
        sb_seat = player_seats[dealer_index]
        bb_seat = player_seats[(dealer_index + 1) % len(player_seats)]
        utg_seat = sb_seat # In heads-up, small blind/dealer acts first pre-flop
        return sb_seat, bb_seat, utg_seat

    # Standard case for 3+ players
    sb_index = (dealer_index + 1) % len(player_seats)
    bb_index = (dealer_index + 2) % len(player_seats)
    utg_index = (dealer_index + 3) % len(player_seats)
    
    sb_seat = player_seats[sb_index]
    bb_seat = player_seats[bb_index]
    utg_seat = player_seats[utg_index]

    return sb_seat, bb_seat, utg_seat
