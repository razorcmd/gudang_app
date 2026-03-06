function pindahBatchSemua(ids, aksi) {
    let namaTujuan = aksi === 'ke_finishing' ? 'FINISHING' : 'GUDANG';
    if(!confirm(`Yakin mau memindahkan SEMUA sisa barang di batch ini ke ${namaTujuan}?`)) return;

    fetch('/update_progress_bulk', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ids: ids, aksi: aksi})
    })
    .then(res => res.json())
    .then(res => {
        if(res.status == 'error') alert(res.pesan);
        else {
            if(aksi == 'ke_gudang') alert("Sukses masuk Gudang! Jangan lupa tambah stoknya di Tab Cargo/Campuran ya.");
            window.location.reload();
        }
    });
}

function switchTab(tabId, element) {
    document.querySelectorAll('.tab-content').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
    document.getElementById('tab-' + tabId).classList.add('active');
    element.classList.add('active');
    window.scrollTo(0, 0);
}

let kunciTombol = false;
let kunciGudang = {}; // Kunci khusus per barang biar nggak tabrakan

function simpanMentahan() {
    // Kalau gembok masih tertutup (masih proses), abaikan klik tambahan!
    if(kunciTombol) return; 
    
    let modelInput = document.getElementById('mModel').value.trim();
    let data = {
        model: modelInput !== "" ? modelInput : "Cargo",
        size: document.getElementById('mSize').value, 
        jumlah: document.getElementById('mQty').value
    };
    
    if(!data.size || !data.jumlah) { alert("Size dan Jumlah wajib diisi!"); return; }
    
    kunciTombol = true; // 🔒 Tutup gembok!
    
    fetch('/tambah_mentahan', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) })
    .then(() => window.location.reload())
    .catch(() => kunciTombol = false); // Buka gembok kalau error/gagal jaringan
}

function kirimCuciMassal() {
    let vendor = document.getElementById('kVendor').value;
    let warnaBatch = document.getElementById('kWarnaBatch').value; // Ambil warna dari input batch
    if(!vendor || !warnaBatch) { alert("Isi Nama Tempat Cuci & Warna Target dulu bos!"); return; }

    let items = [];
    let checkboxes = document.querySelectorAll('.chk-mentahan:checked');
    if(checkboxes.length === 0) { alert("Centang minimal 1 mentahan yang mau dikirim!"); return; }

    let valid = true;
    checkboxes.forEach(chk => {
        let row = chk.parentElement;
        let qty = row.querySelector('.qty-kirim').value;
        let maxQty = parseInt(chk.getAttribute('data-max'));

        if(!qty) { alert("Jumlah potong wajib diisi!"); valid = false; return; }
        if(parseInt(qty) > maxQty) { alert("Jumlah kirim melebihi stok mentahan!"); valid = false; return; }

        // Warna tidak diambil dari per-item lagi, tapi dari variabel warnaBatch
        items.push({ id_mentahan: chk.value, model: chk.getAttribute('data-model'), size: chk.getAttribute('data-size'), qty: qty });
    });

    if(!valid) return;

    fetch('/kirim_produksi_massal', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ vendor: vendor, warna: warnaBatch, items: items }) })
    .then(res => res.json()).then(res => {
        if(res.status == 'error') alert(res.pesan); else window.location.reload();
    });
}

// --- LOGIKA POP-UP PROGRESS PRODUKSI BARU ---
let modalData = {};

function bukaModal(id, aksi, pesan) {
    modalData = { id: id, aksi: aksi };
    document.getElementById('modalTitle').innerText = pesan;
    document.getElementById('modalInput').value = '';
    document.getElementById('customModal').style.display = 'flex'; // Munculin modal
    setTimeout(() => document.getElementById('modalInput').focus(), 100); // Otomatis buka keyboard
}

function tutupModal() {
    document.getElementById('customModal').style.display = 'none'; // Sembunyiin modal
}

