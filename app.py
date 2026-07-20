from flask import Flask, render_template, request, redirect, url_for, jsonify
import requests
from datetime import datetime, timedelta
import os
import logging
from dotenv import load_dotenv
import time
from functools import lru_cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24).hex())

# Configuration
BACKEND_URL = os.getenv('BACKEND_URL', 'https://colddfootball.neckhards.org')
PORT = int(os.getenv('PORT', 5000))  # Render uses PORT env var
DEBUG = os.getenv('DEBUG', 'False').lower() == 'true'
CACHE_DURATION = int(os.getenv('CACHE_DURATION', 30))

# Configure requests session with retry logic and proper headers
def get_session():
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    # Add headers to avoid 403
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
    })
    return session

session = get_session()

# In-memory cache
cache = {}

def get_cached(key, cache_duration=CACHE_DURATION):
    """Get cached data if not expired."""
    if key in cache:
        data, timestamp = cache[key]
        if time.time() - timestamp < cache_duration:
            return data
    return None

def set_cache(key, data):
    """Set cached data with timestamp."""
    cache[key] = (data, time.time())

# Competition mapping for display
COMPETITIONS = {
    'WC': {'name': 'FIFA World Cup', 'icon': '🌍', 'color': '#1a73e8'},
    'CL': {'name': 'Champions League', 'icon': '🏆', 'color': '#003399'},
    'PL': {'name': 'Premier League', 'icon': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'color': '#37003c'},
    'BL1': {'name': 'Bundesliga', 'icon': '🇩🇪', 'color': '#e2001a'},
    'SA': {'name': 'Serie A', 'icon': '🇮🇹', 'color': '#0b4d8e'},
    'PD': {'name': 'La Liga', 'icon': '🇪🇸', 'color': '#e2001a'},
    'FL1': {'name': 'Ligue 1', 'icon': '🇫🇷', 'color': '#003395'},
    'DED': {'name': 'Eredivisie', 'icon': '🇳🇱', 'color': '#f2a800'},
    'ELC': {'name': 'Championship', 'icon': '🏴󠁧󠁢󠁥󠁮󠁧󠁿', 'color': '#0053a0'},
    'CLI': {'name': 'Copa Libertadores', 'icon': '🏆', 'color': '#f5a623'}
}

