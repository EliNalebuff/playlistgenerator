import os
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# ======================================
# 0. Load Environment Variables
# ======================================
load_dotenv()

# ======================================
# 1. Configuration
# ======================================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = "http://localhost:8501"

# Initialize APIs
client = OpenAI(
    api_key=DEEPSEEK_API_KEY,
    base_url="https://api.deepseek.com/v1"
)
sp_oauth = SpotifyOAuth(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET,
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope="playlist-read-private playlist-modify-private playlist-modify-public"
)

# ======================================
# 2. Enhanced UI Components
# ======================================
def styled_login_button():
    auth_url = sp_oauth.get_authorize_url()
    st.markdown(
        f"""
        <style>
            .login-btn {{
                background: linear-gradient(135deg, #1DB954 0%, #1ED760 100%);
                color: white !important;
                padding: 14px 32px;
                border-radius: 30px;
                border: none;
                font-size: 18px;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                display: inline-block;
                text-align: center;
                width: fit-content;
                margin: 2rem auto;
            }}
            .login-btn:hover {{
                transform: translateY(-2px);
                box-shadow: 0 6px 8px rgba(0,0,0,0.15);
            }}
        </style>
        <a href="{auth_url}" class="login-btn">🎵 Connect with Spotify</a>
        """,
        unsafe_allow_html=True
    )

# ======================================
# 3. Authentication Handling
# ======================================
def authenticate_spotify():
    """Handles authentication and session management."""
    if "sp" not in st.session_state or "auth_token" not in st.session_state:
        if "code" in st.query_params:
            try:
                # Force fresh authentication
                code = st.query_params["code"]
                token_info = sp_oauth.get_access_token(code)
                if isinstance(token_info, dict) and "access_token" in token_info:
                    access_token = token_info["access_token"]
                else:
                    st.error("Failed to retrieve Spotify access token.")
                    return
                
                # Save to session state
                st.session_state.sp = spotipy.Spotify(auth=token_info["access_token"])
                st.session_state.auth_token = token_info["access_token"]

                # Clear query parameters
                del st.query_params["code"]
                st.rerun()
            except Exception as e:
                st.error(f"Authentication failed: {str(e)}")
    return st.session_state.get("sp", None)

