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
    
    produksi_raw = conn.execute("SELECT * FROM produksi WHERE selesai < total_pcs ORDER BY id DESC").fetchall()
    produksi_grouped = {}
    for p in produksi_raw:
        batch_key = f"{p['tanggal']} - {p['vendor_cuci']} ({p['warna_target']})"
        
        if batch_key not in produksi_grouped:
            if p['tanggal'].count(':') == 2: 
                tanggal_tampil = p['tanggal'][:-3] 
            else:
                tanggal_tampil = p['tanggal'] 
                
            nama_tampil = f"{tanggal_tampil} - {p['vendor_cuci']} ({p['warna_target']})"
            produksi_grouped[batch_key] = {'list_barang': [], 'grand_total': 0, 'nama_tampil': nama_tampil}
            
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
    warna = data.get('warna') 
    items = data.get('items', [])
    
    conn = database.get_db_connection()
    tgl = datetime.now().strftime("%d %b %H:%M:%S")
    
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
    files = request.files.getlist('file')
    if not files or files[0].filename == '':
        return jsonify({"status": "error", "pesan": "Tidak ada file"})

    # Ambil database Cargo dulu buat patokan "perjodohan"
    conn = database.get_db_connection()
    stok_semua = conn.execute("SELECT sku, varian, size, jumlah_gudang, kategori FROM stok WHERE kategori = 'CARGO'").fetchall()
    
    # Brankas baru yang dikelompokkan berdasarkan SKU Database, bukan teks CSV!
    rekap_pesanan_db = {}
    unmatched_pesanan = {}

    for file in files:
        try:
            row_dicts = []
            nama_file = file.filename.lower()
            file_bytes = file.read() 
            
            # 🧠 JIKA FILE EXCEL SHOPEE (.xlsx)
            if nama_file.endswith('.xlsx'):
                try:
                    import openpyxl
                except Exception as e:
                    import sys
                    versi_python = '.'.join(sys.version.split('.')[:2]) 
                    return jsonify({"status": "error", "pesan": f"Gagal memuat Excel. Di Bash ketik: pip{versi_python} install openpyxl -t ."})
                
                wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
                
                sheet = wb.active 
                for s in wb.worksheets:
                    if 'order' in s.title.lower() or 'pesanan' in s.title.lower():
                        sheet = s
                        break
                        
                headers = [str(cell.value).strip() if cell.value is not None else '' for cell in sheet[1]]
                for row in sheet.iter_rows(min_row=2, values_only=True):
                    if not any(row): continue
                    row_dict = {headers[i]: str(row[i]) if i < len(row) and row[i] is not None else '' for i in range(len(headers))}
                    row_dicts.append(row_dict)
                    
            # 🧠 JIKA FILE CSV TIKTOK (.csv)
            else:
                try: file_str = file_bytes.decode('utf-8-sig')
                except:
                    try: file_str = file_bytes.decode('utf-16')
                    except: file_str = file_bytes.decode('cp1252')
                        
                stream = io.StringIO(file_str, newline=None)
                first_line = file_str.split('\n')[0]
                if ';' in first_line: pemisah = ';'
                elif '\t' in first_line: pemisah = '\t'
                else: pemisah = ','
                    
                stream.seek(0)
                csv_input = csv.DictReader(stream, delimiter=pemisah)
                row_dicts = list(csv_input)

            # --- PROSES PEMBACAAN DAN PERJODOHAN ---
            for row in row_dicts:
                produk = (row.get('Product Name') or row.get('Nama Produk') or '').strip()
                variasi = (row.get('Variation') or row.get('Nama Variasi') or '').strip()
                qty_str = (row.get('Quantity') or row.get('Jumlah') or '1').strip() 
                
                status_tk = (row.get('Order Status') or '').strip().upper()
                status_sh_1 = (row.get('Status Pesanan') or '').strip().upper()
                status_sh_2 = (row.get('Status Pembatalan/ Pengembalian') or '').strip().upper()
                status_gabungan = f"{status_tk} {status_sh_1} {status_sh_2}"
                
                # SATPAM 1: Buang yang Batal/Cancel
                if 'CANCEL' in status_gabungan or 'BATAL' in status_gabungan: continue
                if not produk and not variasi: continue
                
                try: qty = int(qty_str)
                except: qty = 1 
                if qty == 0: continue
                
                # SATPAM 2: Pastikan ini murni celana Cargo Anak
                produk_lower = produk.lower()
                is_tiktok_cargo = 'celana panjang anak cargo pinggang full karet' in produk_lower
                is_shopee_cargo = 'celana panjang anak cargo usia 1-8' in produk_lower
                
                if not (is_tiktok_cargo or is_shopee_cargo):
                    continue
                
                # Samakan terjemahan warna saja
                variasi_normal = variasi.lower().replace('snow black', 'snow hitam') 
                teks_cari = f"{produk_lower} {variasi_normal}"
                
                # 🧠 PROSES PERJODOHAN LANGSUNG KE DATABASE
                barang_cocok = None
                for b in stok_semua:
                    kata_varian = b['varian'].lower().split()
                    cocok_warna = all(k in teks_cari for k in kata_varian)
                    # Regex ini sangat pintar, dia otomatis mengabaikan spasi atau kurung
                    cocok_size = re.search(r'\b' + re.escape(b['size'].lower()) + r'\b', teks_cari)
                    
                    if cocok_warna and cocok_size:
                        barang_cocok = b
                        break
                
                # Kalau jodoh ketemu, gabungkan berdasarkan KTP/SKU nya!
                if barang_cocok:
                    sku = barang_cocok['sku']
                    if sku not in rekap_pesanan_db:
                        rekap_pesanan_db[sku] = {'db_item': barang_cocok, 'qty': 0}
                    rekap_pesanan_db[sku]['qty'] += qty
                else:
                    kunci_unmatched = f"⚠️ {variasi_normal if variasi_normal else produk[:30]}"
                    unmatched_pesanan[kunci_unmatched] = unmatched_pesanan.get(kunci_unmatched, 0) + qty

        except Exception as e:
            conn.close()
            return jsonify({"status": "error", "pesan": f"Gagal membaca file {file.filename}: {str(e)}"})

    conn.close()

    if not rekap_pesanan_db and not unmatched_pesanan:
        return jsonify({"status": "error", "pesan": "Tidak ada pesanan Cargo valid di file yang diupload."})
    
    # --- MENYUSUN HASIL AKHIR ---
    hasil_rekap = []
    for sku, data in rekap_pesanan_db.items():
        b = data['db_item']
        butuh = data['qty']
        sisa = b['jumlah_gudang'] - butuh
        hasil_rekap.append({
            "sku": b['sku'], "nama": f"{b['varian']} ({b['size']})",
            "butuh": butuh, "stok": b['jumlah_gudang'], "sisa": sisa,
            "warna_sort": b['varian'].lower(), "size_sort": b['size'].lower()
        })
        
    for nama, butuh in unmatched_pesanan.items():
        hasil_rekap.append({
            "sku": "?", "nama": nama, "butuh": butuh, "stok": "-", "sisa": -butuh,
            "warna_sort": "zz", "size_sort": "zz"
        })
    
    # Algoritma Pengurutan Sesuai Rak Gudangmu
    urutan_warna = {"light blue": 1, "snow hitam": 2, "snow biru": 3}
    urutan_size = {"s": 1, "m": 2, "l": 3, "xl": 4, "8": 5, "9": 6, "10": 7}
    
    def aturan_urut(item):
        warna_idx = urutan_warna.get(item['warna_sort'], 99)
        size_idx = urutan_size.get(item['size_sort'], 99)
        return (warna_idx, size_idx)
        
    hasil_rekap.sort(key=aturan_urut)
    return jsonify({"status": "sukses", "data": hasil_rekap})

@app.route('/manifest.json')
def serve_manifest(): return send_from_directory('.', 'manifest.json')
@app.route('/sw.js')
def serve_sw(): return send_from_directory('.', 'sw.js')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')