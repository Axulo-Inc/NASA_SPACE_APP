from flask import Flask, request, render_template_string, jsonify, send_file
import requests
import io, csv, datetime
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

app = Flask(__name__)

# Simple HTML templates embedded to keep this single-file
INDEX_HTML = """<!doctype html>
<html>
  <head>
    <title>ClimaGuard AI — MVP</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
      body { font-family: Arial, sans-serif; margin: 2rem; max-width: 900px; }
      label { display:block; margin-top:0.8rem; }
      input, select { width:100%; padding:0.5rem; margin-top:0.3rem; }
      button { margin-top:1rem; padding:0.6rem 1rem; background:#007cba; color:white; border:none; border-radius:4px; cursor:pointer; }
      button:hover { background:#005a87; }
      .result { margin-top:1.2rem; padding:1.5rem; border-radius:8px; background:#f8f9fa; border-left:4px solid #007cba; }
      .risk { font-weight:700; font-size:1.2rem; }
      .safe { color: green; }
      .caution { color: orange; }
      .high-risk { color: red; }
      .plot { max-width:100%; height:auto; margin:1rem 0; }
    </style>
  </head>
  <body>
    <h1>🌍 ClimaGuard AI — MVP</h1>
    <p>Enter a location and date to get historical probability-based weather risk analysis powered by NASA data.</p>
    
    <form method="post" action="/query">
      <label><strong>Location</strong> (city name OR "latitude,longitude")</label>
      <input name="location" placeholder="e.g. Johannesburg OR -26.2041,28.0473" required>
      
      <label><strong>Date</strong> (YYYY-MM-DD)</label>
      <input name="date" type="date" required>
      
      <label><strong>Activity Type</strong> (optional)</label>
      <select name="activity">
        <option value="outdoor_event">🎪 Outdoor Event</option>
        <option value="hiking">🥾 Hiking</option>
        <option value="fishing">🎣 Fishing</option>
        <option value="farming">🌾 Farming</option>
        <option value="beach">🏖️ Beach Day</option>
        <option value="other">📅 Other</option>
      </select>
      
      <button type="submit">🔍 Check Weather Risk</button>
    </form>

    {% if result %}
    <div class="result">
      <h2>📊 Weather Analysis for {{result.location_display}} on {{result.query_date}}</h2>
      
      <p class="risk {{ 'safe' if 'Safe' in result.recommendation else 'caution' if 'Caution' in result.recommendation else 'high-risk' }}">
        🎯 Recommendation: {{result.recommendation}}
      </p>
      
      <h3>📈 Historical Statistics (2000-2020)</h3>
      <ul>
        <li>🌧️ Chance of Rain: <strong>{{result.rain_prob}}%</strong></li>
        <li>🌡️ Average Temperature: <strong>{{result.temp_mean}}°C</strong></li>
        <li>💨 Average Wind Speed: <strong>{{result.wind_mean}} m/s</strong></li>
        <li>💧 Average Humidity: <strong>{{result.rh_mean}}%</strong></li>
      </ul>
      
      <p><strong>📝 Interpretation:</strong> {{result.interpretation}}</p>
      
      <img class="plot" src="{{url_for('static', filename='plot.png')}}?t={{result.timestamp}}" alt="Weather Probability Chart">
      
      <div style="margin-top:1rem;">
        <p><strong>📥 Download Data:</strong></p>
        <a href="/export?lat={{result.lat}}&lon={{result.lon}}&date={{result.query_date}}" style="background:#28a745; color:white; padding:0.5rem 1rem; text-decoration:none; border-radius:4px; margin-right:0.5rem;">📄 Download CSV</a>
        <a href="/export?lat={{result.lat}}&lon={{result.lon}}&date={{result.query_date}}&format=json" style="background:#17a2b8; color:white; padding:0.5rem 1rem; text-decoration:none; border-radius:4px;">🔷 Download JSON</a>
      </div>
    </div>
    {% endif %}

    {% if result and result.error %}
    <div class="result" style="border-left-color:#dc3545;">
      <h3>❌ Error</h3>
      <p>{{result.error}}</p>
    </div>
    {% endif %}

    <hr>
    <p><small>💡 <strong>Demo Tips:</strong> Use coordinates for best results: Johannesburg (-26.2041,28.0473), Cape Town (-33.9249,18.4241), Nairobi (-1.2921,36.8219)</small></p>
    <p><small>⚡ Powered by NASA POWER API • ClimaGuard AI MVP</small></p>
  </body>
</html>
"""

