from flask import Flask, render_template, request, jsonify, send_from_directory
import os
from datetime import datetime
import database 

app = Flask(__name__)

database.init_db()

@app.route('/')
def home():
    conn = database.get_db_connection()
    cargo = conn.execute("SELECT * FROM stok WHERE kategori = 'CARGO'").fetchall()
    campuran = conn.execute("SELECT * FROM stok WHERE kategori = 'CAMPURAN'").fetchall()
    mentahan = conn.execute("SELECT * FROM mentahan").fetchall()
    
    # Logika Baru: Mengelompokkan Produksi per Batch + Menghitung Total Pcs
    produksi_raw = conn.execute("SELECT * FROM produksi WHERE selesai < total_pcs ORDER BY id DESC").fetchall()
    produksi_grouped = {}
    for p in produksi_raw:
        batch_key = f"{p['tanggal']} - {p['vendor_cuci']} ({p['warna_target']})"
        if batch_key not in produksi_grouped:
            produksi_grouped[batch_key] = {'items': [], 'grand_total': 0}
        produksi_grouped[batch_key]['items'].append(p)
        produksi_grouped[batch_key]['grand_total'] += p['total_pcs']
        
    total_mentahan = conn.execute("SELECT SUM(jumlah) FROM mentahan").fetchone()[0] or 0
    conn.close()
    
    return render_template('index.html', cargo=cargo, campuran=campuran, mentahan=mentahan, produksi_grouped=produksi_grouped, total_mentahan=total_mentahan)

@app.route('/update_stok', methods=['POST'])
def update_stok():
    data = request.get_json()
    conn = database.get_db_connection()
    stok_sekarang = conn.execute('SELECT jumlah_gudang FROM stok WHERE sku = ?', (data['sku'],)).fetchone()['jumlah_gudang']
    
    stok_baru = stok_sekarang + data['jumlah'] if data['aksi'] == 'tambah' else stok_sekarang - data['jumlah']
    if stok_baru < 0: return jsonify({"status": "error", "pesan": "Stok kurang!"})

    conn.execute('UPDATE stok SET jumlah_gudang = ? WHERE sku = ?', (stok_baru, data['sku']))
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

@app.route('/manifest.json')
def serve_manifest(): return send_from_directory('.', 'manifest.json')
@app.route('/sw.js')
def serve_sw(): return send_from_directory('.', 'sw.js')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')