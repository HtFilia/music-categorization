from pathlib import Path

GENRES = [
    "country", "electronic", "funk", "hip hop", "jazz", "latin",
    "metal", "polka", "pop", "punk", "reggae", "rock", "soul"
]

SUB_GENRES = { genre: [] for genre in GENRES}

TOP_GENRES_PATH = Path("dataset", "top_genres")
SUB_GENRES_PATH = Path("dataset", "sub_genres")