function konfirmasiModal() {
    let qty = document.getElementById('modalInput').value;
    if (qty && !isNaN(qty) && parseInt(qty) > 0) {
        tutupModal();
        kirimProgress(modalData.id, modalData.aksi, qty);
    } else {
        alert("Masukkan jumlah yang valid!");
    }
}

// Fungsi utama untuk nembak data ke database
function kirimProgress(id, aksi, qty) {
    // Kalau yang diklik tombol "Centang", kita konfirmasi dulu biar ga salah klik
    if(!document.getElementById('customModal').style.display || document.getElementById('customModal').style.display == 'none') {
        if(!confirm(`Yakin mau memindahkan semua ${qty} potong?`)) return;
    }

    fetch('/update_progress', { 
        method: 'POST', 
        headers: {'Content-Type': 'application/json'}, 
        body: JSON.stringify({id: id, aksi: aksi, qty: qty}) 
    })
    .then(res => res.json())
    .then(res => {
        if(res.status == 'error') {
            alert(res.pesan); 
        } else {
            if(aksi == 'ke_gudang') alert("Sukses masuk Gudang! Jangan lupa tambah stoknya di Tab Cargo/Campuran ya.");
            window.location.reload();
        }
    });
}
// --------------------------------------------

function updateGudang(sku, aksi, jumlah) {
    // Kalau barang ini masih diproses, abaikan klik!
    if(kunciGudang[sku]) return; 
    
    kunciGudang[sku] = true; // 🔒 Tutup gembok khusus SKU ini!
    
    fetch('/update_stok', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({sku: sku, aksi: aksi, jumlah: jumlah})
    })
    .then(res => res.json())
    .then(res => {
        kunciGudang[sku] = false; // 🔓 Buka gembok setelah selesai!
        if(res.status == 'error') {
            alert(res.pesan);
        } else {
            document.getElementById('stok-'+sku).innerText = res.stok_baru;
            updateChartData(sku, res.stok_baru);
        }
    })
    .catch(() => kunciGudang[sku] = false); // 🔓 Buka gembok kalau error jaringan
}
function cariBarang(kategori) {
    let inputId = kategori === 'cargo' ? 'searchCargo' : 'searchCampuran';
    let cardClass = kategori === 'cargo' ? '.item-cargo' : '.item-campuran';

    let inputPencarian = document.getElementById(inputId).value.toLowerCase();
    let semuaBarang = document.querySelectorAll(cardClass);

    semuaBarang.forEach(function(barang) {
        let teksBarang = barang.getAttribute('data-search');
        if (teksBarang.includes(inputPencarian)) {
            barang.style.display = 'block'; 
        } else {
            barang.style.display = 'none'; 
        }
    });
}
if ('serviceWorker' in navigator) { navigator.serviceWorker.register('/sw.js'); }
// --- LOGIKA UPLOAD & CETAK CSV ---

window.dataRekapPrint = []; // Brankas sementara untuk nyimpen data sebelum dicetak

function prosesCSV(input) {
    let file = input.files[0];
    if(!file) return;
    
    let formData = new FormData();
    formData.append("file", file);
    
    document.getElementById('rekapModalTitle').innerText = "Sedang menghitung...";
    document.getElementById('rekapModalBody').innerHTML = "<div style='text-align:center; padding: 20px;'>Tunggu sebentar... ⏳</div>";
    document.getElementById('btnCetakRekap').style.display = 'none'; // Sembunyikan tombol cetak
    document.getElementById('rekapModal').style.display = 'flex';
    
    fetch('/upload_csv', { method: 'POST', body: formData })
    .then(res => res.json())
    .then(res => {
        input.value = ""; 
        if(res.status === 'error') {
            alert("Gagal: " + res.pesan);
            document.getElementById('rekapModal').style.display = 'none';
        } else {
            window.dataRekapPrint = res.data; // Simpan data ke brankas
            tampilkanRekap(res.data);
            document.getElementById('btnCetakRekap').style.display = 'block'; // Munculkan tombol cetak
        }
    })
    .catch(err => { alert("Gagal mengirim file."); document.getElementById('rekapModal').style.display = 'none'; });
}

