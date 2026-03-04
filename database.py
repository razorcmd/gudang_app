import sqlite3
from datetime import datetime

def get_db_connection():
    conn = sqlite3.connect('gudang.db')
    conn.row_factory = sqlite3.Row 
    return conn

def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS stok (
            sku TEXT PRIMARY KEY, nama TEXT, varian TEXT, size TEXT, petak TEXT, jumlah_gudang INTEGER, kategori TEXT
        )
    ''')
    conn.execute('CREATE TABLE IF NOT EXISTS mentahan (id INTEGER PRIMARY KEY AUTOINCREMENT, model TEXT, size TEXT, jumlah INTEGER)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS produksi (
            id INTEGER PRIMARY KEY AUTOINCREMENT, tanggal TEXT, model TEXT, size TEXT, warna_target TEXT, vendor_cuci TEXT,
            total_pcs INTEGER, di_cuci INTEGER, di_finishing INTEGER, selesai INTEGER
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS log_aktivitas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, waktu TEXT, keterangan TEXT
        )
    ''')
    
    cursor = conn.cursor()
    cursor.execute('SELECT count(*) FROM stok')
    if cursor.fetchone()[0] == 0:
        data_stok = []
        
        # --- 1. GENERATE PRODUK CARGO (3 Warna x 7 Size = 21 SKU) ---
        cargo_warna = ["Snow Hitam", "Snow Biru", "Light Blue"]
        cargo_size = ["S", "M", "L", "XL", "8", "9", "10"]
        for w in cargo_warna:
            for s in cargo_size:
                # Bikin singkatan SKU otomatis (Contoh: CRG-SH-M)
                kode_warna = "".join([kata[0] for kata in w.split()]).upper() 
                sku = f"CRG-{kode_warna}-{s}"
                data_stok.append((sku, 'Celana Cargo', w, s, 'Gudang 1', 0, 'CARGO'))

        # --- 2. GENERATE PRODUK CAMPURAN ---
        campuran_list = [
            ("Dressy", ["Snow Biru"], ["S", "M", "L", "XL", "XXL"]),
            ("Buggy Jeans", ["Bio Stone Wisker", "Light Blue Wisker"], ["S", "M", "L", "XL"]),
            ("Kulot Cargo", ["Snow Biru", "Snow Hitam"], ["S", "M", "L", "XL"]),
            ("Overall", ["Default"], ["S", "M", "L", "XL"]), # Ku anggap Overall ga ada warna spesifik
            ("Celana Pendek", ["Snow Biru", "Snow Hitam"], ["S", "M", "L", "XL"]),
            ("Cutbray", ["Snow Hitam", "Snow Biru"], ["S", "M", "L", "XL"]),
            ("Sobek", ["Snow Biru", "Snow Hitam"], ["S", "M", "L", "XL"]),
            ("Sobek Hitam Putih", ["Hitam", "Putih"], ["S", "M", "L", "XL"])
        ]
        
        prefix_counter = 1
        for nama, warnas, sizes in campuran_list:
            prefix = "".join([x[0] for x in nama.split()]).upper()[:3] + str(prefix_counter)
            prefix_counter += 1
            for w in warnas:
                for s in sizes:
                    kode_warna = "".join([kata[0] for kata in w.split()]).upper()
                    sku = f"{prefix}-{kode_warna}-{s}"
                    data_stok.append((sku, nama, w, s, 'Gudang 2', 0, 'CAMPURAN'))

        # Tembak semua 70+ data sekaligus ke database!
        conn.executemany('INSERT INTO stok VALUES (?, ?, ?, ?, ?, ?, ?)', data_stok)
        
        # Data dummy untuk tab produksi biar ga kosong
        conn.execute("INSERT INTO mentahan (model, size, jumlah) VALUES ('Cargo', 'M', 150)")
        conn.commit()
    conn.close()