# ======================================
# 4. Main App
# ======================================
def main():
    st.set_page_config(
        page_title="AI Playlist Generator",
        page_icon="🎧",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Add logout button
    col1, col2 = st.columns([4, 1])
    with col2:
        if "sp" in st.session_state:
            if st.button("🔒 Switch Account", help="Log out and use a different Spotify account"):
                # Clear session state and delete token cache
                st.session_state.clear()
                if os.path.exists(".cache"):
                    os.remove(".cache")
                st.rerun()

    # Authenticate Spotify
    sp = authenticate_spotify()
    if not sp:
        styled_login_button()
        return

    # Playlist selection
    with st.expander("🎵 STEP 1: Choose Your Source Playlist", expanded=True):
        try:
            playlists = sp.current_user_playlists()["items"]
            if not playlists:
                st.warning("No playlists found in your account!")
                return
                
            selected_playlist = st.selectbox(
                "Select a playlist:",
                options=playlists,
                format_func=lambda pl: f"{pl['name']} ({pl['tracks']['total']} tracks)"
            )

            col1, col2 = st.columns([1, 3])
            with col1:
                if selected_playlist['images']:
                    st.image(selected_playlist['images'][0]['url'], use_column_width=True)
            with col2:
                st.markdown(f"""
                    <h2>{selected_playlist['name']}</h2>
                    <p>by {selected_playlist['owner']['display_name']}</p>
                    <p>{selected_playlist['tracks']['total']} tracks</p>
                """, unsafe_allow_html=True)
        except Exception as e:
            st.error(f"Error loading playlists: {str(e)}")
            return

    # Playlist customization
    with st.expander("⚙️ STEP 2: Customize Your New Playlist", expanded=True):
        col1, col2 = st.columns(2)
        with col1:
            playlist_length = st.slider("Number of songs", 10, 50, 20)
            release_year = st.slider("Newer vs Older", 0, 100, 50, 
                                   help="Prefer newer or older releases")
            energy = st.slider("Harder vs Softer", 0, 100, 50, 
                             help="Higher energy (harder) or lower energy (softer)")
        with col2:
            playlist_name = st.text_input("Playlist name", f"AI Remix: {selected_playlist['name']}")
            tempo = st.slider("Faster vs Slower", 0, 100, 50, 
                            help="Faster tempo or slower tempo")
            mood = st.slider("Sadder vs Happier", 0, 100, 50, 
                           help="Sadder or happier mood")

    # Generate Playlist
    if st.button("✨ Generate Playlist", use_container_width=True):
        with st.spinner("🎶 Analyzing your music taste..."):
            try:
                # Get playlist tracks
                tracks = sp.playlist_tracks(selected_playlist['id'])['items']
                track_names = [t['track']['name'] for t in tracks if t['track']]

                # Get AI Recommendations
                recommendations = get_recommendations(
                    track_names, 
                    playlist_length,
                    release_year,
                    tempo,
                    energy,
                    mood
                )

                if not recommendations:
                    st.error("Failed to generate recommendations")
                    return

                # Create new playlist
                with st.spinner("📀 Creating your Spotify playlist..."):
                    playlist_url = create_spotify_playlist(sp, recommendations, playlist_name)

                st.success(f"🎉 Playlist created successfully! [Open in Spotify]({playlist_url})")
            except Exception as e:
                st.error(f"Generation failed: {str(e)}")

# ======================================
# 5. AI Recommendation Logic
# ======================================
def get_adjustment(value, feature_name, left_label, right_label):
    """Convert slider value to natural language adjustment"""
    if value == 50:
        return None
    direction = right_label if value > 50 else left_label
    intensity = abs(value - 50) / 50
    
    if intensity <= 0.2:
        adj = "slightly"
    elif intensity <= 0.5:
        adj = "moderately"
    else:
        adj = "significantly"
    
    return f"{adj} {direction} {feature_name}"

def get_recommendations(song_list, num_songs, release_year, tempo, energy, mood):
    try:
        # Generate adjustment descriptions
        adjustments = []
        features = [
            (release_year, "releases", "older", "newer"),
            (tempo, "tempo", "slower", "faster"),
            (energy, "energy", "softer", "harder"),
            (mood, "mood", "sadder", "happier")
        ]
        
        for value, feature, left, right in features:
            adjustment = get_adjustment(value, feature, left, right)
            if adjustment:
                adjustments.append(adjustment)

        # Build dynamic prompt
        prompt = f"""
        Recommend {num_songs} songs that you think I would like based on these tracks: {', '.join(song_list)}.
        {"Maintain similar style but with these adjustments: " + ", ".join(adjustments) + "." if adjustments else ""}
        Return only a numbered list with artist and title.
        Format as: 1. Artist - Song Title
        """

        # Get AI response
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "You are a music recommendation expert."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )

        return parse_recommendations(response.choices[0].message.content)
    except Exception as e:
        st.error(f"Recommendation failed: {str(e)}")
        return []

def parse_recommendations(text):
    songs = []
    for line in text.split('\n'):
        if line.strip() and '. ' in line:
            try:
                song = line.split('. ', 1)[1].strip()
                if '-' in song:
                    songs.append(song)
            except:
                continue
    return songs

def create_spotify_playlist(sp, song_list, playlist_name):
    try:
        track_ids = []
        for song in song_list:
            result = sp.search(q=song, type='track', limit=1)
            if result['tracks']['items']:
                track_ids.append(result['tracks']['items'][0]['id'])

        user_id = sp.me()['id']
        playlist = sp.user_playlist_create(user=user_id, name=playlist_name, public=True)

        if track_ids:
            sp.playlist_add_items(playlist['id'], track_ids)

        return playlist['external_urls']['spotify']
    except Exception as e:
        st.error(f"Playlist creation failed: {str(e)}")
        return None

# ======================================
# 6. Run App
# ======================================
if __name__ == "__main__":
    main()