def geocode_location(location_str):
    location_str = location_str.strip()
    
    # First, check if it's already in lat,lon format
    if ',' in location_str:
        try:
            parts = location_str.split(',')
            lat = float(parts[0].strip())
            lon = float(parts[1].strip())
            return lat, lon, f"{lat:.4f},{lon:.4f}"
        except:
            pass
    
    # For city names, add country hints for better accuracy
    country_hints = {
        'johannesburg': 'South Africa',
        'cape town': 'South Africa', 
        'nairobi': 'Kenya',
        'pretoria': 'South Africa',
        'durban': 'South Africa'
    }
    
    search_query = location_str
    location_lower = location_str.lower()
    if location_lower in country_hints:
        search_query = f"{location_str}, {country_hints[location_lower]}"
    
    try:
        r = requests.get("https://nominatim.openstreetmap.org/search", 
                        params={
                            "q": search_query, 
                            "format": "json", 
                            "limit": 1,
                            "addressdetails": 1
                        }, 
                        headers={"User-Agent": "ClimaGuard-MVP"})
        r.raise_for_status()
        data = r.json()
        if data:
            lat = float(data[0]['lat'])
            lon = float(data[0]['lon'])
            display = data[0].get('display_name', location_str)
            return lat, lon, display
    except Exception as e:
        print("Geocode failed:", e)
    
    return None, None, location_str

def fetch_nasa_power(lat, lon, start_year=2000, end_year=2020):
    base = "https://power.larc.nasa.gov/api/temporal/daily/point"
    params = {
        "start": start_year,
        "end": end_year,
        "latitude": lat,
        "longitude": lon,
        "community": "AG",
        "parameters": "T2M,PRECTOT,WS10M,RH2M",
        "format": "JSON"
    }
    r = requests.get(base, params=params, timeout=30)
    r.raise_for_status()
    return r.json()

def analyze_histories(nasa_json, query_month_day):
    params = nasa_json.get('properties', {}).get('parameter', {})
    
    t2m = params.get('T2M', {})
    prectot = params.get('PRECTOT', {})
    ws10m = params.get('WS10M', {})
    rh2m = params.get('RH2M', {})

    temps = []; rains = []; winds = []; rhs = []
    
    for date_str, v in t2m.items():
        if date_str[4:] == query_month_day:
            temps.append(v)
    for date_str, v in prectot.items():
        if date_str[4:] == query_month_day:
            rains.append(v)
    for date_str, v in ws10m.items():
        if date_str[4:] == query_month_day:
            winds.append(v)
    for date_str, v in rh2m.items():
        if date_str[4:] == query_month_day:
            rhs.append(v)

    import statistics
    def mean_or_none(ls):
        return round(float(statistics.mean(ls)), 2) if ls else 0.0
    
    temp_mean = mean_or_none(temps)
    wind_mean = mean_or_none(winds)
    rh_mean = mean_or_none(rhs)
    
    rain_prob = 0
    if rains:
        rain_count = sum(1 for r in rains if float(r) > 0.0)
        rain_prob = round(100.0 * rain_count / len(rains), 1)

    recommendation = "✅ Safe - Conditions historically favorable"
    reasons = []
    
    if temp_mean >= 32:
        reasons.append("High historical mean temperature (Very Hot)")
    if rain_prob >= 60:
        reasons.append("High historical probability of rain")
    elif rain_prob >= 40:
        reasons.append("Moderate historical probability of rain")
    
    if wind_mean >= 8:
        reasons.append("Elevated wind speeds historically")
    if rh_mean >= 80:
        reasons.append("High humidity historically")

    if reasons:
        if rain_prob >= 60 or temp_mean >= 35:
            recommendation = "❌ High Risk - " + "; ".join(reasons)
        else:
            recommendation = "⚠️ Caution - " + "; ".join(reasons)

    interpretation = " ; ".join(reasons) if reasons else "Historical data shows generally favorable conditions for this date."
    
    return {
        "temp_mean": temp_mean,
        "wind_mean": wind_mean,
        "rh_mean": rh_mean,
        "rain_prob": rain_prob,
        "recommendation": recommendation,
        "interpretation": interpretation
    }

