# Nize CLI

Nize adalah AI chat client berbasis terminal yang terhubung ke relay **api.iamhc.cn** (OpenAI-compatible). Tanpa dependency eksternal — cukup pakai `fetch` dan `readline` bawaan Node.js.

Selain chat biasa, Nize punya kemampuan menjalankan **perintah shell nyata** (curl, dig, whois, openssl, ping, dll) untuk mengecek hal-hal seperti URL/domain secara langsung — tapi setiap perintah harus kamu setujui dulu sebelum dijalankan.

## ✨ Fitur

- Chat AI langsung dari terminal, tanpa dependency tambahan
- Ganti model AI kapan saja lewat perintah `/model`
- Tool calling: AI bisa minta izin menjalankan perintah shell read-only untuk mengambil data nyata (headers, DNS, sertifikat TLS, dll)
- Simpan balasan AI (kode) langsung ke file dengan `/save`
- Export seluruh percakapan ke JSON dengan `/export`
- Ganti system prompt di tengah sesi dengan `/system`
- Pilihan model tersimpan otomatis untuk sesi berikutnya

## 📦 Instalasi

```bash
git clone https://github.com/username/nize-cli.git
cd nize-cli
```

Tidak perlu `npm install` — Nize tidak memakai dependency eksternal apa pun, cukup Node.js versi 18 ke atas (karena butuh `fetch` bawaan).

## ⚙️ Konfigurasi

Buat file `.env` di folder yang sama dengan `aicli.js`, isinya:

```env
AICLI_API_KEY=api_key_kamu_dari_iamhc
AICLI_BASE_URL=https://api.iamhc.cn/v1
AICLI_MODEL=Qwen3.5-397B-A17B
```

Keterangan:
- **AICLI_API_KEY** — wajib diisi. Ambil API key dari akun kamu di [iamhc](https://api.iamhc.cn).
- **AICLI_BASE_URL** — bisa dikosongkan, defaultnya sudah `https://api.iamhc.cn/v1`.
- **AICLI_MODEL** — model default yang dipakai saat chat dimulai. Bisa diganti kapan saja lewat perintah `/model` di dalam chat. Contoh pilihan model yang tersedia: `DeepSeek-V4-Pro`, `glm-5.2`, `Kimi-K2.6`, `MiniMax-M3`, `Qwen3-Coder-Next-FP8`, dan lainnya (lihat daftar lengkap dengan mengetik `/model` saat chat berjalan).

> ⚠️ Jangan commit file `.env` ke GitHub — pastikan sudah masuk `.gitignore` supaya API key kamu tidak bocor.

## 🚀 Menjalankan

```bash
node aicli.js
```

Atau langsung dengan opsi tambahan:

```bash
node aicli.js --model glm-5.2 --system "Jawab dengan singkat dan padat."
```

## 🌐 Panggil cukup dengan `nize` (global, via `npm link`)

Biar tidak perlu ketik `node aicli.js` terus-terusan, kamu bisa daftarkan Nize sebagai perintah global di terminal cukup dengan mengetik `nize` dari folder mana saja.

1. Pastikan file `aicli.js` bisa dieksekusi (khusus Linux/macOS):

   ```bash
   chmod +x aicli.js
   ```

2. Dari dalam folder project ini, jalankan:

   ```bash
   npm link
   ```

   Perintah ini membaca field `bin` di `package.json` (`"nize": "./aicli.js"`) dan membuat symlink global, jadi perintah `nize` langsung tersedia di PATH kamu.

3. Sekarang dari folder mana pun, cukup jalankan:

   ```bash
   nize
   ```

   atau dengan opsi tambahan seperti biasa:

   ```bash
   nize --model glm-5.2 --system "Jawab dengan singkat dan padat."
   ```

> Catatan: file `.env` tetap dibaca dari folder tempat `aicli.js` asli berada (bukan folder tempat kamu menjalankan `nize`), jadi taruh `.env` di folder project ini.

Kalau suatu saat mau membatalkan/menghapus link globalnya:

```bash
npm unlink -g nize-cli
```

## 💬 Perintah di dalam chat

| Perintah | Fungsi |
|---|---|
| `/exit` atau `/quit` | Keluar dari chat |
| `/clear` | Hapus riwayat percakapan |
| `/model` | Lihat daftar model dan pilih secara interaktif |
| `/model <nama>` | Ganti model langsung (bisa pakai nomor atau nama sebagian) |
| `/system <teks>` | Ganti system prompt di tengah sesi |
| `/save <file>` | Simpan blok kode dari balasan terakhir AI ke file |
| `/export <file>` | Simpan seluruh percakapan sebagai JSON |
| `/help` | Tampilkan daftar perintah ini |

## 🛠️ Akses terminal oleh AI

Nize bisa meminta izin menjalankan perintah shell nyata (read-only) untuk mengambil data langsung, misalnya cek DNS, header HTTP, atau sertifikat TLS suatu domain — tapi **setiap perintah akan ditampilkan dulu ke kamu**, dan hanya berjalan setelah kamu menyetujuinya dengan `y` (yes), `n` (no), atau `e` (edit perintah sebelum dijalankan).

## 📄 Lisensi

Bebas digunakan dan dimodifikasi sesuai kebutuhan kamu.
