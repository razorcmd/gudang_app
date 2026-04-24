from flask import Flask, render_template, request, jsonify, send_from_directory, send_file, render_template_string
import os
from datetime import datetime
import database 
import csv
import io
import re
import itertools
import zipfile
# --- TAMBAHAN IMPORT UNTUK QR CODE & URL ---
import qrcode
import urllib.parse

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

    conn = database.get_db_connection()
    stok_semua = conn.execute("SELECT sku, varian, size, jumlah_gudang, kategori FROM stok WHERE kategori = 'CARGO'").fetchall()
    
    rekap_pesanan_db = {}
    unmatched_pesanan = {}

    for file in files:
        try:
            row_dicts = []
            nama_file = file.filename.lower()
            file_bytes = file.read() 
            
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

            for row in row_dicts:
                produk = (row.get('Product Name') or row.get('Nama Produk') or '').strip()
                variasi = (row.get('Variation') or row.get('Nama Variasi') or '').strip()
                qty_str = (row.get('Quantity') or row.get('Jumlah') or '1').strip() 
                
                status_tk = (row.get('Order Status') or '').strip().upper()
                status_sh_1 = (row.get('Status Pesanan') or '').strip().upper()
                status_sh_2 = (row.get('Status Pembatalan/ Pengembalian') or '').strip().upper()
                status_gabungan = f"{status_tk} {status_sh_1} {status_sh_2}"
                
                if 'CANCEL' in status_gabungan or 'BATAL' in status_gabungan: continue
                if not produk and not variasi: continue
                
                try: qty = int(qty_str)
                except: qty = 1 
                if qty == 0: continue
                
                produk_lower = produk.lower()
                is_tiktok_cargo = 'celana panjang anak cargo pinggang full karet' in produk_lower
                is_shopee_cargo = 'celana panjang anak cargo usia 1-8' in produk_lower
                
                if not (is_tiktok_cargo or is_shopee_cargo):
                    continue
                
                variasi_normal = variasi.lower().replace('snow black', 'snow hitam') 
                teks_cari = f"{produk_lower} {variasi_normal}"
                
                barang_cocok = None
                for b in stok_semua:
                    kata_varian = b['varian'].lower().split()
                    cocok_warna = all(k in teks_cari for k in kata_varian)
                    cocok_size = re.search(r'\b' + re.escape(b['size'].lower()) + r'\b', teks_cari)
                    
                    if cocok_warna and cocok_size:
                        barang_cocok = b
                        break
                
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
    
    urutan_warna = {"light blue": 1, "snow hitam": 2, "snow biru": 3}
    urutan_size = {"s": 1, "m": 2, "l": 3, "xl": 4, "8": 5, "9": 6, "10": 7}
    
    def aturan_urut(item):
        warna_idx = urutan_warna.get(item['warna_sort'], 99)
        size_idx = urutan_size.get(item['size_sort'], 99)
        return (warna_idx, size_idx)
        
    hasil_rekap.sort(key=aturan_urut)
    return jsonify({"status": "sukses", "data": hasil_rekap})

# =========================================================================
# --- FUNGSI & URL RAHASIA OPITO (TIDAK MENGGANGGU WEB UTAMA) ---
# =========================================================================

def generate_case_combinations(code_string):
    letter_indices = [i for i, char in enumerate(code_string) if char.isalpha()]
    letters_to_permute = [code_string[i] for i in letter_indices]
    case_options = [(char.lower(), char.upper()) for char in letters_to_permute]

    for combo in itertools.product(*case_options):
        temp_list = list(code_string)
        for i, new_char in enumerate(combo):
            original_index = letter_indices[i]
            temp_list[original_index] = new_char
        yield "".join(temp_list)

