from flask import Flask, request, render_template, redirect, url_for, jsonify, flash, send_from_directory
import requests
import os
import json
from datetime import datetime
import threading
import uuid
from PIL import Image
import io

app = Flask(__name__)
app.secret_key = 'your-secret-key-here-change-in-production'

# Konfigurasi Telegram
TELEGRAM_TOKEN = "8775476123:AAH7hvaKY3F9grmvAVwn9YLvPoUa92oC97w"
CHAT_ID = "576495165"

# Folder untuk menyimpan foto dan data
UPLOAD_FOLDER = "uploads"
DATA_FILE = "data.json"

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {"pembelian": [], "kegiatan": []}
    return {"pembelian": [], "kegiatan": []}

def save_data(data):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def generate_unique_code():
    return uuid.uuid4().hex[:8].upper()

def compress_image(image_path, max_size_mb=1.0, max_width=1280):
    try:
        img = Image.open(image_path)
        if img.mode in ('RGBA', 'P'):
            img = img.convert('RGB')
        if img.width > max_width:
            ratio = max_width / float(img.width)
            new_height = int(float(img.height) * ratio)
            img = img.resize((max_width, new_height), Image.Resampling.LANCZOS)
        
        buffer = io.BytesIO()
        img.save(buffer, format="JPEG", quality=85, optimize=True)
        size_kb = len(buffer.getvalue()) / 1024
        
        if size_kb > (max_size_mb * 1024):
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=70, optimize=True)
            
        buffer.seek(0)
        return buffer
    except Exception as e:
        print(f"Error compressing image: {e}")
        with open(image_path, 'rb') as f:
            return io.BytesIO(f.read())

def send_to_telegram_async(photo_path, caption):
    def send():
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendPhoto"
            compressed_photo = compress_image(photo_path)
            files = {
                'photo': ('compressed.jpg', compressed_photo, 'image/jpeg')
            }
            data = {
                'chat_id': CHAT_ID,
                'caption': caption
            }
            response = requests.post(url, files=files, data=data, timeout=30)
            if response.status_code == 200:
                print(f"✅ Success sent to Telegram")
            else:
                print(f"❌ Failed: {response.text}")
        except Exception as e:
            print(f"⚠️ Error sending to Telegram: {e}")
    
    thread = threading.Thread(target=send)
    thread.daemon = True
    thread.start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/kegiatan')
def kegiatan():
    return render_template('kegiatan.html')

@app.route('/riwayat')
def riwayat():
    data = load_data()
    tahun = request.args.get('tahun', '')
    bulan = request.args.get('bulan', '')
    tanggal = request.args.get('tanggal', '')
    pencarian = request.args.get('pencarian', '')
    tipe = request.args.get('tipe', '')
    
    purchases = data.get('pembelian', [])
    activities = data.get('kegiatan', [])
    
    filtered_purchases = []
    for p in purchases:
        match = True
        if tahun and not p['tanggal'].startswith(tahun): match = False
        if bulan and p['tanggal'][5:7] != bulan.zfill(2): match = False
        if tanggal and p['tanggal'] != tanggal: match = False
        if pencarian:
            search_lower = pencarian.lower()
            if search_lower not in p['uraian'].lower() and search_lower not in p['kode_unik'].lower(): match = False
        if tipe == 'kegiatan': match = False
        if match:
            p['tipe_data'] = 'pembelian'
            filtered_purchases.append(p)
    
    filtered_activities = []
    for a in activities:
        match = True
        if tahun and not a['tanggal'].startswith(tahun): match = False
        if bulan and a['tanggal'][5:7] != bulan.zfill(2): match = False
        if tanggal and a['tanggal'] != tanggal: match = False
        if pencarian:
            search_lower = pencarian.lower()
            if search_lower not in a['nama_kegiatan'].lower() and search_lower not in a['kode_unik'].lower(): match = False
        if tipe == 'pembelian': match = False
        if match:
            a['tipe_data'] = 'kegiatan'
            filtered_activities.append(a)
    
    all_records = filtered_purchases + filtered_activities
    all_records.sort(key=lambda x: x.get('tanggal', ''), reverse=True)
    
    all_dates = [p['tanggal'] for p in purchases] + [a['tanggal'] for a in activities]
    years = sorted(list(set([d[:4] for d in all_dates if len(d) >= 4])), reverse=True)
    months = sorted(list(set([d[5:7] for d in all_dates if len(d) >= 7])))
    
    return render_template('riwayat.html', 
                          records=all_records, years=years, months=months,
                          filter_tahun=tahun, filter_bulan=bulan, filter_tanggal=tanggal,
                          filter_pencarian=pencarian, filter_tipe=tipe)

