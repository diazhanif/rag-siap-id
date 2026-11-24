# rag-siap-id

**RAG-Siap** adalah alat kecil untuk memeriksa korpus Markdown/TXT secara lokal sebelum dokumen dimasukkan ke sistem retrieval-augmented generation (RAG). Ia menandai file kosong, teks terlalu pendek/panjang, Markdown tanpa heading, file yang bukan UTF-8 valid, dan isi duplikat setelah normalisasi whitespace serta kapitalisasi.

```sh
python -m pip install .
rag-siap-id ./dokumen --min-chars 80 --max-chars 12000
```

Untuk pipeline, hasilkan JSON dan jadikan warning/error sebagai status gagal:

```sh
rag-siap-id ./dokumen --json --strict > audit.json
```

`--strict` mengembalikan kode keluar `1` jika ada warning atau error; argumen/path yang tidak valid mengembalikan `2`. CLI hanya membaca `.md`, `.markdown`, dan `.txt`, tidak mengunggah atau mengubah file, serta melewati `.git`, virtualenv, `node_modules`, cache Python, dan symlink. Laporan memakai path relatif dan penanda root `.` (bukan absolut path lokal), serta menyertakan panjang, jumlah kata, heading, dan kode temuan—bukan isi dokumen atau checksum konten.

Ambang karakter hanyalah heuristik dan **bukan** pengukuran token. Hasil ini tidak menjamin relevansi chunk atau kualitas jawaban. Gunakan tokenizer dan evaluasi retrieval yang sesuai dengan stack Anda sebelum produksi.

Sebagai library:

```python
from rag_siap import audit_corpus

report = audit_corpus("./dokumen", min_chars=80, max_chars=12000)
print(report.summary())
```

Tes: `python -m unittest discover -s tests -v`. Tidak ada dependensi runtime. Python 3.9+.

## Lisensi

MIT. Lihat [LICENSE](LICENSE).
