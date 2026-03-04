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

function simpanMentahan() {
    let modelInput = document.getElementById('mModel').value.trim();
    
    let data = {
        model: modelInput !== "" ? modelInput : "Cargo", // Kalau nggak sengaja kehapus, otomatis isi Cargo
        size: document.getElementById('mSize').value, 
        jumlah: document.getElementById('mQty').value
    };
    
    if(!data.size || !data.jumlah) { alert("Size dan Jumlah wajib diisi!"); return; }
    
    fetch('/tambah_mentahan', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data) })
    .then(() => window.location.reload());
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
    fetch('/update_stok', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sku: sku, aksi: aksi, jumlah: jumlah }) })
    .then(res => res.json()).then(data => {
        if(data.status === 'sukses') {
            document.getElementById('stok-' + data.sku).innerText = data.stok_baru;
            // Animasi chart otomatis berubah pas diklik tanpa perlu refresh web!
            if(window.updateChartData) {
                window.updateChartData(data.sku, data.stok_baru);
            }
        } else {
            alert(data.pesan);
        }
    });
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