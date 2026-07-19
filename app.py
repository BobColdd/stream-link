from flask import Flask, render_template, request, redirect, url_for, jsonify
import requests
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'dev-secret-key')

# Backend API URL
BACKEND_URL = os.getenv('BACKEND_URL', 'https://colddfootball.neckhards.org')

# Competition mapping for display
COMPETITIONS = {
    'WC': {'name': 'FIFA World Cup', 'icon': '🌍'},
    'CL': {'name': 'Champions League', 'icon': '🏆'},
    'PL': {'name': 'Premier League', 'icon': '🏴󠁧󠁢󠁥󠁮󠁧󠁿'},
    'BL1': {'name': 'Bundesliga', 'icon': '🇩🇪'},
    'SA': {'name': 'Serie A', 'icon': '🇮🇹'},
    'PD': {'name': 'La Liga', 'icon': '🇪🇸'},
    'FL1': {'name': 'Ligue 1', 'icon': '🇫🇷'},
    'DED': {'name': 'Eredivisie', 'icon': '🇳🇱'},
    'ELC': {'name': 'Championship', 'icon': '🏴󠁧󠁢󠁥󠁮󠁧󠁿'},
    'CLI': {'name': 'Copa Libertadores', 'icon': '🏆'}
}

def fetch_from_backend(endpoint):
    """Fetch data from the backend API."""
    try:
        url = f"{BACKEND_URL}{endpoint}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching from backend: {e}")
        return None

@app.route('/')
def index():
    """Home page - List all competitions."""
    # Fetch competitions from backend
    data = fetch_from_backend('/api/competitions')
    
    competitions = []
    if data and data.get('success'):
        competitions = data.get('data', [])
    
    # Add icons to competitions
    for comp in competitions:
        code = comp.get('code')
        if code in COMPETITIONS:
            comp['icon'] = COMPETITIONS[code]['icon']
        else:
            comp['icon'] = '⚽'
    
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
        except:
            current_date = datetime.now()
    else:
        current_date = datetime.now()
    
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
    
    # Format matches for display
    for match in matches:
        match['kickoff_display'] = match.get('kickoff', 'TBD')
    
    # Get previous and next dates
    prev_date = current_date - timedelta(days=1)
    next_date = current_date + timedelta(days=1)
    
    # Get competition info
    comp_info = COMPETITIONS.get(code, {'name': code, 'icon': '⚽'})
    
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
    data = fetch_from_backend('/api/matches/live')
    
    live_matches = []
    count = 0
    
    if data and data.get('success'):
        live_data = data.get('data', {})
        live_matches = live_data.get('matches', [])
        count = live_data.get('count', 0)
    
    return render_template(
        'live.html',
        live_matches=live_matches,
        count=count
    )

@app.route('/stream/<match_id>')
def stream_player(match_id):
    """Stream player page."""
    # Fetch streams for this match
    data = fetch_from_backend(f'/api/m3u8/{match_id}')
    
    streams = []
    match_info = {'home_team': 'Home', 'away_team': 'Away'}
    
    if data and data.get('success'):
        stream_data = data.get('data', {})
        streams = stream_data.get('streams', [])
    
    return render_template(
        'stream.html',
        match_id=match_id,
        streams=streams,
        home_team=match_info.get('home_team', 'Home'),
        away_team=match_info.get('away_team', 'Away')
    )

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.getenv('PORT', 5001))
    app.run(host='0.0.0.0', port=port, debug=True)