@app.route('/admin-rahasia-opito', methods=['GET', 'POST'])
def rahasia_opito():
    if request.method == 'GET':
        html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Secret Tools</title>
            <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=0">
        </head>
        <body style="background: #f4f7f6; padding: 20px; font-family: Arial, sans-serif;">
            <div style="max-width: 400px; margin: 40px auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 4px 8px rgba(0,0,0,0.1);">
                
                <h3 style="text-align: center; color: #333;">🛠️ OPITO CSV Generator</h3>
                <form method="POST">
                    <input type="hidden" name="action" value="generate_csv">
                    
                    <label style="font-size: 14px; color: #555;">Learner Surname:</label><br>
                    <input type="text" id="csv_surname" name="surname" placeholder="Contoh: Helmi Setyawan" required style="font-size: 16px; width: 95%; margin-top: 5px; margin-bottom: 15px; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">                    
                    <label style="font-size: 14px; color: #555;">Kode Kombinasi:</label><br>
                    <input type="text" name="base_code" placeholder="Contoh: PWZ6YXWUFQ" required style="font-size: 16px; width: 95%; margin-top: 5px; margin-bottom: 20px; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">                    
                    <button type="submit" style="width: 100%; padding: 12px; background: #28a745; color: white; font-weight: bold; border: none; border-radius: 4px; cursor: pointer;">Generate & Download .ZIP</button>
                </form>

                <hr style="margin: 30px 0; border: 1px dashed #ccc;">

                <h3 style="text-align: center; color: #333;">📱 QR Code Generator</h3>
                <form method="POST">
                    <input type="hidden" name="action" value="generate_qr">
                    
                    <label style="font-size: 14px; color: #555;">Learner Surname:</label><br>
                    <input type="text" id="qr_surname" name="qr_surname" placeholder="Contoh: Helmi Setyawan" required style="font-size: 16px; width: 95%; margin-top: 5px; margin-bottom: 15px; padding: 10px; border: 1px solid #ccc; border-radius: 4px;"> 

                    <label style="font-size: 14px; color: #555;">Certification Date:</label><br>
                    <input type="date" name="qr_cert_date" required style="font-size: 16px; width: 95%; margin-top: 5px; margin-bottom: 15px; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">

                    <label style="font-size: 14px; color: #555;">Ref (Kode Kombinasi Valid):</label><br>
                    <input type="text" name="qr_ref" placeholder="Contoh: OPITOpZo1dHge2K" required style="font-size: 16px; width: 95%; margin-top: 5px; margin-bottom: 20px; padding: 10px; border: 1px solid #ccc; border-radius: 4px;">

                    <button type="submit" style="width: 100%; padding: 12px; background: #007bff; color: white; font-weight: bold; border: none; border-radius: 4px; cursor: pointer;">Generate & Download QR (.png)</button>
                </form>

            </div>

            <script>
                document.getElementById('csv_surname').addEventListener('input', function() {
                    document.getElementById('qr_surname').value = this.value;
                });
            </script>
        </body>
        </html>
        """
        return render_template_string(html)
    
    if request.method == 'POST':
        action = request.form.get('action')

        # JIKA TOMBOL CSV DIKLIK
        if action == 'generate_csv':
            surname = request.form.get('surname', '').strip()
            base_code = request.form.get('base_code', '').strip()
            
            headers = [
                "Learner Surname (required),Certificate Reference (required)",
                "LearnerSurname,CertificateReference",
                ""
            ]
            
            combinations = list(generate_case_combinations(base_code))
            chunk_size = 100
            
            memory_file = io.BytesIO()
            with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
                file_count = 1
                for i in range(0, len(combinations), chunk_size):
                    chunk = combinations[i:i + chunk_size]
                    
                    safe_surname = surname.replace(' ', '_')
                    filename = f"{safe_surname}_OPITO_part_{file_count}.csv"
                    
                    csv_content = "\n".join(headers) + "\n"
                    for combo in chunk:
                        csv_content += f"{surname},OPITO{combo}\n"
                    
                    zf.writestr(filename, csv_content)
                    file_count += 1
            
            memory_file.seek(0)
            zip_filename = f"OPITO_{surname.replace(' ', '_')}.zip"
            
            return send_file(
                memory_file,
                download_name=zip_filename,
                as_attachment=True,
                mimetype='application/zip'
            )

        # JIKA TOMBOL QR CODE DIKLIK
        elif action == 'generate_qr':
            surname = request.form.get('qr_surname', '').strip()
            cert_date = request.form.get('qr_cert_date', '').strip()
            ref = request.form.get('qr_ref', '').strip()

            # 1. Merakit URL & Memastikan spasi pada nama di-encode menjadi %20
            safe_surname = urllib.parse.quote(surname)
            url_data = f"https://www.thehubopito.com/public/validate?Surname={safe_surname}&CertificationDate={cert_date}&Ref={ref}"

            # 2. Membuat Objek QR Code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=4,
            )
            qr.add_data(url_data)
            qr.make(fit=True)

            # 3. Membuat gambar ke dalam memory
            img = qr.make_image(fill_color="black", back_color="white")
            img_io = io.BytesIO()
            img.save(img_io, 'PNG')
            img_io.seek(0)

            # 4. Mengunduh gambar secara langsung
            filename = f"QR_{surname.replace(' ', '_')}.png"
            return send_file(
                img_io,
                download_name=filename,
                as_attachment=True,
                mimetype='image/png'
            )

# =========================================================================

@app.route('/manifest.json')
def serve_manifest(): return send_from_directory('.', 'manifest.json')
@app.route('/sw.js')
def serve_sw(): return send_from_directory('.', 'sw.js')

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')