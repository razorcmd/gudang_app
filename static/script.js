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

function updateProgress(id, aksi) {
    let nanya = aksi == 'ke_finishing' ? "Berapa potong yang turun ke Finishing hari ini?" : "Berapa potong yang selesai ke Gudang hari ini?";
    let qty = prompt(nanya);
    if(qty && !isNaN(qty)) {
        fetch('/update_progress', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({id: id, aksi: aksi, qty: qty}) })
        .then(res => res.json()).then(res => {
            if(res.status == 'error') alert(res.pesan); else {
                if(aksi == 'ke_gudang') alert("Sukses! Jangan lupa klik tombol '+ Masuk' di Tab Gudang biar stok asli nambah.");
                window.location.reload();
            }
        });
    }
}

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