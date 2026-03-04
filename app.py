from flask import Flask, render_template, request, jsonify, send_from_directory
import os
from datetime import datetime
import database 
import csv
import io
import re

app = Flask(__name__)

database.init_db()

@app.route('/')
def home():
    conn = database.get_db_connection()
    cargo = conn.execute("SELECT * FROM stok WHERE kategori = 'CARGO'").fetchall()
    campuran = conn.execute("SELECT * FROM stok WHERE kategori = 'CAMPURAN'").fetchall()
    mentahan = conn.execute("SELECT * FROM mentahan").fetchall()
    
    # Logika Baru yang sudah diperbaiki
    produksi_raw = conn.execute("SELECT * FROM produksi WHERE selesai < total_pcs ORDER BY id DESC").fetchall()
    produksi_grouped = {}
    for p in produksi_raw:
        batch_key = f"{p['tanggal']} - {p['vendor_cuci']} ({p['warna_target']})"
        if batch_key not in produksi_grouped:
            # Ganti nama key dari 'items' jadi 'list_barang' supaya tidak error
            produksi_grouped[batch_key] = {'list_barang': [], 'grand_total': 0}
        produksi_grouped[batch_key]['list_barang'].append(p)
        produksi_grouped[batch_key]['grand_total'] += p['total_pcs']
        
    total_mentahan = conn.execute("SELECT SUM(jumlah) FROM mentahan").fetchone()[0] or 0
    logs = conn.execute("SELECT * FROM log_aktivitas ORDER BY id DESC LIMIT 50").fetchall()
    conn.close()
    
    return render_template('index.html', cargo=cargo, campuran=campuran, mentahan=mentahan, produksi_grouped=produksi_grouped, total_mentahan=total_mentahan, logs=logs)

@app.route('/update_stok', methods=['POST'])
def update_stok():
    data = request.get_json()
    conn = database.get_db_connection()
    stok_sekarang = conn.execute('SELECT jumlah_gudang FROM stok WHERE sku = ?', (data['sku'],)).fetchone()['jumlah_gudang']
    
    stok_baru = stok_sekarang + data['jumlah'] if data['aksi'] == 'tambah' else stok_sekarang - data['jumlah']
    if stok_baru < 0: return jsonify({"status": "error", "pesan": "Stok kurang!"})

    conn.execute('UPDATE stok SET jumlah_gudang = ? WHERE sku = ?', (stok_baru, data['sku']))
    # Sisipkan ini sebelum conn.commit()
    waktu = datetime.now().strftime("%d %b %H:%M")
    kata_aksi = "Masuk" if data['aksi'] == 'tambah' else "Keluar"
    keterangan = f"{kata_aksi} {data['jumlah']} pcs (SKU: {data['sku']}). Sisa: {stok_baru}"
    conn.execute("INSERT INTO log_aktivitas (waktu, keterangan) VALUES (?, ?)", (waktu, keterangan))
    conn.commit()
    conn.close()
    return jsonify({"status": "sukses", "stok_baru": stok_baru, "sku": data['sku']})

@app.route('/tambah_mentahan', methods=['POST'])
def tambah_mentahan():
    data = request.get_json()
    conn = database.get_db_connection()
    existing = conn.execute("SELECT id, jumlah FROM mentahan WHERE model = ? AND size = ?", (data['model'], data['size'])).fetchone()
    if existing:
        conn.execute("UPDATE mentahan SET jumlah = ? WHERE id = ?", (existing['jumlah'] + int(data['jumlah']), existing['id']))
    else:
        conn.execute("INSERT INTO mentahan (model, size, jumlah) VALUES (?, ?, ?)", (data['model'], data['size'], data['jumlah']))
    conn.commit()
    conn.close()
    return jsonify({"status": "sukses"})