def fetch_from_backend(endpoint, use_cache=True):
    """Fetch data from the backend API with caching."""
    cache_key = f"backend_{endpoint}"
    
    # Check cache
    if use_cache:
        cached_data = get_cached(cache_key)
        if cached_data:
            logger.info(f"Cache hit for {endpoint}")
            return cached_data
    
    try:
        url = f"{BACKEND_URL}{endpoint}"
        logger.info(f"Fetching from backend: {url}")
        
        response = session.get(url, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        
        # Cache the response
        if use_cache and data:
            set_cache(cache_key, data)
        
        return data
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching from backend: {endpoint}")
        return None
    except requests.exceptions.ConnectionError:
        logger.error(f"Connection error fetching from backend: {endpoint}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching from backend: {e}")
        return None

@app.route('/')
def index():
    """Home page - List all competitions."""
    cache_key = "competitions_list"
    
    # Try cache first
    competitions = get_cached(cache_key, cache_duration=300)  # 5 minutes
    
    if competitions is None:
        # Fetch from backend
        data = fetch_from_backend('/api/competitions')
        
        competitions = []
        if data and data.get('success'):
            competitions = data.get('data', [])
        
        # Cache for longer (5 minutes)
        set_cache(cache_key, competitions)
    
    # Add icons to competitions
    for comp in competitions:
        code = comp.get('code')
        if code in COMPETITIONS:
            comp['icon'] = COMPETITIONS[code]['icon']
            comp['color'] = COMPETITIONS[code]['color']
        else:
            comp['icon'] = '⚽'
            comp['color'] = '#666'
    
    today = datetime.now()
    
    return render_template(
        'index.html',
        competitions=competitions,
        today=today,
        COMPETITIONS=COMPETITIONS
    )

@app.route('/competition/<code>')
def competition_matches(code):
    """Show matches for a specific competition."""
    # Get date from query params
    date_str = request.args.get('date')
    
    if date_str:
        try:
            current_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            current_date = datetime.now()
    else:
        current_date = datetime.now()
    
    # Build cache key
    cache_key = f"matches_{code}_{current_date.strftime('%Y-%m-%d')}"
    
    # Try cache
    cached_data = get_cached(cache_key)
    
    if cached_data:
        matches, competition_name, source = cached_data
    else:
        # Fetch matches from backend
        endpoint = f"/api/matches/{code}"
        if date_str:
            endpoint += f"?date={date_str}"
        
        data = fetch_from_backend(endpoint)
        
        matches = []
        competition_name = code
        source = 'Unknown'
        
        if data and data.get('success'):
            match_data = data.get('data', {})
            matches = match_data.get('matches', [])
            competition_name = match_data.get('competition', {}).get('name', code)
            source = match_data.get('source', 'Unknown')
        
        # Cache for 30 seconds (matches update frequently)
        set_cache(cache_key, (matches, competition_name, source))
    
    # Format matches for display
    for match in matches:
        match['kickoff_display'] = match.get('kickoff', 'TBD')
    
    # Get previous and next dates
    prev_date = current_date - timedelta(days=1)
    next_date = current_date + timedelta(days=1)
    
    # Get competition info
    comp_info = COMPETITIONS.get(code, {'name': code, 'icon': '⚽', 'color': '#666'})
    
    return render_template(
        'matches.html',
        code=code,
        competition_name=competition_name,
        comp_info=comp_info,
        matches=matches,
        current_date=current_date,
        prev_date=prev_date,
        next_date=next_date,
        source=source,
        date_str=current_date.strftime('%Y-%m-%d')
    )

@app.route('/live')
def live_matches():
    """Show all live matches."""
    cache_key = "live_matches"
    
    # Cache for 15 seconds (live updates)
    cached_data = get_cached(cache_key, cache_duration=15)
    
    if cached_data:
        live_matches, count = cached_data
    else:
        data = fetch_from_backend('/api/matches/live')
        
        live_matches = []
        count = 0
        
        if data and data.get('success'):
            live_data = data.get('data', {})
            live_matches = live_data.get('matches', [])
            count = live_data.get('count', 0)
        
        set_cache(cache_key, (live_matches, count))
    
    return render_template(
        'live.html',
        live_matches=live_matches,
        count=count
    )

@app.route('/stream/<match_id>')
def stream_player(match_id):
    """Stream player page."""
    cache_key = f"streams_{match_id}"
    
    # Cache for 1 minute
    cached_data = get_cached(cache_key, cache_duration=60)
    
    if cached_data:
        streams = cached_data
    else:
        data = fetch_from_backend(f'/api/m3u8/{match_id}')
        
        streams = []
        
        if data and data.get('success'):
            stream_data = data.get('data', {})
            streams = stream_data.get('streams', [])
        
        set_cache(cache_key, streams)
    
    return render_template(
        'stream.html',
        match_id=match_id,
        streams=streams,
        home_team='Home',
        away_team='Away'
    )

@app.route('/health')
def health():
    """Health check endpoint for Render."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'backend': BACKEND_URL,
        'cache_size': len(cache),
        'port': PORT
    })

@app.route('/api/competitions')
def api_competitions_proxy():
    """Proxy endpoint for competitions."""
    data = fetch_from_backend('/api/competitions')
    if data:
        return jsonify(data)
    return jsonify({'success': False, 'error': 'Failed to fetch competitions'}), 500

@app.route('/api/matches/<code>')
def api_matches_proxy(code):
    """Proxy endpoint for matches."""
    date = request.args.get('date')
    endpoint = f"/api/matches/{code}"
    if date:
        endpoint += f"?date={date}"
    
    data = fetch_from_backend(endpoint)
    if data:
        return jsonify(data)
    return jsonify({'success': False, 'error': 'Failed to fetch matches'}), 500

@app.route('/api/matches/live')
def api_live_matches_proxy():
    """Proxy endpoint for live matches."""
    data = fetch_from_backend('/api/matches/live')
    if data:
        return jsonify(data)
    return jsonify({'success': False, 'error': 'Failed to fetch live matches'}), 500

@app.route('/api/m3u8/<match_id>')
def api_m3u8_proxy(match_id):
    """Proxy endpoint for m3u8 streams."""
    data = fetch_from_backend(f'/api/m3u8/{match_id}')
    if data:
        return jsonify(data)
    return jsonify({'success': False, 'error': 'Failed to fetch streams'}), 500

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors."""
    return render_template('404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return render_template('500.html'), 500

if __name__ == '__main__':
    # Run on the port Render provides
    port = int(os.getenv('PORT', 5000))
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=DEBUG)
