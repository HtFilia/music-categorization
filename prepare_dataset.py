import argparse
from pathlib import Path
from const import GENRES, SUB_GENRES, TOP_GENRES_PATH, SUB_GENRES_PATH
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import csv
import time
from pytubefix import Search
import subprocess

def _make_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("-n", "--number", type=int, required=True)
    parser.add_argument("--max-retries", type=int, required=False, default=5)
    parser.add_argument("--all", "--all-genres", action="store_false", default=True)
    return parser

def setup_structure():
    TOP_GENRES_PATH.mkdir(parents=True, exist_ok=True)
    SUB_GENRES_PATH.mkdir(parents=True, exist_ok=True)
    for genre in GENRES:
        (TOP_GENRES_PATH / Path(genre)).mkdir(exist_ok=True)
        (SUB_GENRES_PATH / Path(genre)).mkdir(exist_ok=True)
        for subgenre in SUB_GENRES[genre]:
            (SUB_GENRES_PATH / Path(genre, subgenre)).mkdir(parents=True, exist_ok=True)

# Initialize Spotify API client
sp = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())

# Path to aggregated CSV file
CSV_FILE = TOP_GENRES_PATH / Path("songs.csv")

def get_songs_by_genre(genre, offset, max_calls=5):
    """
    Fetch a batch of songs by genre from Spotify with retry logic.

    Args:
        genre (str): The genre to search for.
        offset (int): Offset for pagination (used to fetch the next batch).
        max_calls (int): Maximum number of retries for API calls in case of errors.

    Returns:
        list: A list of dictionaries with 'artist_name' and 'song_name' keys.
    """
    results = []
    retries = 0

    while retries < max_calls:
        try:
            # Call Spotify API
            response = sp.search(q=f"genre:{genre}", type='track', limit=50, offset=offset)
            tracks = response.get('tracks', {}).get('items', [])
            
            if not tracks:
                print(f"No tracks found for genre: {genre} at offset: {offset}.")
                return results  # Return empty list if no tracks are found

            # Process each track
            for track in tracks:
                # Skip songs shorter than 30 seconds
                if track['duration_ms'] < 30 * 1000:
                    continue
                
                artist_name = track['artists'][0]['name']
                song_name = track['name']
                
                # Add to results
                results.append({'artist_name': artist_name, 'song_name': song_name})

                # Save to aggregated CSV
                save_to_csv(CSV_FILE, genre, song_name, artist_name)

            print(f"Successfully fetched {len(results)} songs for genre: {genre} at offset: {offset}.")
            return results  # Return the results if the API call is successful

        except Exception as e:
            retries += 1
            print(f"Error during API call (attempt {retries}/{max_calls}): {e}")
            time.sleep(1)  # Optional delay between retries

    print(f"Max retries reached for genre: {genre} at offset: {offset}. Stopping execution.")
    return results

def save_to_csv(file_path, genre, song_name, artist_name):
    """
    Save song details to a CSV file.

    Args:
        file_path (Path): Path to the CSV file.
        genre (str): Genre of the song.
        song_name (str): Name of the song.
        artist_name (str): Name of the artist.
    """
    file_exists = file_path.exists()
    with file_path.open(mode='a', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        if not file_exists:
            writer.writerow(['Genre', 'Song Name', 'Artist Name'])  # Write header
        writer.writerow([genre, song_name, artist_name])

def build(genres, songs_per_genre, max_api_calls):
    for genre in genres:
        print(f"Fetching songs for genre: {genre}")
        offset = 0
        total_songs_fetched = 0

        while total_songs_fetched < songs_per_genre:
            songs = get_songs_by_genre(genre, offset, max_api_calls)
            if not songs:
                print(f"No more songs found for genre: {genre} or max retries reached.")
                break  # Stop fetching if no songs are returned or retries are exhausted
            download_youtube_audio(songs, genre)
            total_songs_fetched += len(songs)
            offset += 50  # Increment offset for the next batch

            print(f"Total songs fetched for genre {genre}: {total_songs_fetched}/{songs_per_genre}")

        print(f"Finished fetching songs for genre: {genre}. Total songs fetched: {total_songs_fetched}")

def download_youtube_audio(songs, genre, output_path="dataset/top_genres"):
    """
    Download audio for a list of songs and save them as .wav files.

    Args:
        songs (list): List of dictionaries with 'song_name' and 'artist_name' keys.
        genre (str): The genre of the songs.
        output_path (str): Base directory for saving downloaded files.
    """
    # Ensure the output directory exists
    genre_path = Path(output_path) / genre
    genre_path.mkdir(parents=True, exist_ok=True)

    # Process each song
    for song in songs:
        song_name = song['song_name']
        artist_name = song['artist_name']
        sanitized_name = sanitize_filename(f"{song_name}-{artist_name}")
        wav_file_path = genre_path / f"{sanitized_name}.wav"

        # Skip if the file already exists
        if wav_file_path.exists():
            print(f"File already exists: {wav_file_path}")
            continue

        # Search and download from YouTube
        try:
            print(f"Searching YouTube for: {song_name} by {artist_name}")
            query = f"{song_name} {artist_name} audio"
            search = Search(query)
            videos = search.videos

            if not videos:
                print(f"No YouTube results found for: {song_name} by {artist_name}")
                continue

            yt = videos[0]
            audio_stream = yt.streams.get_audio_only()
            temp_file_path = genre_path / f"{sanitized_name}.m4a"

            # Download audio
            print(f"Downloading: {song_name} by {artist_name}")
            audio_stream.download(output_path=genre_path, filename=f"{sanitized_name}.m4a")

            # Convert to .wav using ffmpeg
            print(f"Converting to .wav: {wav_file_path}")
            convert_to_wav(temp_file_path, wav_file_path)

            # Remove the temporary .m4a file
            temp_file_path.unlink(missing_ok=True)
            print(f"Successfully saved: {wav_file_path}")

        except Exception as e:
            print(f"Error processing {song_name} by {artist_name}: {e}")

def sanitize_filename(filename):
    """
    Sanitize filenames by removing problematic characters.
    """
    return "".join(c if c.isalnum() or c in " -_" else "_" for c in filename)

def convert_to_wav(input_path, output_path):
    """
    Convert an audio file to .wav format using ffmpeg.

    Args:
        input_path (Path): Path to the input file.
        output_path (Path): Path to the output .wav file.
    """
    try:
        subprocess.run(
            ["ffmpeg", "-i", str(input_path), "-ar", "44100", "-ac", "2", str(output_path)],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
    except Exception as e:
        print(f"Error converting {input_path} to .wav: {e}")



def main():
    args = _make_parser().parse_args()
    build(GENRES, args.number, args.max_retries)

if __name__ == "__main__":
    main()