@app.route('/kirim_produksi_massal', methods=['POST'])
def kirim_produksi_massal():
    data = request.get_json()
    vendor = data.get('vendor')
    warna = data.get('warna') # Sekarang warnanya diambil satu untuk semua
    items = data.get('items', [])
    
    conn = database.get_db_connection()
    tgl = datetime.now().strftime("%d %b")
    
    try:
        for item in items:
            id_mentahan = item['id_mentahan']
            qty_kirim = int(item['qty'])
            
            mentahan = conn.execute("SELECT jumlah FROM mentahan WHERE id = ?", (id_mentahan,)).fetchone()
            if not mentahan or mentahan['jumlah'] < qty_kirim:
                return jsonify({"status": "error", "pesan": f"Stok mentahan {item['model']} kurang!"})
            
            sisa = mentahan['jumlah'] - qty_kirim
            if sisa == 0:
                conn.execute("DELETE FROM mentahan WHERE id = ?", (id_mentahan,))
            else:
                conn.execute("UPDATE mentahan SET jumlah = ? WHERE id = ?", (sisa, id_mentahan))
            
            conn.execute('''
                INSERT INTO produksi (tanggal, model, size, warna_target, vendor_cuci, total_pcs, di_cuci, di_finishing, selesai)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (tgl, item['model'], item['size'], warna, vendor, qty_kirim, qty_kirim, 0, 0))
        
        conn.commit()
        status = "sukses"
    except Exception as e:
        status = "error"
    finally:
        conn.close()
        
    return jsonify({"status": status})

@app.route('/update_progress', methods=['POST'])
def update_progress():
    data = request.get_json()
    batch_id = data['id']
    qty = int(data['qty'])
    aksi = data['aksi']
    
    conn = database.get_db_connection()
    batch = conn.execute("SELECT * FROM produksi WHERE id = ?", (batch_id,)).fetchone()
    
    if aksi == 'ke_finishing':
        if qty > batch['di_cuci']: return jsonify({"status": "error", "pesan": "Jumlah melebihi yang ada di cucian!"})
        conn.execute("UPDATE produksi SET di_cuci = di_cuci - ?, di_finishing = di_finishing + ? WHERE id = ?", (qty, qty, batch_id))
    
    elif aksi == 'ke_gudang':
        if qty > batch['di_finishing']: return jsonify({"status": "error", "pesan": "Jumlah melebihi yang ada di finishing!"})
        conn.execute("UPDATE produksi SET di_finishing = di_finishing - ?, selesai = selesai + ? WHERE id = ?", (qty, qty, batch_id))
        
    conn.commit()
    conn.close()
    return jsonify({"status": "sukses"})

@app.route('/update_progress_bulk', methods=['POST'])
def update_progress_bulk():
    data = request.get_json()
    ids = data['ids']
    aksi = data['aksi']
    
    conn = database.get_db_connection()
    for batch_id in ids:
        batch = conn.execute("SELECT * FROM produksi WHERE id = ?", (batch_id,)).fetchone()
        if not batch: continue
        
        if aksi == 'ke_finishing':
            qty = batch['di_cuci']
            if qty > 0:
                conn.execute("UPDATE produksi SET di_cuci = 0, di_finishing = di_finishing + ? WHERE id = ?", (qty, batch_id))
        elif aksi == 'ke_gudang':
            qty = batch['di_finishing']
            if qty > 0:
                conn.execute("UPDATE produksi SET di_finishing = 0, selesai = selesai + ? WHERE id = ?", (qty, batch_id))
                
    conn.commit()
    conn.close()
    return jsonify({"status": "sukses"})

@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    if 'file' not in request.files: return jsonify({"status": "error", "pesan": "Tidak ada file"})
    file = request.files['file']
    try:
        file_bytes = file.stream.read()
        try: file_str = file_bytes.decode('utf-8-sig')
        except:
            try: file_str = file_bytes.decode('utf-16')
            except: file_str = file_bytes.decode('cp1252')
                
        stream = io.StringIO(file_str, newline=None)
        
        # --- MULAI DARI SINI SPASINYA SUDAH DIRAPIKAN ---
        first_line = file_str.split('\n')[0]
        if ';' in first_line:
            pemisah = ';'
        elif '\t' in first_line:
            pemisah = '\t'
        else:
            pemisah = ','
            
        stream.seek(0)
        csv_input = csv.DictReader(stream, delimiter=pemisah)

        rekap_pesanan = {}
        
        for row in csv_input:
            produk = row.get('Product Name', '').strip()
            variasi = row.get('Variation', '').strip()
            qty_str = row.get('Quantity', '0').strip()
            status = row.get('Order Status', '').strip().upper()
            
            if 'CANCEL' in status or 'BATAL' in status: continue
            if not produk and not variasi: continue
            
            # Abaikan baris ke-2 dari TikTok yang isinya cuma teks penjelasan
            try: qty = int(qty_str)
            except: qty = 0
            if qty == 0: continue
            
            kunci_rekap = f"{produk} || {variasi}"
            rekap_pesanan[kunci_rekap] = rekap_pesanan.get(kunci_rekap, 0) + qty

        if not rekap_pesanan:
            return jsonify({"status": "error", "pesan": "Tidak ada data pesanan valid. Pastikan ada kolom Product Name, Variation, dan Quantity."})

        conn = database.get_db_connection()
        stok_semua = conn.execute("SELECT sku, varian, size, jumlah_gudang, kategori FROM stok").fetchall()
        
        hasil_rekap = []
        for kunci, butuh_qty in rekap_pesanan.items():
            produk, variasi = kunci.split(" || ")
            
            variasi_normal = variasi.lower()
            variasi_normal = variasi_normal.replace('8 (8tahun)', '8').replace('9 (9tahun)', '9').replace('10 (10 tahun)', '10')
            
            teks_cari_warna = f"{produk} {variasi_normal}".lower()
            teks_cari_size = variasi_normal if variasi_normal else produk.lower()
            
            barang_cocok = None
            for b in stok_semua:
                varian_db = b['varian'].lower()
                size_db = b['size'].lower()
                
                kata_varian = varian_db.split()
                cocok_warna = all(kata in teks_cari_warna for kata in kata_varian)
                cocok_size = re.search(r'\b' + re.escape(size_db) + r'\b', teks_cari_size)
                
                if cocok_warna and cocok_size:
                    if 'cargo' in produk.lower() and b['kategori'] != 'CARGO': continue
                    barang_cocok = b
                    break
            
            if barang_cocok:
                sisa = barang_cocok['jumlah_gudang'] - butuh_qty
                hasil_rekap.append({
                    "sku": barang_cocok['sku'], "nama": f"{barang_cocok['varian']} ({barang_cocok['size']})",
                    "butuh": butuh_qty, "stok": barang_cocok['jumlah_gudang'], "sisa": sisa
                })
            else:
                nama_tampil = variasi if variasi else produk[:30]
                hasil_rekap.append({
                    "sku": "?", "nama": f"⚠️ {nama_tampil}", "butuh": butuh_qty, "stok": "-", "sisa": -butuh_qty
                })
                
        conn.close()
        hasil_rekap.sort(key=lambda x: x['sisa'] if isinstance(x['sisa'], int) else -9999)
        return jsonify({"status": "sukses", "data": hasil_rekap})
    except Exception as e:
        return jsonify({"status": "error", "pesan": f"Gagal membaca file: {str(e)}"})

@app.route('/manifest.json')
def serve_manifest(): return send_from_directory('.', 'manifest.json')
@app.route('/sw.js')
def serve_sw(): return send_from_directory('.', 'sw.js')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')