@app.route('/add-purchase', methods=['POST'])
def add_purchase():
    tanggal = request.form.get('tanggal')
    uraian = request.form.get('uraian')
    jumlah = request.form.get('jumlah')
    nomor_bukti = request.form.get('nomor_bukti')
    foto = request.files.get('foto')
    
    if not all([tanggal, uraian, jumlah]):
        flash('Semua field wajib diisi!', 'error')
        return redirect(url_for('index'))
    
    try:
        jumlah_clean = jumlah.replace('.', '')
        jumlah_val = float(jumlah_clean)
    except ValueError:
        flash('Jumlah harus berupa angka!', 'error')
        return redirect(url_for('index'))
    
    kode_unik = generate_unique_code()
    foto_filename = None
    
    if foto and foto.filename:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        foto_filename = f"{timestamp}_{foto.filename}"
        foto_path = os.path.join(UPLOAD_FOLDER, foto_filename)
        foto.save(foto_path)
        caption = f"📝 Pembelian Baru\n\n🔖 Kode: #{kode_unik}\n📅 Tanggal: {tanggal}\n📋 Uraian: {uraian}\n💰 Jumlah: Rp {jumlah_val:,.0f}\n🔢 No Bukti: {nomor_bukti or '-'}"
        send_to_telegram_async(foto_path, caption)
    
    purchase = {
        'id': datetime.now().timestamp(), 'kode_unik': kode_unik, 'tanggal': tanggal,
        'uraian': uraian, 'jumlah': jumlah_val, 'nomor_bukti': nomor_bukti,
        'foto': foto_filename, 'created_at': datetime.now().isoformat()
    }
    
    data = load_data()
    data['pembelian'].append(purchase)
    save_data(data)
    flash(f'Data pembelian berhasil disimpan! Kode: #{kode_unik}', 'success')
    return redirect(url_for('index'))

@app.route('/add-kegiatan', methods=['POST'])
def add_kegiatan():
    tanggal = request.form.get('tanggal')
    nama_kegiatan = request.form.get('nama_kegiatan')
    foto = request.files.get('foto')
    
    if not all([tanggal, nama_kegiatan]):
        flash('Tanggal dan Nama Kegiatan wajib diisi!', 'error')
        return redirect(url_for('kegiatan'))
    
    kode_unik = generate_unique_code()
    foto_filename = None
    
    if foto and foto.filename:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
        foto_filename = f"{timestamp}_{foto.filename}"
        foto_path = os.path.join(UPLOAD_FOLDER, foto_filename)
        foto.save(foto_path)
        caption = f"🎯 Kegiatan Baru\n\n🔖 Kode: #{kode_unik}\n📅 Tanggal: {tanggal}\n📋 Nama: {nama_kegiatan}"
        send_to_telegram_async(foto_path, caption)
    
    activity = {
        'id': datetime.now().timestamp(), 'kode_unik': kode_unik, 'tanggal': tanggal,
        'nama_kegiatan': nama_kegiatan, 'foto': foto_filename, 'created_at': datetime.now().isoformat()
    }
    
    data = load_data()
    data['kegiatan'].append(activity)
    save_data(data)
    flash(f'Data kegiatan berhasil disimpan! Kode: #{kode_unik}', 'success')
    return redirect(url_for('kegiatan'))

@app.route('/delete-purchase/<float:purchase_id>')
def delete_purchase(purchase_id):
    data = load_data()
    purchase_to_delete = next((p for p in data['pembelian'] if p['id'] == purchase_id), None)
    if purchase_to_delete:
        if purchase_to_delete.get('foto'):
            foto_path = os.path.join(UPLOAD_FOLDER, purchase_to_delete['foto'])
            if os.path.exists(foto_path): os.remove(foto_path)
        data['pembelian'] = [p for p in data['pembelian'] if p['id'] != purchase_id]
        save_data(data)
    flash('Data pembelian berhasil dihapus!', 'success')
    return redirect(url_for('riwayat'))

@app.route('/delete-kegiatan/<float:kegiatan_id>')
def delete_kegiatan(kegiatan_id):
    data = load_data()
    activity_to_delete = next((a for a in data['kegiatan'] if a['id'] == kegiatan_id), None)
    if activity_to_delete:
        if activity_to_delete.get('foto'):
            foto_path = os.path.join(UPLOAD_FOLDER, activity_to_delete['foto'])
            if os.path.exists(foto_path): os.remove(foto_path)
        data['kegiatan'] = [a for a in data['kegiatan'] if a['id'] != kegiatan_id]
        save_data(data)
    flash('Data kegiatan berhasil dihapus!', 'success')
    return redirect(url_for('riwayat'))

@app.route('/manifest.json')
def manifest():
    return send_from_directory('.', 'manifest.json')

@app.route('/icon-192.png')
def icon192():
    return send_from_directory('.', 'icon-192.png')

@app.route('/icon-512.png')
def icon512():
    return send_from_directory('.', 'icon-512.png')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