function tampilkanRekap(data) {
    document.getElementById('rekapModalTitle').innerText = "📊 Rekap Kebutuhan Packing";
    let html = '<div style="font-size: 13px;">';
    
    data.forEach(item => {
        let warnaSisa = item.sisa < 0 ? 'color: #e74c3c; font-weight: bold; font-size: 16px;' : 'color: #2ecc71; font-weight: bold; font-size: 14px;';
        html += `
        <div style="border-bottom: 1px solid #eee; padding: 10px 0; display: flex; justify-content: space-between; align-items: center;">
            <div style="flex: 2;">
                <strong style="color: #2c3e50;">${item.nama}</strong><br>
                <span style="font-size: 11px; color: #7f8c8d;">${item.sku}</span>
            </div>
            <div style="flex: 1; text-align: center; border-left: 1px dashed #ccc;">Butuh:<br><strong style="color:#e67e22; font-size: 14px;">${item.butuh}</strong></div>
            <div style="flex: 1; text-align: center; border-left: 1px dashed #ccc;">Stok:<br><strong style="font-size: 14px;">${item.stok}</strong></div>
            <div style="flex: 1; text-align: right; border-left: 1px dashed #ccc; background: #f8f9fa; padding: 4px;">Sisa:<br><span style="${warnaSisa}">${item.sisa}</span></div>
        </div>`;
    });
    
    html += '</div>';
    document.getElementById('rekapModalBody').innerHTML = html;
}

// 🖨️ FUNGSI BARU: CETAK KE PRINTER THERMAL
function cetakRekap() {
    // Buka tab tersembunyi
    let printWindow = window.open('', '_blank');
    let today = new Date();
    let dateStr = today.getDate() + '/' + (today.getMonth()+1) + '/' + today.getFullYear() + ' ' + today.getHours() + ':' + today.getMinutes();

    // Buat desain khusus hitam putih (karena printer thermal ga ada warna)
    let html = `
    <html>
    <head>
        <title>Picking List - Pharadisa</title>
        <style>
            /* Paksa ukuran kertas 10x15 cm (100x150 mm) */
            @page { size: 100mm 150mm; margin: 3mm; }
            body { font-family: 'Arial', sans-serif; color: #000; margin: 0; padding: 0; font-size: 13px; }
            h2 { text-align: center; margin: 5px 0 2px 0; font-size: 18px; text-transform: uppercase; border-bottom: 2px solid #000; padding-bottom: 5px; }
            .date { text-align: center; font-size: 11px; margin-bottom: 10px; font-weight: bold; }
            table { width: 100%; border-collapse: collapse; }
            th, td { border: 1px solid #000; padding: 6px; text-align: left; vertical-align: middle; }
            th { font-weight: bold; background-color: #f0f0f0; }
            .qty { text-align: center; font-size: 18px; font-weight: bold; width: 35px; }
            .check { width: 25px; text-align: center; }
            .box { display: inline-block; width: 16px; height: 16px; border: 1px solid #000; }
            .item-name { font-size: 14px; font-weight: bold; line-height: 1.2; }
        </style>
    </head>
    <body>
        <h2>📦 PICKING LIST CARGO</h2>
        <div class="date">Waktu Cetak: ${dateStr}</div>
        <table>
            <thead>
                <tr>
                    <th>Warna & Size</th>
                    <th class="qty">Qty</th>
                    <th class="check">Cek</th>
                </tr>
            </thead>
            <tbody>
    `;

    window.dataRekapPrint.forEach(item => {
        html += `
            <tr>
                <td class="item-name">${item.nama}</td>
                <td class="qty">${item.butuh}</td>
                <td class="check"><div class="box"></div></td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
        <div style="text-align: center; margin-top: 10px; font-size: 10px;">Pharadisa Stock &copy; ${today.getFullYear()}</div>
        <script>
            // Otomatis perintahin browser untuk ngeprint pas halamannya kebuka
            window.onload = function() { window.print(); window.close(); }
        </script>
    </body>
    </html>
    `;

    printWindow.document.write(html);
    printWindow.document.close();
}