def save_plot(stats, out_path):
    labels = ['Rain %', 'Temp (°C)', 'Wind (m/s)', 'Humidity %']
    values = [
        stats.get('rain_prob', 0),
        stats.get('temp_mean', 0),
        stats.get('wind_mean', 0),
        stats.get('rh_mean', 0)
    ]
    
    colors = ['#3498db', '#e74c3c', '#f39c12', '#2ecc71']
    
    plt.clf()
    plt.figure(figsize=(10, 5))
    bars = plt.bar(labels, values, color=colors, alpha=0.8)
    plt.ylabel('Values')
    plt.title('Historical Weather Statistics')
    plt.ylim(0, max(values) * 1.2 if values else 100)
    
    for bar, value in zip(bars, values):
        plt.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.5, 
                f'{value}', ha='center', va='bottom', fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(out_path, dpi=100, bbox_inches='tight')
    plt.close()

@app.route('/')
def index():
    return render_template_string(INDEX_HTML)

@app.route('/query', methods=['POST'])
def query():
    location = request.form.get('location')
    date_str = request.form.get('date')
    activity = request.form.get('activity', 'other')
    
    lat, lon, display = geocode_location(location)
    if lat is None:
        return render_template_string(INDEX_HTML, result={"error": "Could not geocode location. Please try format: 'City Name' or 'latitude,longitude'"})

    try:
        nasa = fetch_nasa_power(lat, lon)
    except Exception as e:
        return render_template_string(INDEX_HTML, result={"error": f"Failed to fetch NASA data: {str(e)}"})

    try:
        qdate = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        month_day = f"{qdate.month:02d}{qdate.day:02d}"
    except:
        return render_template_string(INDEX_HTML, result={"error": "Invalid date format. Use YYYY-MM-DD"})

    stats = analyze_histories(nasa, month_day)
    stats.update({
        "lat": lat, 
        "lon": lon, 
        "location_display": display, 
        "query_date": date_str,
        "timestamp": datetime.datetime.now().timestamp()
    })

    save_plot(stats, "static/plot.png")
    return render_template_string(INDEX_HTML, result=stats)

@app.route('/export', methods=['GET'])
def export():
    lat = request.args.get('lat')
    lon = request.args.get('lon')
    date_str = request.args.get('date')
    out_format = request.args.get('format', 'csv')
    
    if not (lat and lon and date_str):
        return "Missing parameters lat, lon, date", 400
    
    try:
        latf = float(lat); lonf = float(lon)
    except:
        return "Invalid lat/lon", 400
    
    try:
        nasa = fetch_nasa_power(latf, lonf)
    except Exception as e:
        return f"Failed to fetch NASA data: {e}", 500
    
    qdate = datetime.datetime.strptime(date_str, "%Y-%m-%d")
    month_day = f"{qdate.month:02d}{qdate.day:02d}"
    params = nasa.get('properties', {}).get('parameter', {})
    
    rows = []
    years = []
    for date_key, val in params.get('T2M', {}).items():
        if date_key[4:] == month_day:
            year = date_key[:4]
            years.append(year)
    
    years = sorted(list(set(years)))
    for y in years:
        row = {"year": y}
        for pname in ['T2M', 'PRECTOT', 'WS10M', 'RH2M']:
            row[pname] = params.get(pname, {}).get(y + month_day, None)
        rows.append(row)

    if out_format == 'json':
        return jsonify(rows)
    
    si = io.StringIO()
    writer = csv.DictWriter(si, fieldnames=["year", "T2M", "PRECTOT", "WS10M", "RH2M"])
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    
    mem = io.BytesIO()
    mem.write(si.getvalue().encode('utf-8'))
    mem.seek(0)
    return send_file(mem, mimetype='text/csv', download_name='climaguard_export.csv', as_attachment=True)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=True)
